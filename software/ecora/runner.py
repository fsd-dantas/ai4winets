"""Deterministic run orchestration over a frozen study and the finite reference world.

The orchestrator owns the decision loop and the seed plan. It does not decide anything:
every decision belongs to a configured provider, and every input the providers receive
crosses the audited boundary. Advancing the world, exporting observations, assembling the
two built-from stage inputs and closing the run are harness responsibilities fixed across
treatments, so they cannot vary with the arm under comparison.
"""

from functools import partial
import random

from .boundary import Boundary
from .contracts import Record, digest, require
from .fixtures import ASSEMBLY, fixture_environment
from .model import FiniteModel
from .registry import ProviderResult
from .schema import INPUT_TYPES, OUTPUT_TYPES
from .assessment import assessment_binding
from .eco import eco_binding
from .exact import exact_binding
from .experts import expert_binding
from .planning import planner_binding
from .scenario import describe_world, verify_world
from .study import resolve
from .telemetry import projection_binding
from .truth import (TruthPort, oracle_assessment_binding, oracle_diagnosis_binding,
                    truth_binding)

STREAM_NAMES = ("arrivals", "errors", "disturbances", "controller")

# The decision knowledge is data. These names are kept because the package and its tests
# refer to them, but what they hold is read from `studies/baseline.json` rather than
# written here: the rule inventory, the local view a projection relays, the planner and
# coordination configuration, and how a concluded diagnosis becomes symbolic predicates.
# A different study file is a different study, not a tuned version of this one.
BASELINE = resolve("baseline")
PROJECTION = BASELINE.projection
RULES = BASELINE.rules
PLANNER = BASELINE.planner
ECO = BASELINE.eco
PREDICATE_MAP = BASELINE.predicate_map
ORACLE = BASELINE.oracle["telemetry"]
ORACLE_READS = BASELINE.oracle["diagnosis_reads"]


class Stream:
    """One named draw sequence. Its position depends only on its own draws."""

    def __init__(self, name, seed):
        self.name = name
        self.draws = 0
        self._random = random.Random(f"{seed}:{name}")

    def random(self):
        self.draws += 1
        return self._random.random()

    def choice(self, population):
        self.draws += 1
        return self._random.choice(list(population))

    def snapshot(self):
        return {"stream": self.name, "draws": self.draws}


class Streams:
    """Independent named streams derived from the study's frozen seed manifest.

    Each stream is its own generator, so a controller draw cannot shift an arrival draw.
    Sharing one generator across purposes would make the exogenous inputs depend on how
    often a provider happened to consult its own randomness, and two treatments would then
    no longer face the same world.
    """

    def __init__(self, seed_manifest, names=STREAM_NAMES):
        seed = digest(seed_manifest)
        self._streams = {name: Stream(name, seed) for name in names}

    def __getitem__(self, name):
        require(name in self._streams, f"undeclared random stream: {name}")
        return self._streams[name]

    def snapshot(self):
        return {name: stream.snapshot() for name, stream in sorted(self._streams.items())}


def observation_batch(model, capability_ids, at, period_s, sequence):
    """Build the adapter batch for a moment in the world.

    Regeneration and the original run share this, so a prefix that fails to verify has
    diverged in the world rather than in how two code paths happened to describe it.
    """
    exported = model.observations(capability_ids=capability_ids, window_s=period_s)
    # A signal that did not come back is carried as unknown, and the batch says so. An
    # adapter that reported full coverage while holding a timed-out probe would be
    # claiming to have seen something it did not.
    answered = [o for o in exported if o["quality"] != "missing"]
    return Record("AdapterObservationBatch", {
        "observations": exported, "watermark_s": at,
        "window": {"start_s": max(0.0, at - period_s), "end_s": at},
        "sequence": sequence,
        "completeness": len(answered) / len(exported) if exported else 0,
        "omitted_metrics": sorted({o["metric"] for o in exported if o["quality"] == "missing"})})


