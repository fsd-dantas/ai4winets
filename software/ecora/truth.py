"""The restricted, logged truth interface, and the telemetry Oracle that uses it.

An Oracle is a reference, not a cheat, and the difference is entirely in what it is allowed
to see and whether anyone can tell that it saw it. docs/ECoRA/stage-arms.md fixes the
initial regime as `oracle_state`: current simulator truth at the decision watermark, never
future arrivals, never future random draws, never an undisclosed disturbance schedule.

Three restrictions make that enforceable rather than promised.

Access is capability-scoped. A truth capability declares exactly which subject, service,
signal and unit it opens, and a read outside that scope is refused. Holding one truth
capability is not permission to read anything else, any more than it would be for an
ordinary observation.

Access is to the present only. The port refuses a read at any time other than the model's
current instant, so a provider cannot look ahead by asking for a later moment, and cannot
quietly reuse a stale value by asking for an earlier one.

Access is logged. Every read is recorded and returns a privileged source reference that
travels with whatever it produces, so an Oracle-derived value keeps its lineage through
every stage that touches it. A provider cannot shed the label by wrapping the value in an
otherwise ordinary record.

What the port exposes is current state. It holds no event calendar, no disturbance
schedule and no random stream, so there is nothing in it to read the future from.
"""

from functools import partial

from .contracts import Record, digest, require
from .registry import ProviderResult
from .schema import INPUT_TYPES, OUTPUT_TYPES

VERSION = "oracle-v1"

# The finite model's current-state projection, by the capability name that opens it.
PROJECTIONS = {
    "queue_occupancy": ("byte", lambda model, site: model.truth()["queue_bytes"][
        f"{site}/{model.truth()['selected_path'][site]}"]),
    "path_state": ("id", lambda model, site: model.truth()["selected_path"][site]),
    "pacing_profile": ("id", lambda model, site: model.truth()["pacing"][site]),
    "held_ami": ("count", lambda model, site: model.truth()["held_ami"][site]),
    # A per-leg quantity: the target names the leg, as it does for an ordinary probe.
    "path_probe": ("s", lambda model, target: model.probe(*target.split("/", 1))),
}


def _cohort_capability(port):
    """The one capability that opens the complete event record, if it was granted."""
    return next((identifier for identifier in port.granted()
                 if identifier.endswith(".cohort_record")), None)


def _declared(port, since):
    """The reads a provider made in this invocation, for it to declare to the boundary."""
    return sorted({entry["reference"] for entry in port.log[since:]})


