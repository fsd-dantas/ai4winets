"""Exact references at contract-limited information: certified planning and resolution.

These are Oracles in the sense stage-arms.md means by "a specified exact or privileged
reference with documented scope", and they are the exact kind rather than the privileged
one. They read nothing a Proposed arm could not read. What they add is not information but
optimality: an exhaustive answer to the problem they were handed.

That distinction is the whole point of keeping them out of truth.py. Proposed-minus-exact
measures how much a method gives up at fixed information, which is an algorithmic gap.
Contract-limited-minus-privileged measures what the observation contract costs, which is
an information gap. Reporting one as the other would answer a question nobody asked.

An exact reference that cannot finish says so. A solver that exhausts its budget returns
unknown with whatever bound it reached and no certificate, because a heuristic result
wearing an Oracle's name is how an unsupported claim of optimality gets into a study.
"""

from functools import partial
from itertools import combinations

from .contracts import Record, digest, require
from .planning import PlannerProvider, uniform_cost
from .registry import ProviderResult
from .schema import INPUT_TYPES, OUTPUT_TYPES
from .symbolic import catalog, certificate, validate_plan

VERSION = "exact-v1"


def _resources(steps):
    """What a plan would write. Two plans conflict when these intersect."""
    fluent = {"select_path": "selected_path", "set_ami_pacing": "pacing_profile",
              "defer_eligible_message": "release_at_s"}
    return {f"{step['target']}/{fluent[step['operator']]}"
            for step in steps if step["operator"] in fluent}


class ExactPlannerProvider(PlannerProvider):
    """Exhaustive shortest path over the bounded symbolic graph, with its certificate.

    The certificate is the enumerated optimal-cost table and the digest of the graph it
    was computed over. A plan is only called optimal when its cost matches that table, so
    the claim is checked against an exact answer rather than asserted by the search that
    produced it.
    """

    def __init__(self):
        super().__init__("uniform_cost")

    def invoke(self, inputs, prior_state, context):
        watermark = context.data["decision_watermark_s"]
        config = context.data["configuration"]
        problem = next((Record.from_dict(m.data["payload"]) for m in inputs
                        if Record.from_dict(m.data["payload"]).kind == "PlanningProblem"), None)
        if problem is None:
            return ProviderResult((), {}, {"reference": "exact_planning"}, "no_op",
                                  {"code": "no_problem", "detail": "No planning problem was supplied."})
        data = problem.data
        known = frozenset(data["known_predicates"])
        unknown = frozenset(data["unknown_predicates"])
        goals = list(data["goals"])
        operators = catalog(config["sites"], config["costs"])
        budget = data["expansion_budget"]
        try:
            table = certificate(known, unknown, operators, config.get("state_limit", 64))
        except Exception as exc:
            # The space outgrew its declared bound, so nothing here is certified.
            return self._uncertified(config, watermark, f"space_exceeded: {exc}")
        plan, cost, effort = uniform_cost(known, unknown, operators, goals, budget)
        if plan is None:
            return self._uncertified(config, watermark,
                                     "no plan within the declared budget"
                                     if effort.get("exhausted") else "no plan exists in this graph",
                                     bound=min(table["optimal_costs"].values(), default=None))
        achieved, final, why = validate_plan(known, unknown, operators, goals, plan)
        exact = table["optimal_costs"][" ".join(sorted(final))]
        require(abs(exact - cost) < 1e-9,
                "the enumerated table and the search disagree on the optimal cost")
        by_id = {operator.operator_id: operator for operator in operators}
        proposal = self._proposal(config, watermark, tuple(by_id[step] for step in plan), cost,
                                  "achieved_in_model" if achieved else "unmet",
                                  f"certificate:{table['graph_digest'][:16]}")
        state = {"plans": prior_state.data["state"].get("plans", 0) + 1}
        return ProviderResult((proposal,), state,
                              {"reference": "exact_planning", "certified": achieved,
                               "states_enumerated": table["states"], "optimal_cost": cost,
                               "graph_digest": table["graph_digest"], **effort})

    def _uncertified(self, config, watermark, why, bound=None):
        """No certificate, no optimality claim, and the reason on the record."""
        proposal = self._proposal(config, watermark, (), 0.0, "unknown", None)
        return ProviderResult((proposal,), {},
                              {"reference": "exact_planning", "certified": False,
                               "reason": why, "partial_bound": bound})


