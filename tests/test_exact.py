import unittest

from ecora.contracts import ContractError, Record
from ecora.exact import ExactPlannerProvider, ExactResolutionProvider, exact_binding
from ecora.registry import Registry
from ecora.symbolic import predicate

ON_LTE = predicate("selected_path", "site-1", "lte")
ON_ALT = predicate("selected_path", "site-1", "alternative")
REACH_LTE = predicate("reachable", "site-1", "lte")
REACH_ALT = predicate("reachable", "site-1", "alternative")
PACE_NORMAL = predicate("pacing", "site-1", "normal")
PACE_RESTRICTED = predicate("pacing", "site-1", "restricted")

PLANNER = {"sites": ["site-1"], "costs": {"select_path": 2, "set_ami_pacing": 1},
           "agent_id": "agent:site-1:ami", "service": "ami", "validity_s": 1,
           "state_limit": 64}
ECO = {"validity_s": 1, "max_proposals": 8,
       "authority": {"select_path": "actuate.shared.path",
                     "set_ami_pacing": "actuate.ami.pacing"}}


class Message:
    def __init__(self, kind, payload):
        self.data = {"payload": Record(kind, payload).to_dict()}


class Snapshot:
    def __init__(self, state=None):
        self.data = {"state": state or {}}


class Context:
    def __init__(self, configuration, watermark=0.0):
        self.data = {"configuration": configuration, "decision_watermark_s": watermark}


def problem(goals, *, known=(ON_LTE, REACH_LTE, REACH_ALT, PACE_NORMAL), unknown=(),
            budget=10000, horizon=8):
    return Message("PlanningProblem", {
        "known_predicates": sorted(known), "unknown_predicates": sorted(unknown),
        "goals": list(goals), "operator_catalog_version": "v1",
        "action_costs": {"select_path": 2, "set_ami_pacing": 1},
        "expansion_budget": budget, "time_budget_s": 2, "memory_budget_bytes": 1024,
        "horizon_steps": horizon})


def proposal(proposal_id, *, service="ami", operator="select_path", arguments=None,
             preconditions=("observation:ami:0",), cost=2):
    step = {"operator": operator, "target": "site-1",
            "arguments": arguments or {"path": "alternative"},
            "preconditions": list(preconditions), "add_effects": [], "delete_effects": [],
            "cost": cost}
    return Message("PlanProposal", {
        "proposal_id": proposal_id, "agent_id": f"agent:site-1:{service}", "site_id": "site-1",
        "service": service, "steps": [step], "assumptions": [], "estimated_cost": cost,
        "valid_until_s": 1, "goal_status": "unmet", "certificate_ref": None})


def plan(goals, config=None, **changes):
    result = ExactPlannerProvider().invoke([problem(goals, **changes)], Snapshot(),
                                           Context(config or PLANNER))
    return result.outputs[0].data, result.trace, result.status


def resolve(proposals, config=None):
    result = ExactResolutionProvider().invoke(proposals, Snapshot(), Context(config or ECO))
    record = next(r for r in result.outputs if r.kind == "ResolutionRecord")
    commands = [r for r in result.outputs if r.kind == "ActionCommand"]
    return record.data, commands, result.trace, result.status


class ExactPlanningTests(unittest.TestCase):
    def test_an_optimal_plan_carries_the_certificate_it_was_checked_against(self):
        proposed, trace, status = plan([ON_ALT, PACE_RESTRICTED])
        self.assertEqual(status, "ok")
        self.assertTrue(trace["certified"])
        self.assertEqual(proposed["goal_status"], "achieved_in_model")
        self.assertEqual(proposed["estimated_cost"], trace["optimal_cost"])
        self.assertTrue(proposed["certificate_ref"].startswith("certificate:"))
        self.assertEqual(trace["states_enumerated"], 6)

    def test_an_unreachable_goal_is_uncertified_and_claims_nothing(self):
        proposed, trace, _ = plan([ON_ALT], known=(ON_LTE, REACH_LTE, PACE_NORMAL),
                                  unknown=(REACH_ALT,))
        self.assertFalse(trace["certified"])
        self.assertIsNone(proposed["certificate_ref"], "no certificate without an exact answer")
        self.assertEqual(proposed["goal_status"], "unknown")
        self.assertEqual([step["operator"] for step in proposed["steps"]], ["no_op"])

    def test_a_space_beyond_its_declared_bound_yields_no_certificate(self):
        proposed, trace, _ = plan([ON_ALT], config={**PLANNER, "state_limit": 2})
        self.assertFalse(trace["certified"])
        self.assertIn("space_exceeded", trace["reason"])
        self.assertIsNone(proposed["certificate_ref"])

    def test_an_exhausted_budget_does_not_become_an_optimality_claim(self):
        proposed, trace, _ = plan([ON_ALT, PACE_RESTRICTED], budget=1)
        self.assertFalse(trace["certified"])
        self.assertIsNone(proposed["certificate_ref"])
        self.assertEqual(proposed["goal_status"], "unknown")

    def test_it_reads_no_more_than_the_arm_it_references(self):
        """An exact reference is not a privileged one: same information, better answer."""
        binding = exact_binding(Registry(), ["observe.ami.queue"], PLANNER, "planning")
        self.assertEqual(binding["arm"], "oracle")
        self.assertEqual(binding["information_regime"], "contract_only")
        self.assertFalse(binding["allow_privileged_inputs"])


class ExactResolutionTests(unittest.TestCase):
    def test_it_admits_a_conflict_free_set_and_defers_the_rest(self):
        competing = [proposal("p:a"), proposal("p:b", arguments={"path": "lte"})]
        record, commands, trace, _ = resolve(competing)
        dispositions = sorted(d["disposition"] for d in record["decisions"])
        self.assertEqual(dispositions, ["admit", "defer"])
        self.assertEqual(len(commands), 1)
        self.assertGreater(trace["enumerated"], 1, "it actually enumerated subsets")

    def test_proposals_on_separate_resources_are_all_admitted(self):
        independent = [proposal("p:a"),
                       proposal("p:b", operator="set_ami_pacing",
                                arguments={"profile": "restricted"}, cost=1)]
        record, commands, _, _ = resolve(independent)
        self.assertEqual([d["disposition"] for d in record["decisions"]], ["admit", "admit"])
        self.assertEqual(len(commands), 2)

    def test_the_declared_objective_prefers_scada_then_ami_then_cheapness(self):
        contended = [proposal("p:ami", service="ami"), proposal("p:scada", service="scada")]
        record, _, _, _ = resolve(contended)
        admitted = [d["proposal_id"] for d in record["decisions"] if d["disposition"] == "admit"]
        self.assertEqual(admitted, ["p:scada"], "SCADA is preferred before AMI")

    def test_the_same_inputs_always_produce_the_same_allocation(self):
        competing = [proposal("p:a"), proposal("p:b", arguments={"path": "lte"})]
        first, _, _, _ = resolve(competing)
        second, _, _, _ = resolve(list(reversed(competing)))
        self.assertEqual(first["decisions"], second["decisions"])

    def test_more_proposals_than_the_bound_is_refused_not_approximated(self):
        many = [proposal(f"p:{index}") for index in range(9)]
        record, commands, trace, status = resolve(many, {**ECO, "max_proposals": 8})
        self.assertEqual(status, "rejected")
        self.assertEqual(commands, [])
        self.assertTrue(all(d["disposition"] == "defer" for d in record["decisions"]))

    def test_an_unknown_stage_has_no_exact_reference(self):
        with self.assertRaises(ContractError):
            exact_binding(Registry(), [], PLANNER, "telemetry")


if __name__ == "__main__":
    unittest.main()