class TruthPort:
    """Current model state, opened only through a declared truth capability and logged."""

    def __init__(self, model, capabilities):
        self.model = model
        self._capabilities = {c["capability_id"]: c for c in capabilities
                              if c["kind"] == "truth"}
        self.log = []

    def granted(self):
        return sorted(self._capabilities)

    def read(self, capability_id, at_s):
        """One current-state value, or a refusal. Never a future or a stale one."""
        capability = self._capabilities.get(capability_id)
        require(capability is not None,
                f"no truth capability grants {capability_id}")
        require(at_s == self.model.now,
                "truth is current state only; the port serves neither the future nor the past")
        name = capability["name"]
        require(name in PROJECTIONS, f"the truth projection does not carry {name}")
        unit, extract = PROJECTIONS[name]
        require(capability["unit"] == unit, f"{name} is declared in {unit}")
        value = extract(self.model, capability["target"])
        reference = f"truth:{name}:{capability['target']}:{at_s}"
        # Some quantities do not exist in some states: a leg with no service has no round
        # trip. Even an omniscient reader finds nothing there, and reports nothing rather
        # than a number, because the value is undefined and not merely unobserved.
        absent = None if value is not None else {
            "code": "undefined_in_model",
            "detail": f"{name} has no value for {capability['target']} in this state."}
        self.log.append({"capability_id": capability_id, "name": name,
                         "target": capability["target"], "at_s": at_s, "reference": reference})
        return {
            "observation_id": f"observation:truth:{capability['target']}:{name}:{at_s}",
            "subject": capability["target"], "service": capability["service"],
            "metric": name, "unit": unit, "value": value,
            "quality": "missing" if absent else "observed",
            "missing_reason": absent, "event_time_s": at_s, "available_at_s": at_s,
            "window": {"start_s": at_s, "end_s": at_s}, "source": "truth.port",
            "sampling_policy": "instantaneous", "valid_min": None, "valid_max": None,
            "assumptions": ["Privileged current-state read; not deployable evidence."],
            "evidence_kind": "simulator_truth", "capability_id": capability_id,
            "source_observation_ids": [], "formula": None,
            "privileged_source_refs": [reference]}

    def read_cohorts(self, capability_id, cohort_specs, at_s):
        """The complete event record, scored into the study's frozen cohorts.

        This is one read of one capability, not a way around the scalar projection. It is
        logged like any other, and it is current-state only for the same reason: a cohort
        whose window has not closed reports what has happened, not what will.
        """
        capability = self._capabilities.get(capability_id)
        require(capability is not None, f"no truth capability grants {capability_id}")
        require(at_s == self.model.now,
                "truth is current state only; the port serves neither the future nor the past")
        require(capability["name"] == "cohort_record",
                f"{capability_id} does not open the event record")
        reference = f"truth:cohort_record:{capability['target']}:{at_s}"
        self.log.append({"capability_id": capability_id, "name": "cohort_record",
                         "target": capability["target"], "at_s": at_s, "reference": reference})
        return self.model.cohorts(cohort_specs)

    def accounting(self):
        return {"regime": "oracle_state", "reads": len(self.log),
                "capabilities": self.granted(),
                "note": "privileged current state; not evidence any controller could obtain"}


class OracleTelemetryProvider:
    """Exact current values of the finite truth projection, with privileged lineage.

    This is a reference for measuring how much a contract-limited telemetry arm gives up,
    not a controller anyone could deploy. Every value it relays is marked as simulator
    truth and carries the reference of the read that produced it.
    """

    def __init__(self, port):
        self.port = port

    def invoke(self, inputs, prior_state, context):
        watermark = context.data["decision_watermark_s"]
        config = context.data["configuration"]
        before = len(self.port.log)
        observations = [self.port.read(capability_id, watermark)
                        for capability_id in config["reads"]]
        batch = Record("TelemetryBatch", {
            "observations": observations, "watermark_s": watermark,
            "window": {"start_s": watermark, "end_s": watermark},
            "sequence": config.get("sequence", 0),
            "completeness": 1 if observations else 0, "omitted_metrics": []})
        state = {"reads": prior_state.data["state"].get("reads", 0) + len(observations)}
        return ProviderResult((batch,), state,
                              {"organisation": "oracle_state",
                               "reads": len(self.port.log) - before,
                               "privileged_source_refs": _declared(self.port, before),
                               "port": self.port.accounting()})


class OracleDiagnosisProvider:
    """Exact current truth, read through the same rules and into the same label ontology.

    It shares the rule inventory and the inference with the Proposed arm, so the only
    difference between them is what each was given. That is what makes the gap between
    them readable as an information gap rather than as two implementations disagreeing.

    It diagnoses only what the model establishes. An unmodelled physical cause has no
    ground truth to read, so no Oracle here can supply one, and the gap it measures is
    bounded by what the world represents.
    """

    def __init__(self, port):
        self.port = port

    def invoke(self, inputs, prior_state, context):
        from .experts import _Inference, snapshot_from
        watermark = context.data["decision_watermark_s"]
        config = context.data["configuration"]
        before = len(self.port.log)
        truth = [self.port.read(capability_id, watermark) for capability_id in config["reads"]]
        observed, unknown = snapshot_from(truth)
        rules = config["rules"]
        inference = _Inference(rules, config.get("activation_budget", 1000))
        passes, changed = 0, True
        while changed:
            changed = False
            passes += 1
            for rule in rules:
                changed |= inference.consider(rule, observed, unknown)
        record = inference.record("oracle_state", passes)
        state = {"evaluations": prior_state.data["state"].get("evaluations", 0) + 1}
        return ProviderResult((record,), state,
                              {"organisation": "oracle_state", "reads": len(self.port.log) - before,
                               "activations": inference.activations, "passes": passes,
                               "privileged_source_refs": _declared(self.port, before),
                               "unknown_signals": sorted(unknown), "port": self.port.accounting()})