class ExactResolutionProvider:
    """Exact feasible allocation: enumerate subsets, keep the safe ones, rank them.

    The objective is the declared one, in its declared order: admit as many SCADA
    proposals as possible, then as many waiting AMI proposals, then spend as little
    mutation cost as possible, with a deterministic tie-break on proposal identity so the
    same inputs always produce the same allocation.

    It is exact over the proposals it was handed. That is not the same as optimal service,
    and nothing here claims it is: a better allocation of these proposals says nothing
    about the proposals nobody made.
    """

    def invoke(self, inputs, prior_state, context):
        watermark = context.data["decision_watermark_s"]
        config = context.data["configuration"]
        proposals = sorted((Record.from_dict(m.data["payload"]).data for m in inputs
                            if Record.from_dict(m.data["payload"]).kind == "PlanProposal"),
                           key=lambda p: p["proposal_id"])
        limit = config.get("max_proposals", 8)
        resolution_id = f"resolution:{VERSION}:{watermark}"
        if len(proposals) > limit:
            record = self._record(resolution_id, proposals, set(), [], "too_many_proposals",
                                  "Enumeration would exceed the declared bound.")
            return ProviderResult((record,), {}, {"reference": "exact_resolution",
                                                  "enumerated": 0}, "rejected",
                                  {"code": "enumeration_bound",
                                   "detail": "More proposals than the declared bound permits."})
        best, considered = (), 0
        for size in range(len(proposals), -1, -1):
            for subset in combinations(range(len(proposals)), size):
                considered += 1
                chosen = [proposals[i] for i in subset]
                if not self._conflict_free(chosen):
                    continue
                if self._score(chosen) > self._score([proposals[i] for i in best]):
                    best = subset
        admitted = {proposals[i]["proposal_id"] for i in best}
        commands = [c for c in (self._command(proposals[i], config, watermark, resolution_id)
                                for i in best) if c is not None]
        # A proposal whose command could not be issued was not really admitted.
        issued = {c.data["command_id"].split("command:", 1)[-1] for c in commands}
        admitted = {p for p in admitted if p in issued}
        record = self._record(resolution_id, proposals, admitted,
                              [c.data["command_id"] for c in commands], "exact_allocation",
                              "Admitted by exhaustive allocation under the declared objective.")
        return ProviderResult((record, *commands), {},
                              {"reference": "exact_resolution", "enumerated": considered,
                               "admitted": len(admitted)})

    @staticmethod
    def _conflict_free(chosen):
        seen = set()
        for proposal in chosen:
            touched = _resources(proposal["steps"])
            if touched & seen:
                return False
            seen |= touched
        return True

    @staticmethod
    def _score(chosen):
        """SCADA admitted, then AMI admitted, then cheaper. Ties break on identity."""
        scada = sum(1 for p in chosen if p["service"] == "scada")
        ami = sum(1 for p in chosen if p["service"] == "ami")
        cost = sum(p["estimated_cost"] for p in chosen)
        return (scada, ami, -cost, tuple(sorted(p["proposal_id"] for p in chosen)))

    @staticmethod
    def _record(resolution_id, proposals, admitted, command_ids, code, detail):
        return Record("ResolutionRecord", {
            "resolution_id": resolution_id,
            "proposal_ids": [p["proposal_id"] for p in proposals],
            "decisions": [{"proposal_id": p["proposal_id"],
                           "disposition": "admit" if p["proposal_id"] in admitted else "defer",
                           "reason": {"code": code, "detail": detail},
                           "conflicting_proposal_ids": sorted(
                               other["proposal_id"] for other in proposals
                               if other["proposal_id"] != p["proposal_id"]
                               and _resources(other["steps"]) & _resources(p["steps"]))}
                          for p in proposals],
            "claim_versions": {}, "command_ids": command_ids})

    @staticmethod
    def _command(proposal, config, watermark, resolution_id):
        scopes = {"select_path": ("site", "shared", "selected_path"),
                  "set_ami_pacing": ("ami_queue", "ami", "pacing_profile")}
        steps = proposal["steps"]
        step = steps[0] if steps else None
        if step is None or step["operator"] not in scopes:
            return None
        capability = config.get("authority", {}).get(step["operator"])
        if not capability or not step["preconditions"]:
            return None
        scope, service, fluent = scopes[step["operator"]]
        return Record("ActionCommand", {
            "command_id": f"command:{proposal['proposal_id']}", "operator": step["operator"],
            "catalog_version": "v1", "target": step["target"], "scope": scope, "service": service,
            "issuer": proposal["agent_id"], "arguments": step["arguments"], "argument_units": {},
            "read_set": [f"{step['target']}/{fluent}"], "write_set": [f"{step['target']}/{fluent}"],
            "resource_footprint": [f"{step['target']}/{service}"], "expected_state_version": 0,
            "precondition_evidence_ids": step["preconditions"], "resolution_id": resolution_id,
            "authority_capability_id": capability, "not_before_s": watermark,
            "expires_at_s": watermark + config.get("validity_s", 1),
            "idempotency_key": f"idempotency:{proposal['proposal_id']}"})


PROVIDERS = {"planning": ("planning.exact", ExactPlannerProvider),
             "resolution": ("resolution.exact", ExactResolutionProvider)}


def exact_binding(registry, capability_ids, configuration, stage):
    """Register an exact reference for one stage and return its frozen binding.

    The regime stays `contract_only`: an exact reference reads no more than the arm it is
    a reference for, and labelling it privileged would misattribute an algorithmic gap to
    an information one.
    """
    require(stage in PROVIDERS, f"no exact reference is defined for stage {stage}")
    provider_id, factory = PROVIDERS[stage]
    spec = Record("ProviderSpec", {
        "stage_id": stage, "provider_id": provider_id, "provider_version": VERSION,
        "arm": "oracle", "input_types": list(INPUT_TYPES[stage]),
        "output_types": list(OUTPUT_TYPES[stage]), "state_schema_version": "1",
        "capability_ids": list(capability_ids), "direct_truth_access": False})
    if not registry.registered(stage, provider_id, VERSION):
        registry.register(spec, factory)
    return {k: v for k, v in spec.data.items() if k != "direct_truth_access"} | {
        "information_regime": "contract_only", "allow_privileged_inputs": False,
        "configuration": configuration, "configuration_hash": digest(configuration)}