class ModelActionProvider:
    """Applies an admitted command to the finite world and reports what it observed.

    An applied receipt cites the observation the run exports at the next decision epoch,
    derived from the model's own identity scheme rather than a formatted guess, so the
    evidence a receipt names is evidence the run actually produces.
    """

    def __init__(self, model, period_s):
        self.model = model
        self.period_s = period_s

    def invoke(self, inputs, prior_state, context):
        watermark = context.data["decision_watermark_s"]
        receipts = []
        for message in inputs:
            payload = Record.from_dict(message.data["payload"])
            if payload.kind != "ActionCommand":
                continue
            applied, why = self.model.apply(payload)
            readback = {"select_path": "path_state", "set_ami_pacing": "pacing_profile"}
            metric = readback.get(payload.data["operator"])
            evidence = [self.model.observation_id(payload.data["target"], metric,
                                                  watermark + self.period_s)] if applied and metric else []
            receipts.append(Record("ActionReceipt", {
                "command_id": payload.data["command_id"],
                "idempotency_key": payload.data["idempotency_key"],
                "disposition": "applied" if applied else "rejected",
                "applied_at_s": watermark if applied else None,
                "resulting_state": self.model.truth()["selected_path"] if applied else {},
                "application_observation_ids": evidence,
                "reason": None if applied else {"code": why, "detail": "The world refused the command."}}))
        if not receipts:
            return ProviderResult((), {}, {"applied": 0}, "no_op",
                                  {"code": "no_command", "detail": "No admitted command reached the actuator."})
        return ProviderResult(tuple(receipts), {}, {"applied": len(receipts)})


class Run:
    """One run of one treatment against one frozen scenario."""

    def __init__(self, boundary, model, *, streams, capability_ids, period_s, epochs, assembly,
                 start_epoch=0, predicate_map=None):
        self.boundary = boundary
        self.model = model
        self.streams = streams
        self.capability_ids = capability_ids
        self.period_s = period_s
        self.epochs = epochs
        self.assembly = assembly
        # How a concluded diagnosis becomes symbolic predicates. Harness-fixed across the
        # treatments of one study, so the projection cannot vary with the arm under
        # comparison, and declared by the study rather than by this module.
        self.predicate_map = BASELINE.predicate_map if predicate_map is None else predicate_map
        # A branch starts partway through, on a world regenerated and verified against the
        # recorded prefix. Everything it produces from here is its own.
        self.start_epoch = start_epoch
        self._state = {}

    def _advance(self, stage, invocation_id, dataset_ids, watermark):
        """Invoke a stage, carrying its own prior state forward between epochs."""
        dataset = self.boundary.invoke(
            stage, invocation_id, dataset_ids, watermark_s=watermark,
            prior_state_hash=self._state.get(stage),
            random_state=self.streams["controller"].snapshot())
        self._state[stage] = self.boundary.store.invocation(invocation_id).data["next_state_hash"]
        return dataset.data["dataset_id"]

    def _epoch(self, index):
        at = index * self.period_s
        self.model.advance_to(at)
        source = self._export(str(index), at, index)
        telemetry = self._advance("telemetry", f"telemetry:{index}", [source.data["dataset_id"]], at)
        diagnosis = self._advance("diagnosis", f"diagnosis:{index}", [telemetry], at)
        known, unknown = self._projection(diagnosis)
        problem = self.boundary.assemble(
            f"assemble-planning:{index}", "planning", [diagnosis],
            Record("PlanningProblem", {**self.assembly["planning"],
                                       "known_predicates": known, "unknown_predicates": unknown}),
            watermark_s=at).data["dataset_id"]
        planning = self._advance("planning", f"planning:{index}", [problem], at)
        resolution = self._advance("resolution", f"resolution:{index}", [planning], at)
        return self._advance("action", f"action:{index}", [resolution], at)

    def _projection(self, diagnosis_dataset):
        """Project the diagnosis onto symbolic predicates, and say what stays unknown.

        This reads the diagnosis the controller reached, not the world. Deriving the
        planner's initial state from model truth would hand it state no arm was permitted
        to observe, and the difference between arms would stop meaning anything.

        A leg currently carrying traffic is evidently reachable. Any other leg's
        reachability is unknown until a probe says otherwise, and an unknown precondition
        prohibits the edge, so a planner cannot switch onto a leg on no evidence.
        """
        concluded = set()
        for message in self.boundary.store.messages(diagnosis_dataset):
            payload = Record.from_dict(message.data["payload"])
            if payload.kind != "DiagnosisRecord":
                continue
            concluded.update(h["label"] for h in payload.data["hypotheses"]
                             if h["status"] == "supported")
        mapping = self.predicate_map
        known = set()
        for label, predicates in mapping.items():
            if label in concluded:
                known.update(predicates)
        unknown = {predicate for predicates in mapping.values()
                   for predicate in predicates if predicate.startswith("reachable:")} - known
        return sorted(known), sorted(unknown)

    def _export(self, label, at, sequence):
        batch = observation_batch(self.model, self.capability_ids, at, self.period_s, sequence)
        return self.boundary.ingest(f"ingest:{label}", batch, watermark_s=at)

    def execute(self):
        """Run every epoch, then close the run with a result and an assurance report."""
        last_action = None
        for index in range(self.start_epoch, self.epochs):
            last_action = self._epoch(index)
        closing = self.epochs * self.period_s
        self.model.advance_to(closing)
        # A closing observation, so the consequence of the final action is observed rather
        # than asserted. Without it a receipt would cite evidence the run never exports.
        self._export("closing", closing, self.epochs)
        cohorts = self.boundary.assemble(
            "assemble-result", "result", [last_action] if last_action else [],
            Record("ResultInput", {
                "receipt_ids": [], "observation_ids": [],
                "cohorts": self.model.cohorts(self.assembly["result"]["cohorts"])}),
            watermark_s=closing).data["dataset_id"]
        result = self._advance("result", "result", [cohorts], closing)
        return self._advance("assurance", "assurance", [result], closing)


