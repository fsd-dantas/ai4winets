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
from .eco import eco_binding
from .experts import expert_binding
from .planning import planner_binding
from .telemetry import projection_binding

STREAM_NAMES = ("arrivals", "errors", "disturbances", "controller")

# The local view one site's agents are permitted: its own AMI queue and its path selector.
# Declared here rather than inferred, so what a projection expects is frozen with a study.
PROJECTION = {
    "neighbourhood": {"subject": "site-1", "services": ["ami", "shared"]},
    "expected": [
        {"subject": "site-1", "service": "ami", "metric": "queue_occupancy", "unit": "byte",
         "capability_id": "observe.ami.queue"},
        {"subject": "site-1", "service": "shared", "metric": "path_state", "unit": "id",
         "capability_id": "observe.shared.path"},
        {"subject": "site-1", "service": "ami", "metric": "pacing_profile", "unit": "id",
         "capability_id": "observe.ami.pacing"},
        {"subject": "site-1/lte", "service": "shared", "metric": "path_probe", "unit": "s",
         "capability_id": "observe.probe.lte"},
        {"subject": "site-1/alternative", "service": "shared", "metric": "path_probe",
         "unit": "s", "capability_id": "observe.probe.alternative"},
    ],
    "max_observation_age_s": 0.5,
}

# The shared rule inventory, over the operational predicates declared in v1-scope.md and
# the signals the projection relays. The pressure threshold is the declared
# queue_pressure_fraction (0.75) against queue_limit_bytes (65536); both are nominal.
# `settled_on_alternative` requires two conclusions rather than an observation, so an
# organisation has to reach a fixed point rather than firing every rule once.
RULES = {
    "rules": [
        {"rule_id": "queue_pressure", "requires": ["queue_occupancy"],
         "condition": {"metric": "queue_occupancy", "op": "ge", "value": 49152},
         "concludes": "local_queue_pressure", "priority": 10,
         "contradicts": ["local_queue_nominal"],
         "explanation": "Occupied bytes reached the declared pressure fraction."},
        {"rule_id": "queue_nominal", "requires": ["queue_occupancy"],
         "condition": {"metric": "queue_occupancy", "op": "lt", "value": 49152},
         "concludes": "local_queue_nominal", "priority": 10,
         "contradicts": ["local_queue_pressure"],
         "explanation": "Occupied bytes remained below the declared pressure fraction."},
        {"rule_id": "on_alternative", "requires": ["path_state"],
         "condition": {"metric": "path_state", "op": "eq", "value": "alternative"},
         "concludes": "on_alternative_path", "priority": 5, "contradicts": ["on_primary_path"],
         "explanation": "The site's selector reports the alternative leg."},
        {"rule_id": "on_primary", "requires": ["path_state"],
         "condition": {"metric": "path_state", "op": "eq", "value": "lte"},
         "concludes": "on_primary_path", "priority": 5, "contradicts": ["on_alternative_path"],
         "explanation": "The site's selector reports the primary leg."},
        {"rule_id": "pacing_normal", "requires": ["pacing_profile"],
         "condition": {"metric": "pacing_profile", "op": "eq", "value": "normal"},
         "concludes": "pacing_is_normal", "priority": 5,
         "explanation": "The AMI release profile reads back as normal."},
        {"rule_id": "pacing_restricted", "requires": ["pacing_profile"],
         "condition": {"metric": "pacing_profile", "op": "eq", "value": "restricted"},
         "concludes": "pacing_is_restricted", "priority": 5,
         "explanation": "The AMI release profile reads back as restricted."},
        {"rule_id": "lte_viable", "requires": ["site-1/lte/path_probe"],
         "condition": {"metric": "site-1/lte/path_probe", "op": "le", "value": 1.0},
         "concludes": "lte_viable", "priority": 5,
         "explanation": "A probe on the primary leg came back within its timeout."},
        {"rule_id": "alternative_viable", "requires": ["site-1/alternative/path_probe"],
         "condition": {"metric": "site-1/alternative/path_probe", "op": "le", "value": 1.0},
         "concludes": "alternative_viable", "priority": 5,
         "explanation": "A probe on the alternative leg came back within its timeout."},
        {"rule_id": "settled_on_alternative", "requires": [], "condition": None,
         "requires_predicates": ["local_queue_nominal", "on_alternative_path"],
         "concludes": "settled_on_alternative_path", "priority": 1,
         "explanation": "The alternative leg is carrying the load without queue pressure."},
    ],
    "activation_budget": 200,
}

