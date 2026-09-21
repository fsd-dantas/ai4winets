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

STREAM_NAMES = ("arrivals", "errors", "disturbances", "controller")


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
            evidence = [self.model.observation_id(payload.data["target"], "path_state",
                                                  watermark + self.period_s)] if applied else []
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

    def __init__(self, boundary, model, *, streams, capability_ids, period_s, epochs, assembly):
        self.boundary = boundary
        self.model = model
        self.streams = streams
        self.capability_ids = capability_ids
        self.period_s = period_s
        self.epochs = epochs
        self.assembly = assembly
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
        problem = self.boundary.assemble(
            f"assemble-planning:{index}", "planning", [diagnosis],
            Record("PlanningProblem", {**self.assembly["planning"],
                                       "known_predicates": sorted(self._predicates()),
                                       "unknown_predicates": []}),
            watermark_s=at).data["dataset_id"]
        planning = self._advance("planning", f"planning:{index}", [problem], at)
        resolution = self._advance("resolution", f"resolution:{index}", [planning], at)
        return self._advance("action", f"action:{index}", [resolution], at)

    def _predicates(self):
        """Predicates the harness derives from observable state, never from truth."""
        return {f"selected_{self.model.path[site]}" for site in self.model.sites}

    def _export(self, label, at, sequence):
        exported = self.model.observations(capability_ids=self.capability_ids, window_s=self.period_s)
        batch = Record("AdapterObservationBatch", {
            "observations": exported, "watermark_s": at,
            "window": {"start_s": max(0.0, at - self.period_s), "end_s": at},
            "sequence": sequence, "completeness": 1 if exported else 0, "omitted_metrics": []})
        return self.boundary.ingest(f"ingest:{label}", batch, watermark_s=at)

    def execute(self):
        """Run every epoch, then close the run with a result and an assurance report."""
        last_action = None
        for index in range(self.epochs):
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


def closed_loop_environment(model, *, period_s, assembly=None):
    """A study whose action stage is bound to the finite world, with a Null arm beside it.

    The Null treatment and the closed-loop treatment differ in one binding, so a paired
    comparison between them attributes any difference to that stage rather than to the
    orchestration around it.
    """
    registry, study, scenario_set, scenario, caps = fixture_environment(assembly=assembly)
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
    data = {**data, "treatments": [*data["treatments"], {"treatment_id": "closed_loop", "bindings": bindings}]}
    return registry, Record("StudyManifest", data), scenario_set, scenario, caps