class Continuation:
    """Regenerates a recorded run's causal prefix and verifies it before any branch.

    Checkpointing the world is not available here, so the prefix is rebuilt under the
    recorded configuration and the commands the recorded run actually applied, then checked
    against the observations that run ingested. Verification is the whole point: a
    counterfactual built on a prefix that did not reproduce is not a counterfactual, and an
    unverified prefix is not a branch point.

    What a verified branch supports is a service outcome under its own continuation. It
    does not license reading the original run's later evidence as the counterfactual: that
    evidence belongs to the actions that were actually taken.
    """

    def __init__(self, store, *, build_model, capability_ids, period_s):
        self.store = store
        self.build_model = build_model
        self.capability_ids = capability_ids
        self.period_s = period_s

    def _payloads(self, dataset_id):
        return [Record.from_dict(m.data["payload"]) for m in self.store.messages(dataset_id)]

    def recorded_prefix(self, epochs):
        """The observation payload each recorded epoch ingested."""
        return [[p.content_hash for p in self._payloads(f"dataset:ingest:{index}")]
                for index in range(epochs)]

    def applied_commands(self, epoch):
        """The commands the recorded run applied, not merely the ones it admitted."""
        applied = {p.data["command_id"] for p in self._payloads(f"dataset:action:{epoch}")
                   if p.kind == "ActionReceipt" and p.data["disposition"] == "applied"}
        return [p for p in self._payloads(f"dataset:resolution:{epoch}")
                if p.kind == "ActionCommand" and p.data["command_id"] in applied]

    def regenerate(self, branch_epoch):
        """Rebuild the world up to the branch point, refusing to continue if it diverges."""
        recorded = self.recorded_prefix(branch_epoch)
        model = self.build_model()
        for index in range(branch_epoch):
            at = index * self.period_s
            model.advance_to(at)
            batch = observation_batch(model, self.capability_ids, at, self.period_s, index)
            require([batch.content_hash] == recorded[index],
                    f"regenerated prefix diverges from the recorded run at epoch {index}")
            for command in self.applied_commands(index):
                applied, why = model.apply(command)
                require(applied, f"a recorded command no longer applies at epoch {index}: {why}")
        return model


