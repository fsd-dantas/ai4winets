"""Synthetic contract fixtures. These are not research Null/Proposed/Oracle methods."""

from functools import partial

from .contracts import Record, digest
from .nulls import null_bindings
from .registry import ProviderResult, Registry
from .schema import INPUT_TYPES, OUTPUT_TYPES, STAGES


def reason(code="fixture", detail="Synthetic contract fixture."):
    return {"code": code, "detail": detail}


# The assembled stage inputs a study freezes, so that goal and cohort selection cannot
# vary with the arm under comparison. Synthetic; no calibrated budget or deadline.
ASSEMBLY = {
    "planning": {"goals": ["selected_path:site-1:alternative"],
                 "operator_catalog_version": "v1",
                 "action_costs": {"select_path": 2}, "expansion_budget": 100,
                 "time_budget_s": 2, "memory_budget_bytes": 1024, "horizon_steps": 8},
    "result": {"cohorts": [{"cohort_id": "cohort:ami", "service": "ami",
                            "generation_window": {"start_s": 0, "end_s": 0}, "deadline_s": 10}]},
}


# Declared policy settings for the Null arm. Fixed before measurement: a Null policy
# changed after seeing results invalidates the comparison it anchors.
NULL_CONFIGURATION = {
    "diagnosis": {"candidate_order": ["queue_pressure", "ami_age_risk"]},
    "planning": {"target": "site-1", "service": "ami", "agent_id": "agent:site-1:ami",
                 "arguments": {"path": "alternative"}, "validity_s": 1},
    "resolution": {"authority": {"select_path": "actuate.shared.path"}, "validity_s": 1},
    "assurance": {"requirement_ids": ["req:delivery"]},
}


def planning_problem(**changes):
    """A PlanningProblem conforming to ASSEMBLY; predicates stay run-derived."""
    data = {**ASSEMBLY["planning"], "known_predicates": ["selected_lte"],
            "unknown_predicates": ["reachable_alternative"]}
    return Record("PlanningProblem", {**data, **changes})


def result_input(**changes):
    """A ResultInput whose cohort identities, windows and deadlines match ASSEMBLY."""
    cohorts = [{**spec, "generated": 1, "delivered_on_time": 0, "delivered_late": 0,
                "lost": 0, "pending": 1, "duplicate_deliveries": 0, "censored": True}
               for spec in ASSEMBLY["result"]["cohorts"]]
    return Record("ResultInput", {"receipt_ids": [], "observation_ids": [],
                                  "cohorts": cohorts, **changes})


def observation(**changes):
    data = {"observation_id": "observation:ami:0", "subject": "site-1", "service": "ami",
            "metric": "queue_occupancy", "unit": "byte", "value": 512, "quality": "observed",
            "missing_reason": None, "event_time_s": 0, "available_at_s": 0,
            "window": {"start_s": 0, "end_s": 0}, "source": "synthetic.adapter",
            "sampling_policy": "fixture", "valid_min": 0, "valid_max": 65536,
            "assumptions": ["Synthetic fixture; no network model or calibration."],
            "evidence_kind": "measured", "capability_id": "observe.ami.queue",
            "source_observation_ids": [], "formula": None, "privileged_source_refs": []}
    return {**data, **changes}


def batch(kind="AdapterObservationBatch", observations=None, watermark=0):
    return Record(kind, {"observations": [observation()] if observations is None else observations,
                         "watermark_s": watermark, "window": {"start_s": 0, "end_s": watermark},
                         "sequence": 0, "completeness": 1, "omitted_metrics": []})


def command(**changes):
    d = {"command_id": "command:fixture", "operator": "set_ami_pacing", "catalog_version": "v1",
         "target": "site-1", "scope": "ami_queue", "service": "ami", "issuer": "agent:site-1:ami",
         "arguments": {"profile": "restricted"}, "argument_units": {}, "read_set": ["site-1/pacing_profile"],
         "write_set": ["site-1/pacing_profile"], "resource_footprint": ["site-1/ami"],
         "expected_state_version": 0, "precondition_evidence_ids": ["observation:ami:0"],
         "resolution_id": "resolution:fixture", "authority_capability_id": "actuate.ami.pacing",
         "not_before_s": 0, "expires_at_s": 1, "idempotency_key": "idempotency:fixture"}
    return Record("ActionCommand", {**d, **changes})