def oracle_diagnosis_binding(registry, port, capability_ids, configuration):
    """Register the diagnosis Oracle against a port and return its frozen binding."""
    require(configuration.get("rules"), "an Oracle diagnosis needs the shared rule inventory")
    for capability_id in configuration["reads"]:
        require(capability_id in port.granted(),
                f"the Oracle declares a read no truth capability grants: {capability_id}")
    spec = Record("ProviderSpec", {
        "stage_id": "diagnosis", "provider_id": "diagnosis.oracle_state",
        "provider_version": VERSION, "arm": "oracle",
        "input_types": list(INPUT_TYPES["diagnosis"]),
        "output_types": list(OUTPUT_TYPES["diagnosis"]), "state_schema_version": "1",
        "capability_ids": list(capability_ids), "direct_truth_access": True})
    if not registry.registered("diagnosis", spec.data["provider_id"], VERSION):
        registry.register(spec, partial(OracleDiagnosisProvider, port))
    return {k: v for k, v in spec.data.items() if k != "direct_truth_access"} | {
        "information_regime": "oracle_state", "allow_privileged_inputs": True,
        "configuration": configuration, "configuration_hash": digest(configuration)}


def truth_binding(registry, port, capability_ids, configuration):
    """Register the telemetry Oracle against a port and return its frozen binding."""
    require(configuration.get("reads"), "an Oracle must declare what truth it reads")
    for capability_id in configuration["reads"]:
        require(capability_id in port.granted(),
                f"the Oracle declares a read no truth capability grants: {capability_id}")
    spec = Record("ProviderSpec", {
        "stage_id": "telemetry", "provider_id": "telemetry.oracle_state",
        "provider_version": VERSION, "arm": "oracle",
        "input_types": list(INPUT_TYPES["telemetry"]),
        "output_types": list(OUTPUT_TYPES["telemetry"]), "state_schema_version": "1",
        "capability_ids": list(capability_ids), "direct_truth_access": True})
    if not registry.registered("telemetry", spec.data["provider_id"], VERSION):
        registry.register(spec, partial(OracleTelemetryProvider, port))
    return {k: v for k, v in spec.data.items() if k != "direct_truth_access"} | {
        "information_regime": "oracle_state", "allow_privileged_inputs": True,
        "configuration": configuration, "configuration_hash": digest(configuration)}


class OracleResultProvider:
    """Independent extraction from the complete simulator event record.

    The Proposed arm counts what the cohorts it was handed report. This one counts the
    events themselves, with exact identities and times, so the gap between them is what
    the extraction path loses rather than what the world did.

    It is an Oracle by information and not by procedure: given the same counts it would
    reach the same measurements, because it uses the same extraction the Proposed arm does.
    """

    def __init__(self, port):
        self.port = port

    def invoke(self, inputs, prior_state, context):
        from .assessment import cohort_measurements
        watermark = context.data["decision_watermark_s"]
        config = context.data["configuration"]
        before = len(self.port.log)
        capability = _cohort_capability(self.port)
        if capability is None:
            # An Oracle cell without the grant it needs is unsupported, and says so. It is
            # not quietly replaced by the Proposed arm wearing an Oracle's name.
            return ProviderResult((), {}, {"reference": "oracle_result"}, "rejected",
                                  {"code": "no_truth_capability",
                                   "detail": "No capability grants the complete event record."})
        cohorts = self.port.read_cohorts(capability, config["cohorts"], watermark)
        measurements, totals = cohort_measurements(cohorts)
        censored = [c["cohort_id"] for c in cohorts if c["censored"]]
        record = Record("ResultRecord", {
            "before_window": {"start_s": 0, "end_s": watermark},
            "after_window": {"start_s": watermark, "end_s": watermark},
            "cohorts": cohorts, "measurements": measurements, "action_ids": [],
            "uncertainty": ("Censored cohorts: " + ", ".join(censored)) if censored
            else "No cohort was censored in this extraction."})
        return ProviderResult((record,), {}, {
            "reference": "oracle_result", "cohorts": len(cohorts),
            "population": totals.get("generated", 0), "censored": censored,
            "reads": len(self.port.log) - before,
            "privileged_source_refs": _declared(self.port, before)})