def closed_loop_environment(model, *, period_s, assembly=None, extra_capabilities=(),
                            projection=None, rules=None, scenario=None, study=None):
    """A study whose action stage is bound to the finite world, with a Null arm beside it.

    The Null treatment and the closed-loop treatment differ in one binding, so a paired
    comparison between them attributes any difference to that stage rather than to the
    orchestration around it.

    The scenario and the model are held to each other. A supplied scenario is the source
    the world was built from and the run is refused if the model does not match it; where
    none is supplied the scenario is derived from the model instead. Either way the
    scenario hash frozen into every claim describes the world that actually ran.
    """
    study = study or BASELINE
    projection = projection or study.projection
    rules = rules or study.rules
    planner, coordination = study.planner, study.eco
    oracle, oracle_reads = study.oracle["telemetry"], study.oracle["diagnosis_reads"]
    assembly = assembly or study.assembly
    if scenario is not None and hasattr(model, "resolved"):
        # A simulated world reports what it built; it is held to the scenario the same way.
        from .simulator import verify_simulated
        verify_simulated(model.resolved, scenario)
    elif scenario is not None:
        verify_world(model, scenario)
    else:
        # A derived scenario states what the world is, not what a study needs of it: the
        # capabilities it would name are the ones this function is about to grant, so
        # requiring them here would only check the grant against itself.
        scenario = describe_world(model, scenario_id="scenario:derived")
    registry, study, scenario_set, scenario, caps = fixture_environment(
        assembly=assembly, extra_capabilities=extra_capabilities, scenario=scenario)
    # Truth is granted separately from observation and actuation: the registry refuses an
    # ordinary binding that holds a truth capability, so the split has to be explicit.
    every = caps.data["capabilities"]
    granted = [c["capability_id"] for c in every if c["kind"] != "truth"]
    truths = [c["capability_id"] for c in every if c["kind"] == "truth"]
    spec = Record("ProviderSpec", {
        "stage_id": "action", "provider_id": "model.action", "provider_version": "finite-v1",
        "arm": "proposed", "input_types": list(INPUT_TYPES["action"]),
        "output_types": list(OUTPUT_TYPES["action"]), "state_schema_version": "1",
        "capability_ids": granted, "direct_truth_access": False})
    registry.register(spec, partial(ModelActionProvider, model, period_s))
    data = study.data
    null_treatment = next(t for t in data["treatments"] if t["treatment_id"] == "null_baseline")
    bindings = []
    for binding in null_treatment["bindings"]:
        if binding["stage_id"] != "action":
            bindings.append(dict(binding))
            continue
        configuration = {}
        bindings.append({k: v for k, v in spec.data.items() if k != "direct_truth_access"} |
                        {"information_regime": "contract_only", "allow_privileged_inputs": False,
                         "configuration": configuration, "configuration_hash": digest(configuration)})
    # A third treatment differing from closed_loop in the telemetry binding alone, so the
    # three form a chain where each step changes exactly one stage.
    projection = projection_binding(registry, granted, projection)
    observing = [dict(projection) if b["stage_id"] == "telemetry" else dict(b) for b in bindings]

    def diagnosing(organisation):
        binding = expert_binding(registry, granted, rules, organisation)
        return [dict(binding) if b["stage_id"] == "diagnosis" else dict(b) for b in observing]

    reasoning = diagnosing("blackboard")
    planning = planner_binding(registry, granted, planner, "uniform_cost")
    planned = [dict(planning) if b["stage_id"] == "planning" else dict(b) for b in reasoning]
    # Means-ends analysis over the same STRIPS representation and the same operator
    # catalog, one binding from the uniform-cost arm and sharing its Null resolution.
    # GPS is a different search, not a different problem, so what separates the two rows
    # is the procedure and nothing else.
    means_ends = planner_binding(registry, granted, planner, "gps")
    gps_planned = [dict(means_ends) if b["stage_id"] == "planning" else dict(b)
                   for b in planned]

    coordinating = eco_binding(registry, granted, coordination, "resolution", "expiring_marks")
    coordinated = [dict(coordinating) if b["stage_id"] == "resolution" else dict(b)
                   for b in planned]

    # An Oracle telemetry arm taints the whole pipeline downstream of it, so every stage
    # in that treatment must be permitted to consume privileged input. That is two changes
    # rather than one, and it is not presented as a drop-in swap of a single binding.
    port = TruthPort(model, caps.data["capabilities"])
    # An Oracle sees everything an ordinary arm sees, and truth besides. It is a
    # superset reference, not a different set of eyes.
    oracle_telemetry = truth_binding(registry, port, granted + truths, oracle)
    privileged = [dict(oracle_telemetry) if b["stage_id"] == "telemetry"
                  else {**b, "allow_privileged_inputs": True} for b in coordinated]

    # The action Oracle is the same adapter as the Proposed arm. stage-arms.md says to
    # declare that equivalence where the integration is direct enough, rather than invent
    # a gap: a fabricated difference between them would be measured as one.
    oracle_action = Record("ProviderSpec", {
        "stage_id": "action", "provider_id": "action.verified_application",
        "provider_version": "finite-v1", "arm": "oracle",
        "input_types": list(INPUT_TYPES["action"]), "output_types": list(OUTPUT_TYPES["action"]),
        "state_schema_version": "1", "capability_ids": granted, "direct_truth_access": False})
    if not registry.registered("action", "action.verified_application", "finite-v1"):
        registry.register(oracle_action, partial(ModelActionProvider, model, period_s))
    verified = [{k: v for k, v in oracle_action.data.items() if k != "direct_truth_access"} |
                {"information_regime": "contract_only", "allow_privileged_inputs": False,
                 "configuration": {}, "configuration_hash": digest({})}
                if b["stage_id"] == "action" else dict(b) for b in coordinated]

    # The last two stages had only a Null arm, so every run ended inconclusive by
    # construction. These reach a verdict where the evidence supports one.
    extraction = assessment_binding(registry, granted, {}, "result")
    extracted = [dict(extraction) if b["stage_id"] == "result" else dict(b) for b in verified]
    evaluation = assessment_binding(
        registry, granted, {"requirements": scenario.data["requirements"],
                            "evaluator_version": "assessment-v1"}, "assurance")
    assured = [dict(evaluation) if b["stage_id"] == "assurance" else dict(b) for b in extracted]

    # Exact references at contract-limited information. Each is one binding from the arm
    # it references, so the gap between them is algorithmic and not informational.
    exact_plan = exact_binding(registry, granted, planner, "planning")
    planned_exactly = [dict(exact_plan) if b["stage_id"] == "planning" else dict(b)
                       for b in coordinated]
    exact_resolve = exact_binding(registry, granted, coordination, "resolution")
    resolved_exactly = [dict(exact_resolve) if b["stage_id"] == "resolution" else dict(b)
                        for b in planned_exactly]

    # Measurement without decision: the Null arm's telemetry, diagnosis, planning and
    # resolution, with the two assessment stages that can reach a verdict. Without it the
    # study can only show requirements met by arms that also act, and a reader has no way
    # to see what the world does when nothing intervenes. It is the counterfactual the
    # closed-loop arms are worth comparing against.
    unattended = [dict(extraction) if b["stage_id"] == "result"
                  else dict(evaluation) if b["stage_id"] == "assurance"
                  else dict(b) for b in bindings]

    # The last two stages gain the references stage-arms.md designates for them:
    # independent extraction from the complete event record, and reference evaluation
    # against full truth with the same frozen requirements. Both read truth, so both are
    # granted it explicitly and both declare what they read.
    oracle_extraction = oracle_assessment_binding(
        registry, port, granted + truths, {"cohorts": assembly["result"]["cohorts"]}, "result")
    exact_measured = [dict(oracle_extraction) if b["stage_id"] == "result"
                      else {**b, "allow_privileged_inputs": True} for b in assured]
    oracle_evaluation = oracle_assessment_binding(
        registry, port, granted + truths,
        {"cohorts": assembly["result"]["cohorts"],
         "requirements": scenario.data["requirements"],
         "evaluator_version": "assessment-v1"}, "assurance")
    exact_assured = [dict(oracle_evaluation) if b["stage_id"] == "assurance" else dict(b)
                     for b in exact_measured]

    # A diagnosis Oracle reads truth directly, so it needs no Oracle upstream of it. This
    # treatment differs from eco in the diagnosis binding alone, which is what makes the
    # gap between them a difference in information rather than in anything else.
    oracle_diagnosis = oracle_diagnosis_binding(
        registry, port, granted + truths,
        {**rules, "reads": oracle_reads})
    informed = [dict(oracle_diagnosis) if b["stage_id"] == "diagnosis"
                else {**b, "allow_privileged_inputs": True} for b in coordinated]

    data = {**data, "treatments": [*data["treatments"],
                                   {"treatment_id": "closed_loop", "bindings": bindings},
                                   {"treatment_id": "observing", "bindings": observing},
                                   {"treatment_id": "expert", "bindings": diagnosing("single_engine")},
                                   {"treatment_id": "blackboard", "bindings": reasoning},
                                   {"treatment_id": "planner", "bindings": planned},
                                   {"treatment_id": "gps", "bindings": gps_planned},
                                   {"treatment_id": "eco", "bindings": coordinated},
                                   {"treatment_id": "oracle", "bindings": privileged},
                                   {"treatment_id": "verified_action", "bindings": verified},
                                   {"treatment_id": "measured", "bindings": extracted},
                                   {"treatment_id": "unattended", "bindings": unattended},
                                   {"treatment_id": "assured", "bindings": assured},
                                   {"treatment_id": "oracle_result", "bindings": exact_measured},
                                   {"treatment_id": "oracle_assurance", "bindings": exact_assured},
                                   {"treatment_id": "exact_planning", "bindings": planned_exactly},
                                   {"treatment_id": "exact_resolution", "bindings": resolved_exactly},
                                   {"treatment_id": "oracle_diagnosis", "bindings": informed}]}
    return registry, Record("StudyManifest", data), scenario_set, scenario, caps