class FixtureProvider:
    """Emits schema-valid payloads at every stage so the seams are exercised.

    These carry no diagnostic, planning or measurement content. They establish that the
    contracts compose; they are not the research Null, Proposed and Oracle methods.
    """

    def __init__(self, stage):
        self.stage = stage

    def invoke(self, inputs, prior_state, context):
        watermark = context.data["decision_watermark_s"]
        payloads = [Record.from_dict(m.data["payload"]) for m in inputs]
        if self.stage == "telemetry":
            return ProviderResult((Record("TelemetryBatch", payloads[0].data),), {}, {"fixture": True})
        if self.stage == "diagnosis":
            label = context.data["configuration"]["label"]
            output = Record("DiagnosisRecord", {"hypotheses": [{"label": label, "support_ids": [],
                             "counterevidence_ids": [], "status": "unknown"}], "rule_trace": [],
                             "unresolved_conflicts": [], "confidence_semantics": "categorical"})
            return ProviderResult((output,), {"seen": prior_state.data["state"].get("seen", 0) + 1},
                                  {"fixture": True})
        if self.stage == "planning":
            proposal = Record("PlanProposal", {"proposal_id": "proposal:fixture", "agent_id": "agent:site-1:ami",
                              "site_id": "site-1", "service": "ami", "steps": [], "assumptions": [],
                              "estimated_cost": 0, "valid_until_s": watermark + 1,
                              "goal_status": "unknown", "certificate_ref": None})
            return ProviderResult((proposal,), {}, {"fixture": True})
        if self.stage == "resolution":
            proposal_ids = [p.data["proposal_id"] for p in payloads if p.kind == "PlanProposal"]
            issued = command(not_before_s=watermark, expires_at_s=watermark + 1) if proposal_ids else None
            record = Record("ResolutionRecord", {"resolution_id": "resolution:fixture",
                            "proposal_ids": proposal_ids,
                            "decisions": [{"proposal_id": pid, "disposition": "admit", "reason": reason(),
                                           "conflicting_proposal_ids": []} for pid in proposal_ids],
                            "claim_versions": {},
                            "command_ids": [issued.data["command_id"]] if issued else []})
            return ProviderResult((record, issued) if issued else (record,), {}, {"fixture": True})
        if self.stage == "action":
            receipts = tuple(Record("ActionReceipt", {"command_id": c.data["command_id"],
                             "idempotency_key": c.data["idempotency_key"], "disposition": "no_op",
                             "applied_at_s": None, "resulting_state": {}, "application_observation_ids": [],
                             "reason": reason("no_actuator", "No simulator is attached to this fixture.")})
                             for c in payloads if c.kind == "ActionCommand")
            return ProviderResult(receipts, {}, {"fixture": True}, "ok" if receipts else "no_op",
                                  None if receipts else reason())
        if self.stage == "result":
            return ProviderResult((Record("ResultRecord", {
                "before_window": {"start_s": 0, "end_s": watermark},
                "after_window": {"start_s": watermark, "end_s": watermark},
                "cohorts": payloads[0].data["cohorts"],
                "measurements": [{"metric": "within_age_delivery", "unit": "ratio", "value": None,
                                  "quality": "unknown", "numerator": 0, "denominator": 0}],
                "action_ids": [], "uncertainty": "Synthetic fixture; no simulated service."}),),
                {}, {"fixture": True})
        if self.stage == "assurance":
            scope = inputs[0].data["scope"]
            return ProviderResult((Record("AssuranceReport", {
                "study_id": scope["study_id"], "scenario_set_version": scope["scenario_set_version"],
                "scenario_set_hash": scope["scenario_set_hash"], "contributing_run_ids": [scope["run_id"]],
                "contributing_invocation_ids": [], "contributing_dataset_ids": [],
                "evaluator_version": "fixture-1",
                "claims": [{"requirement_id": "req:delivery", "verdict": "inconclusive", "evidence_refs": [],
                            "reason": reason("no_evidence", "No simulated service evidence exists.")}],
                "limitations": ["Contract fixture; establishes composition, not service behaviour."],
                "created_at_utc": "2026-09-21T00:00:00Z"}),), {}, {"fixture": True})
        return ProviderResult((), {}, {"fixture": True}, "no_op", reason())