# What the symbolic planner configures, and what the eco resolver may issue. Both are
# frozen with the study: the costs a planner optimises and the authority a resolver holds
# must not vary with the arm whose contribution is being measured.
PLANNER = {"sites": ["site-1"], "costs": {"select_path": 2, "set_ami_pacing": 1},
           "agent_id": "agent:site-1:ami", "service": "ami", "validity_s": 1,
           "certify": True, "state_limit": 64, "expansion_budget": 10000}

ECO = {"mark_ttl_s": 0.3, "backoff_min_s": 0.1, "backoff_max_s": 0.3, "validity_s": 1,
       "mark_transport_model": "ideal_local",
       "authority": {"select_path": "actuate.shared.path",
                     "set_ami_pacing": "actuate.ami.pacing"}}

# How a concluded diagnosis becomes symbolic predicates. Harness-fixed across treatments,
# so the projection cannot vary with the arm whose contribution is being measured. A leg
# carrying traffic is evidently reachable; nothing here asserts the other leg is.
PREDICATE_MAP = {
    "on_primary_path": ["selected_path:site-1:lte"],
    "on_alternative_path": ["selected_path:site-1:alternative"],
    # Reachability now comes from a probe that answered, not from the leg being in use.
    "lte_viable": ["reachable:site-1:lte"],
    "alternative_viable": ["reachable:site-1:alternative"],
    "pacing_is_normal": ["pacing:site-1:normal"],
    "pacing_is_restricted": ["pacing:site-1:restricted"],
    "local_queue_nominal": ["queue_nominal:site-1:ami"],
    "local_queue_pressure": ["queue_pressure:site-1:ami"],
}


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
                 start_epoch=0):
        self.boundary = boundary
        self.model = model
        self.streams = streams
        self.capability_ids = capability_ids
        self.period_s = period_s
        self.epochs = epochs
        self.assembly = assembly
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
        known = set()
        for label, predicates in PREDICATE_MAP.items():
            if label in concluded:
                known.update(predicates)
        unknown = {predicate for predicates in PREDICATE_MAP.values()
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
                            projection=None, rules=None):
    """A study whose action stage is bound to the finite world, with a Null arm beside it.

    The Null treatment and the closed-loop treatment differ in one binding, so a paired
    comparison between them attributes any difference to that stage rather than to the
    orchestration around it.
    """
    registry, study, scenario_set, scenario, caps = fixture_environment(
        assembly=assembly, extra_capabilities=extra_capabilities)
    spec = Record("ProviderSpec", {
        "stage_id": "action", "provider_id": "model.action", "provider_version": "finite-v1",
        "arm": "proposed", "input_types": list(INPUT_TYPES["action"]),
        "output_types": list(OUTPUT_TYPES["action"]), "state_schema_version": "1",
        "capability_ids": [c["capability_id"] for c in caps.data["capabilities"]],
        "direct_truth_access": False})
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
    granted = [c["capability_id"] for c in caps.data["capabilities"]]
    projection = projection_binding(registry, granted, projection or PROJECTION)
    observing = [dict(projection) if b["stage_id"] == "telemetry" else dict(b) for b in bindings]

    def diagnosing(organisation):
        binding = expert_binding(registry, granted, rules or RULES, organisation)
        return [dict(binding) if b["stage_id"] == "diagnosis" else dict(b) for b in observing]

    reasoning = diagnosing("blackboard")
    planning = planner_binding(registry, granted, PLANNER, "uniform_cost")
    planned = [dict(planning) if b["stage_id"] == "planning" else dict(b) for b in reasoning]
    coordinating = eco_binding(registry, granted, ECO, "resolution", "expiring_marks")
    coordinated = [dict(coordinating) if b["stage_id"] == "resolution" else dict(b)
                   for b in planned]

    data = {**data, "treatments": [*data["treatments"],
                                   {"treatment_id": "closed_loop", "bindings": bindings},
                                   {"treatment_id": "observing", "bindings": observing},
                                   {"treatment_id": "expert", "bindings": diagnosing("single_engine")},
                                   {"treatment_id": "blackboard", "bindings": reasoning},
                                   {"treatment_id": "planner", "bindings": planned},
                                   {"treatment_id": "eco", "bindings": coordinated}]}
    return registry, Record("StudyManifest", data), scenario_set, scenario, caps
