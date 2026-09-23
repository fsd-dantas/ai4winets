"""Null stage providers: explicit trivial policies preserving schema, safety and authority.

The policies are specified in docs/ECoRA/stage-arms.md. A Null arm is a declared
experimental baseline, not scaffolding and not an absent provider: it answers whether the
Proposed behaviour adds value over a trivial policy. Every Null emits a valid typed
output, including explicit unknowns, abstentions, no-ops and inconclusive verdicts.

Each policy is fixed and versioned. Changing one after seeing results invalidates the
comparison it anchors, so a variant belongs to a new provider version.
"""

from functools import partial

from .contracts import observed_version, Record, digest
from .registry import ProviderResult
from .schema import INPUT_TYPES, OPERATORS, OUTPUT_TYPES, STAGES

VERSION = "null-v1"

# Operator to (command scope, service, owned mutable field) for the operators a Null
# resolver may issue. An operator absent here is not feasible for this policy.
_SCOPES = {"select_path": ("site", "shared", "selected_path"),
           "set_ami_pacing": ("ami_queue", "ami", "pacing_profile")}


def _reason(code, detail):
    return {"code": code, "detail": detail}


class NullProvider:
    """One trivial policy per stage, selected by stage_id at construction."""

    def __init__(self, stage):
        self.stage = stage

    def invoke(self, inputs, prior_state, context):
        watermark = context.data["decision_watermark_s"]
        config = context.data["configuration"]
        payloads = [Record.from_dict(message.data["payload"]) for message in inputs]
        return getattr(self, f"_{self.stage}")(payloads, config, watermark, inputs)

    def _telemetry(self, payloads, config, watermark, inputs):
        """Empty dynamic observations with explicit unknowns, watermark and completeness."""
        offered = sorted({observation["metric"] for payload in payloads
                          if payload.kind == "AdapterObservationBatch"
                          for observation in payload.data["observations"]})
        batch = Record("TelemetryBatch", {
            "observations": [], "watermark_s": watermark,
            "window": {"start_s": watermark, "end_s": watermark}, "sequence": 0,
            "completeness": 0, "omitted_metrics": offered})
        return ProviderResult((batch,), {}, {"policy": "omit_all", "omitted": len(offered)})

    def _diagnosis(self, payloads, config, watermark, inputs):
        """First candidate in a fixed declared ordering; abstain if none is declared."""
        order = config.get("candidate_order", [])
        hypotheses = [{"label": order[0], "support_ids": [], "counterevidence_ids": [],
                       "status": "unknown"}] if order else []
        trace = [{"policy": "first_candidate", "ordering": order,
                  "selected": order[0] if order else None,
                  "note": "Unvalidated guess; no evidence was examined."}]
        record = Record("DiagnosisRecord", {
            "hypotheses": hypotheses, "rule_trace": trace, "unresolved_conflicts": [],
            "confidence_semantics": "categorical"})
        return ProviderResult((record,), {}, {"policy": "first_candidate", "abstained": not order})

    def _planning(self, payloads, config, watermark, inputs):
        """First feasible catalog action as a one-step plan; explicit no-op if none."""
        problem = next((p for p in payloads if p.kind == "PlanningProblem"), None)
        catalog = [op for op in sorted(problem.data["action_costs"])
                   if op in OPERATORS and op != "no_op"] if problem else []
        target = config.get("target", "unassigned")
        if catalog:
            operator = catalog[0]
            step = {"operator": operator, "target": target,
                    "arguments": config.get("arguments", {}),
                    "preconditions": problem.data["known_predicates"],
                    "add_effects": [], "delete_effects": [],
                    "cost": problem.data["action_costs"][operator]}
        else:
            step = {"operator": "no_op", "target": target, "arguments": {},
                    "preconditions": [], "add_effects": [], "delete_effects": [], "cost": 0}
        proposal = Record("PlanProposal", {
            "proposal_id": f"proposal:{VERSION}:{target}:{watermark}",
            "agent_id": config.get("agent_id", "agent:null"), "site_id": target,
            "service": config.get("service", "ami"), "steps": [step], "assumptions": [],
            "estimated_cost": step["cost"], "valid_until_s": watermark + config.get("validity_s", 1),
            # No search was performed, so no goal may be claimed achieved.
            "goal_status": "unmet", "certificate_ref": None,
            "state_versions": dict(problem.data.get("state_versions", {})) if problem else {}})
        return ProviderResult((proposal,), {}, {"policy": "first_feasible", "operator": step["operator"]})

    def _command(self, proposal, config, watermark, resolution_id):
        """Build the admitted proposal's command, or None when the policy cannot act."""
        steps = proposal.data["steps"]
        step = steps[0] if steps else None
        if step is None or step["operator"] not in _SCOPES:
            return None
        capability = config.get("authority", {}).get(step["operator"])
        # A mutation needs declared authority and precondition evidence. A Null telemetry
        # arm supplies neither, so an all-Null pipeline cannot act; that is the baseline.
        if not capability or not step["preconditions"]:
            return None
        scope, service, field = _SCOPES[step["operator"]]
        # The version the controller observed; without one there is nothing to check a
        # stale write against, so no command is written.
        version = observed_version(proposal.data, step["target"], step["operator"])
        if version is None:
            return None
        return Record("ActionCommand", {
            "command_id": f"command:{proposal.data['proposal_id']}", "operator": step["operator"],
            "catalog_version": "v1", "target": step["target"], "scope": scope, "service": service,
            "issuer": proposal.data["agent_id"], "arguments": step["arguments"],
            "argument_units": {}, "read_set": [f'{step["target"]}/{field}'],
            "write_set": [f'{step["target"]}/{field}'],
            "resource_footprint": [f'{step["target"]}/{service}'], "expected_state_version": version,
            "precondition_evidence_ids": step["preconditions"], "resolution_id": resolution_id,
            "authority_capability_id": capability, "not_before_s": watermark,
            "expires_at_s": watermark + config.get("validity_s", 1),
            "idempotency_key": f"idempotency:{proposal.data['proposal_id']}"})

    def _resolution(self, payloads, config, watermark, inputs):
        """First feasible proposal in a fixed order; defer the rest."""
        proposals = sorted((p for p in payloads if p.kind == "PlanProposal"),
                           key=lambda p: p.data["proposal_id"])
        resolution_id = f"resolution:{VERSION}:{watermark}"
        command, admitted = None, None
        for proposal in proposals:
            command = self._command(proposal, config, watermark, resolution_id)
            if command is not None:
                admitted = proposal.data["proposal_id"]
                break
        decisions = [{"proposal_id": p.data["proposal_id"],
                      "disposition": "admit" if p.data["proposal_id"] == admitted else "defer",
                      "reason": _reason("first_feasible", "Admitted the first feasible proposal.")
                      if p.data["proposal_id"] == admitted else
                      _reason("deferred", "Not first feasible under the fixed Null ordering."),
                      "conflicting_proposal_ids": []} for p in proposals]
        record = Record("ResolutionRecord", {
            "resolution_id": resolution_id, "proposal_ids": [p.data["proposal_id"] for p in proposals],
            "decisions": decisions, "claim_versions": {},
            "command_ids": [command.data["command_id"]] if command else []})
        outputs = (record, command) if command else (record,)
        return ProviderResult(outputs, {}, {"policy": "first_feasible", "admitted": admitted})

    def _action(self, payloads, config, watermark, inputs):
        """Suppress mutation and emit a suppressed receipt."""
        receipts = tuple(Record("ActionReceipt", {
            "command_id": command.data["command_id"],
            "idempotency_key": command.data["idempotency_key"], "disposition": "suppressed",
            "applied_at_s": None, "resulting_state": {}, "application_observation_ids": [],
            "reason": _reason("null_arm", "The Null action arm suppresses every mutation.")})
            for command in payloads if command.kind == "ActionCommand")
        if not receipts:
            return ProviderResult((), {}, {"policy": "suppress"}, "no_op",
                                  _reason("no_command", "No admitted command reached the actuator."))
        return ProviderResult(receipts, {}, {"policy": "suppress", "suppressed": len(receipts)})

    def _result(self, payloads, config, watermark, inputs):
        """Receipt-only summary; service outcomes are left unknown."""
        supplied = next((p for p in payloads if p.kind == "ResultInput"), None)
        if supplied is None:
            return ProviderResult((), {}, {"policy": "receipt_only"}, "no_op",
                                  _reason("no_input", "No assembled cohort specification was supplied."))
        record = Record("ResultRecord", {
            "before_window": {"start_s": 0, "end_s": watermark},
            "after_window": {"start_s": watermark, "end_s": watermark},
            "cohorts": supplied.data["cohorts"], "measurements": [],
            "action_ids": supplied.data["receipt_ids"],
            "uncertainty": "Null result arm: receipts only, no service outcome extracted."})
        return ProviderResult((record,), {}, {"policy": "receipt_only"})

    def _assurance(self, payloads, config, watermark, inputs):
        """Explicit inconclusive claims with an inventory of the evidence it was given."""
        if not inputs:
            return ProviderResult((), {}, {"policy": "inconclusive"}, "no_op",
                                  _reason("no_evidence", "No result evidence reached the evaluator."))
        scope = inputs[0].data["scope"]
        report = Record("AssuranceReport", {
            "study_id": scope["study_id"], "scenario_set_version": scope["scenario_set_version"],
            "scenario_set_hash": scope["scenario_set_hash"], "contributing_run_ids": [scope["run_id"]],
            "contributing_invocation_ids": sorted({m.data["stage_invocation_id"] for m in inputs}),
            "contributing_dataset_ids": sorted({m.data["output_dataset_id"] for m in inputs}),
            "evaluator_version": VERSION,
            "claims": [{"requirement_id": requirement, "verdict": "inconclusive", "evidence_refs": [],
                        "reason": _reason("null_arm", "The Null assurance arm evaluates no requirement.")}
                       for requirement in config.get("requirement_ids", [])],
            "limitations": ["Null assurance arm; no requirement was evaluated against evidence."],
            "created_at_utc": config.get("created_at_utc", "2026-09-21T00:00:00Z")})
        return ProviderResult((report,), {}, {"policy": "inconclusive"})


def null_bindings(registry, capability_ids, configurations):
    """Register a Null provider per stage and return its frozen treatment bindings."""
    bindings = []
    for stage in STAGES:
        spec = Record("ProviderSpec", {
            "stage_id": stage, "provider_id": f"null.{stage}", "provider_version": VERSION,
            "arm": "null", "input_types": list(INPUT_TYPES[stage]),
            "output_types": list(OUTPUT_TYPES[stage]), "state_schema_version": "1",
            "capability_ids": list(capability_ids), "direct_truth_access": False})
        # A Null policy is registered once; a second treatment differs by configuration,
        # never by a second registration of the same provider version.
        if not registry.registered(stage, spec.data["provider_id"], VERSION):
            registry.register(spec, partial(NullProvider, stage))
        configuration = configurations.get(stage, {})
        bindings.append({k: v for k, v in spec.data.items() if k != "direct_truth_access"} |
                        {"information_regime": "contract_only", "allow_privileged_inputs": False,
                         "configuration": configuration, "configuration_hash": digest(configuration)})
    return bindings