def fixture_environment(*, allow_privileged=False, extra_capabilities=(), assembly=None,
                        scenario=None):
    """All identities, values and capabilities in this fixture are synthetic."""
    registry = Registry()
    cap = {"capability_id": "observe.ami.queue", "kind": "observe", "target": "site-1",
           "service": "ami", "name": "queue_occupancy", "unit": "byte", "evidence_refs": ["fixture:observation"]}
    path_cap = {"capability_id": "observe.shared.path", "kind": "observe", "target": "site-1",
                "service": "shared", "name": "path_state", "unit": "id", "evidence_refs": ["fixture:observation"]}
    actuator = {"capability_id": "actuate.ami.pacing", "kind": "actuate", "target": "site-1",
                "service": "ami", "name": "set_ami_pacing", "unit": None, "evidence_refs": ["fixture:actuation"]}
    path_actuator = {"capability_id": "actuate.shared.path", "kind": "actuate", "target": "site-1",
                     "service": "shared", "name": "select_path", "unit": None, "evidence_refs": ["fixture:actuation"]}
    probes = [{"capability_id": f"observe.probe.{leg}", "kind": "observe",
               "target": f"site-1/{leg}", "service": "shared", "name": "path_probe",
               "unit": "s", "evidence_refs": ["fixture:observation"]}
              for leg in ("lte", "alternative")]
    pacing_cap = {"capability_id": "observe.ami.pacing", "kind": "observe", "target": "site-1",
                  "service": "ami", "name": "pacing_profile", "unit": "id",
                  "evidence_refs": ["fixture:observation"]}
    # Truth capabilities are separate grants, so an Oracle's reach is declared and not
    # inferred from what it happens to be able to observe.
    truths = [{"capability_id": f"truth.{service}.{name}", "kind": "truth", "target": "site-1",
               "service": service, "name": name, "unit": unit,
               "evidence_refs": ["fixture:truth"]}
              for service, name, unit in (("ami", "queue_occupancy", "byte"),
                                          ("shared", "path_state", "id"),
                                          ("ami", "pacing_profile", "id"))]
    truths += [{"capability_id": f"truth.probe.{leg}", "kind": "truth",
                "target": f"site-1/{leg}", "service": "shared", "name": "path_probe",
                "unit": "s", "evidence_refs": ["fixture:truth"]}
               for leg in ("lte", "alternative")]
    granted = [cap, path_cap, pacing_cap, actuator, path_actuator, *probes, *truths]
    ordinary = [c["capability_id"] for c in granted if c["kind"] != "truth"]
    caps = Record("CapabilityManifest", {"adapter_id": "fixture", "adapter_version": "1", "model_version": "fixture-1",
                  "capabilities": [*granted, *extra_capabilities], "limitations": ["Fixture only; no enabled simulator."],
                  "timing_mode": "logical"})
    base = []
    for stage in STAGES:
        spec = Record("ProviderSpec", {"stage_id": stage, "provider_id": f"fixture.{stage}", "provider_version": "1",
                      "arm": "proposed", "input_types": list(INPUT_TYPES[stage]), "output_types": list(OUTPUT_TYPES[stage]),
                      "state_schema_version": "1", "capability_ids": ordinary,
                      "direct_truth_access": False})
        registry.register(spec, partial(FixtureProvider, stage))
        config = {"label": "fixture_a"} if stage == "diagnosis" else {}
        base.append({k: v for k, v in spec.data.items() if k != "direct_truth_access"} |
                    {"information_regime": "contract_only", "allow_privileged_inputs": allow_privileged,
                     "configuration": config, "configuration_hash": digest(config)})
    alternate_spec = Record("ProviderSpec", {**registry.resolve(base[1]).spec.data,
                             "provider_id": "fixture.diagnosis_alternate", "arm": "proposed"})
    registry.register(alternate_spec, partial(FixtureProvider, "diagnosis"))
    alternate = [dict(b) for b in base]
    alternate[1] = {**alternate[1], "provider_id": "fixture.diagnosis_alternate",
                    "configuration": {"label": "fixture_b"}, "configuration_hash": digest({"label": "fixture_b"})}
    nulls = null_bindings(registry, ordinary, NULL_CONFIGURATION)
    # The contract fixture is a scenario, not a runnable world: it declares one flow, so
    # ecora.scenario.build_world refuses it. A study over the finite model supplies its own.
    scenario = scenario or Record("ScenarioSpec", {
                      "scenario_id": "scenario:fixture", "revision": "1", "synthetic": True,
                      "topology": {"sites": ["site-1"], "initial_path": "lte", "initial_pacing": "normal",
                                   "legs": [{"leg_id": "alternative", "capacity_bps": 1000000,
                                             "delay_s": 0.01, "queue_limit_bytes": 65536},
                                            {"leg_id": "lte", "capacity_bps": 1000000,
                                             "delay_s": 0.01, "queue_limit_bytes": 65536}],
                                   "egress": {"leg_id": "egress", "capacity_bps": 256000,
                                              "delay_s": 0.001, "queue_limit_bytes": 65536}},
                      "flows": [{"flow_id": "flow:ami", "source": "site-1", "destination": "central-1",
                                 "service": "ami", "generation": {"period_s": 1}, "payload_bytes": 512,
                                 "deadline_s": 10, "max_deferral_s": 2}],
                      "requirements": [{"requirement_id": "req:delivery", "target": "site-1", "service": "ami",
                                        "metric": "within_age_delivery", "unit": "ratio", "comparator": "ge",
                                        "threshold": 0.99, "window_s": 10, "denominator": "generated readings",
                                        "missingness_limit": 0}], "initial_state": {}, "disturbances": [],
                      "parameter_set_hash": digest({"fixture": True}), "required_capability_ids": [cap["capability_id"]]})
    scenario_set = Record("ScenarioSetManifest", {"set_id": "set:fixture", "version": "1",
                          "members": [{"scenario_id": scenario.data["scenario_id"], "revision": "1",
                                       "content_hash": scenario.content_hash, "weight": 1}],
                          "benchmark_definition": "Synthetic contract fixture, not a research benchmark.", "parent_hash": None})
    study = Record("StudyManifest", {"study_id": "study:fixture", "frozen": True,
                   "scenario_set_version": "1", "scenario_set_hash": scenario_set.content_hash,
                   "treatments": [{"treatment_id": "reference", "bindings": base},
                                  {"treatment_id": "substitution", "bindings": alternate},
                                  {"treatment_id": "null_baseline", "bindings": nulls}],
                   "assembly": assembly or ASSEMBLY,
                   "capability_manifest_hash": caps.content_hash, "parameter_set_hash": scenario.data["parameter_set_hash"],
                   "analysis_version": "fixture-1", "scoring_version": "fixture-1", "seed_manifest": {"fixture": 0},
                   "compute_budget_s": 60, "storage_budget_bytes": 10485760, "access_policy_version": "v1"})
    return registry, study, scenario_set, scenario, caps