class OracleAssuranceProvider:
    """Reference evaluation against full truth and the same frozen requirements.

    It does not trust the result it was handed. It re-derives the measurements from the
    event record and scores those, so a result stage that under-reported is visible as a
    difference between this arm and the Proposed one rather than inherited by both.

    What it may not do is score differently. The requirements and comparators are the
    study's, frozen in this binding exactly as they are in the Proposed arm's, because an
    Oracle that changed what passing means would be measuring a different question.
    """

    def __init__(self, port):
        self.port = port

    def invoke(self, inputs, prior_state, context):
        from .assessment import AssuranceProvider, cohort_measurements
        watermark = context.data["decision_watermark_s"]
        config = context.data["configuration"]
        scope = inputs[0].data["scope"] if inputs else None
        if scope is None:
            return ProviderResult((), {}, {"evaluator": "oracle_truth"}, "no_op",
                                  {"code": "no_result", "detail": "No result evidence reached the evaluator."})
        before = len(self.port.log)
        capability = _cohort_capability(self.port)
        if capability is None:
            return ProviderResult((), {}, {"evaluator": "oracle_truth"}, "rejected",
                                  {"code": "no_truth_capability",
                                   "detail": "No capability grants the complete event record."})
        cohorts = self.port.read_cohorts(capability, config["cohorts"], watermark)
        measurements, _ = cohort_measurements(cohorts)
        reference = Record("ResultRecord", {
            "before_window": {"start_s": 0, "end_s": watermark},
            "after_window": {"start_s": watermark, "end_s": watermark},
            "cohorts": cohorts, "measurements": measurements, "action_ids": [],
            "uncertainty": "Derived from the complete event record."})

        class _Reference:
            def __init__(self, payload, origin):
                self.data = dict(origin.data, payload=payload.to_dict())

        result = AssuranceProvider().invoke(
            [_Reference(reference, inputs[0])], prior_state, context)
        trace = dict(result.trace, evaluator="oracle_truth",
                     reads=len(self.port.log) - before,
                     privileged_source_refs=_declared(self.port, before))
        return ProviderResult(result.outputs, result.next_state, trace, result.status,
                              result.reason)


def oracle_assessment_binding(registry, port, capability_ids, configuration, stage):
    """Register the Oracle provider for an assessment stage and return its binding."""
    require(stage in ("result", "assurance"), f"no assessment Oracle is defined for {stage}")
    require(configuration.get("cohorts"),
            "an Oracle extraction must be given the frozen cohorts it counts")
    if stage == "assurance":
        require(configuration.get("requirements"),
                "an Oracle evaluator is scored against the study's frozen requirements")
    factory = OracleResultProvider if stage == "result" else OracleAssuranceProvider
    provider_id = f"{stage}.oracle_truth"
    spec = Record("ProviderSpec", {
        "stage_id": stage, "provider_id": provider_id, "provider_version": VERSION,
        "arm": "oracle", "input_types": list(INPUT_TYPES[stage]),
        "output_types": list(OUTPUT_TYPES[stage]), "state_schema_version": "1",
        "capability_ids": list(capability_ids), "direct_truth_access": True})
    if not registry.registered(stage, provider_id, VERSION):
        registry.register(spec, partial(factory, port))
    return {k: v for k, v in spec.data.items() if k != "direct_truth_access"} | {
        "information_regime": "oracle_state", "allow_privileged_inputs": True,
        "configuration": configuration, "configuration_hash": digest(configuration)}