def payload_fixtures():
    """Valid payload examples with explicit unknown/non-pass outcomes where appropriate."""
    _, study, scenario_set, scenario, caps = fixture_environment()
    window = {"start_s": 0, "end_s": 1}
    cohort = {"cohort_id": "cohort:ami", "service": "ami", "generation_window": window, "generated": 2,
              "delivered_on_time": 1, "delivered_late": 0, "lost": 0, "pending": 1,
              "duplicate_deliveries": 1, "censored": True, "deadline_s": 10}
    examples = [study, scenario_set, scenario, caps, batch(), batch("TelemetryBatch"), command()]
    examples.extend(Record(kind, data) for kind, data in {
        "DiagnosisRecord": {"hypotheses": [], "rule_trace": [], "unresolved_conflicts": [], "confidence_semantics": "categorical"},
        "PlanningProblem": {"known_predicates": [], "unknown_predicates": ["reachable"], "goals": ["selected_alternative"],
                            "operator_catalog_version": "v1", "action_costs": {"select_path": 2},
                            "expansion_budget": 100, "time_budget_s": 2, "memory_budget_bytes": 1024, "horizon_steps": 8},
        "PlanProposal": {"proposal_id": "proposal:fixture", "agent_id": "agent:site-1:ami", "site_id": "site-1", "service": "ami",
                         "steps": [], "assumptions": [], "estimated_cost": 0, "valid_until_s": 1,
                         "goal_status": "unknown", "certificate_ref": None},
        "ResolutionRecord": {"resolution_id": "resolution:fixture", "proposal_ids": ["proposal:fixture"],
                             "decisions": [{"proposal_id": "proposal:fixture", "disposition": "defer", "reason": reason(),
                                            "conflicting_proposal_ids": []}], "claim_versions": {}, "command_ids": []},
        "ActionReceipt": {"command_id": "command:fixture", "idempotency_key": "idempotency:fixture", "disposition": "unknown",
                          "applied_at_s": None, "resulting_state": {}, "application_observation_ids": [], "reason": reason()},
        "ResultInput": {"receipt_ids": [], "observation_ids": [], "cohorts": [cohort]},
        "ResultRecord": {"before_window": window, "after_window": {"start_s": 1, "end_s": 2}, "cohorts": [cohort],
                         "measurements": [{"metric": "delivery", "unit": "ratio", "value": None, "quality": "unknown",
                                           "numerator": 1, "denominator": 2}], "action_ids": [], "uncertainty": "Censored fixture."},
        "AssuranceReport": {"study_id": study.data["study_id"], "scenario_set_version": "1", "scenario_set_hash": scenario_set.content_hash,
                            "contributing_run_ids": ["run:fixture"], "contributing_invocation_ids": [], "contributing_dataset_ids": [],
                            "evaluator_version": "fixture-1", "claims": [{"requirement_id": "req:delivery", "verdict": "inconclusive",
                                                                         "evidence_refs": [], "reason": reason()}],
                            "limitations": ["No simulated evidence."], "created_at_utc": "2026-09-21T00:00:00Z"},
        "BoundaryOutcome": {"status": "no_op", "reason": reason()},
        "Snapshot": {"state": {"counter": 0}, "privileged_source_refs": [], "state_schema_version": "1"},
        "ProviderContext": {"configuration": {}, "decision_watermark_s": 0, "random_state": {},
                            "information_regime": "contract_only", "privileged_source_refs": []},
    }.items())
    return tuple(examples)
