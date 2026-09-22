import unittest

from ecora.contracts import ContractError
from ecora.planning import astar, gps, planner_binding, uniform_cost
from ecora.registry import Registry
from ecora.symbolic import (Operator, catalog, certificate, enumerate_space, predicate,
                            successors, validate_plan)

SITES = ["site-1"]
COSTS = {"select_path": 2, "set_ami_pacing": 1}
OPERATORS = catalog(SITES, COSTS)

ON_LTE = predicate("selected_path", "site-1", "lte")
ON_ALT = predicate("selected_path", "site-1", "alternative")
REACH_LTE = predicate("reachable", "site-1", "lte")
REACH_ALT = predicate("reachable", "site-1", "alternative")
PACE_NORMAL = predicate("pacing", "site-1", "normal")
PACE_RESTRICTED = predicate("pacing", "site-1", "restricted")

INFORMED = frozenset({ON_LTE, REACH_LTE, REACH_ALT, PACE_NORMAL})
BLIND = frozenset({ON_LTE, REACH_LTE, PACE_NORMAL})
UNKNOWN_ALT = frozenset({REACH_ALT})


class SymbolicTests(unittest.TestCase):
    def test_an_operator_rewrites_state_as_strips_defines_it(self):
        switch = next(o for o in OPERATORS if o.operator_id == "select_path:site-1:alternative")
        following = switch.apply(INFORMED)
        self.assertIn(ON_ALT, following)
        self.assertNotIn(ON_LTE, following)
        # (S - delete) union add: nothing else moves.
        self.assertEqual(following - {ON_ALT}, INFORMED - {ON_LTE})

    def test_an_unknown_precondition_prohibits_the_edge(self):
        """Unknown reachability prevents path mutation; it does not become false."""
        switch = next(o for o in OPERATORS if o.operator_id == "select_path:site-1:alternative")
        self.assertTrue(switch.applicable(INFORMED, frozenset()))
        self.assertFalse(switch.applicable(BLIND, UNKNOWN_ALT))
        reached = {operator.operator_id for operator, _ in successors(BLIND, UNKNOWN_ALT, OPERATORS)}
        self.assertNotIn("select_path:site-1:alternative", reached)

    def test_effects_are_configuration_and_never_predicted_service(self):
        for operator in OPERATORS:
            for effect in operator.add | operator.delete:
                with self.subTest(operator=operator.operator_id, effect=effect):
                    self.assertTrue(effect.startswith(("selected_path:", "pacing:")),
                                    "an operator may not assert a service outcome")

    def test_a_state_preserving_edge_is_not_expanded(self):
        reached = {operator.operator_id for operator, _ in successors(INFORMED, frozenset(), OPERATORS)}
        self.assertNotIn("select_path:site-1:lte", reached)
        self.assertNotIn("set_ami_pacing:site-1:normal", reached)

    def test_the_validator_separates_executability_from_goal_achievement(self):
        plan = ("set_ami_pacing:site-1:restricted",)
        met, final, why = validate_plan(INFORMED, frozenset(), OPERATORS, [PACE_RESTRICTED], plan)
        self.assertTrue(met)
        self.assertIsNone(why)
        # Well formed, executable, and leaves a different goal unmet.
        met, _, why = validate_plan(INFORMED, frozenset(), OPERATORS, [ON_ALT], plan)
        self.assertFalse(met)
        self.assertIn("unmet goals", why)

    def test_the_validator_refuses_a_plan_it_cannot_replay(self):
        for plan in (("select_path:site-1:atlantis",), ("select_path:site-1:alternative",)):
            with self.subTest(plan=plan):
                met, _, why = validate_plan(BLIND, UNKNOWN_ALT, OPERATORS, [ON_ALT], plan)
                self.assertFalse(met)
                self.assertIsNotNone(why)


class PlannerTests(unittest.TestCase):
    def search(self, procedure, initial, unknown, goals, budget=10000):
        return procedure(initial, unknown, OPERATORS, goals, budget)

    def test_astar_with_a_zero_heuristic_matches_uniform_cost(self):
        """The declared property check: same graph, same costs, same optimal cost."""
        problems = [
            ([ON_ALT], INFORMED, frozenset()),
            ([PACE_RESTRICTED], INFORMED, frozenset()),
            ([ON_ALT, PACE_RESTRICTED], INFORMED, frozenset()),
            ([PACE_RESTRICTED], BLIND, UNKNOWN_ALT),
        ]
        for goals, initial, unknown in problems:
            with self.subTest(goals=goals):
                plan_u, cost_u, _ = self.search(uniform_cost, initial, unknown, goals)
                plan_a, cost_a, _ = self.search(astar, initial, unknown, goals)
                self.assertEqual(cost_u, cost_a)
                self.assertEqual(len(plan_u or ()), len(plan_a or ()))

    def test_the_optimal_cost_matches_the_enumerated_certificate(self):
        table = enumerate_space(INFORMED, frozenset(), OPERATORS, 64)
        plan, cost, _ = self.search(uniform_cost, INFORMED, frozenset(), [ON_ALT, PACE_RESTRICTED])
        met, final, _ = validate_plan(INFORMED, frozenset(), OPERATORS, [ON_ALT, PACE_RESTRICTED], plan)
        self.assertTrue(met)
        self.assertEqual(cost, table[final])
        self.assertEqual(cost, COSTS["select_path"] + COSTS["set_ami_pacing"])

    def test_every_planner_produces_a_plan_the_validator_accepts(self):
        goals = [ON_ALT, PACE_RESTRICTED]
        for name, procedure in (("uniform_cost", uniform_cost), ("astar", astar), ("gps", gps)):
            with self.subTest(search=name):
                plan, _, _ = self.search(procedure, INFORMED, frozenset(), goals)
                self.assertIsNotNone(plan)
                met, _, why = validate_plan(INFORMED, frozenset(), OPERATORS, goals, plan)
                self.assertTrue(met, why)

    def test_no_planner_switches_onto_a_leg_it_cannot_reach(self):
        for name, procedure in (("uniform_cost", uniform_cost), ("astar", astar), ("gps", gps)):
            with self.subTest(search=name):
                plan, cost, _ = self.search(procedure, BLIND, UNKNOWN_ALT, [ON_ALT])
                self.assertIsNone(plan, "an unknown precondition must not be planned through")

    def test_a_bounded_gps_failure_is_not_a_proof_of_infeasibility(self):
        """Goals that undo one another: GPS fails, and says only that it found nothing."""
        seesaw = (
            Operator("left", "set_ami_pacing", "site-1", (("profile", "a"),),
                     frozenset(), frozenset({"x"}), frozenset({"y"}), 1),
            Operator("right", "set_ami_pacing", "site-1", (("profile", "b"),),
                     frozenset(), frozenset({"y"}), frozenset({"x"}), 1),
        )
        plan, cost, effort = gps(frozenset(), frozenset(), seesaw, ["x", "y"], 100)
        self.assertIsNone(plan)
        self.assertFalse(effort["exhausted"], "it terminated by policy, not by budget")
        self.assertGreater(effort["differences"], 0)
        # Whatever it tried, the validator would have caught an unmet goal anyway.
        met, _, why = validate_plan(frozenset(), frozenset(), seesaw, ["x", "y"], ("left",))
        self.assertFalse(met)
        self.assertIn("unmet goals", why)

    def test_an_exhausted_budget_is_reported_rather_than_truncated(self):
        for name, procedure in (("uniform_cost", uniform_cost), ("astar", astar)):
            with self.subTest(search=name):
                plan, cost, effort = self.search(procedure, INFORMED, frozenset(),
                                                 [ON_ALT, PACE_RESTRICTED], budget=1)
                self.assertIsNone(plan)
                self.assertTrue(effort["exhausted"])

    def test_this_domain_cannot_discriminate_planners_on_cost(self):
        """A property of the v1 configuration domain, recorded rather than worked around.

        The reachable configuration space is six states and every goal is one operator
        away, so uniform cost, A* and GPS all return the optimal cost on every problem in
        it. Planning headroom against an exact reference is therefore zero here by
        construction and not by measurement, and a factorial that varied the planning
        stage over this domain would be varying something that cannot differ.

        The design already anticipates this: S8 is a separate planner microbenchmark over
        interacting configuration goals, and that is where the planning factor can
        actually discriminate. This test exists so the limitation stays visible.
        """
        problems = [[ON_ALT], [PACE_RESTRICTED], [ON_ALT, PACE_RESTRICTED],
                    [predicate("pacing", "site-1", "minimum")]]
        self.assertEqual(len(enumerate_space(INFORMED, frozenset(), OPERATORS, 64)), 6)
        for goals in problems:
            with self.subTest(goals=goals):
                costs = {name: self.search(procedure, INFORMED, frozenset(), goals)[1]
                         for name, procedure in (("uniform_cost", uniform_cost),
                                                 ("astar", astar), ("gps", gps))}
                self.assertEqual(len(set(costs.values())), 1, f"costs differ: {costs}")
        # They do differ in effort, which is what remains measurable on this domain.
        _, _, direct = self.search(gps, INFORMED, frozenset(), [ON_ALT, PACE_RESTRICTED])
        _, _, exhaustive = self.search(uniform_cost, INFORMED, frozenset(),
                                       [ON_ALT, PACE_RESTRICTED])
        self.assertLess(direct["expansions"], exhaustive["expansions"])

    def test_a_planner_binding_is_checked_before_it_is_bound(self):
        with self.assertRaises(ContractError):
            planner_binding(Registry(), [], {"sites": SITES, "costs": COSTS}, search="telepathy")
        with self.assertRaises(ContractError):
            planner_binding(Registry(), [], {"sites": [], "costs": COSTS})
        with self.assertRaises(ContractError):
            planner_binding(Registry(), [], {"sites": SITES, "costs": {"select_path": -1,
                                                                       "set_ami_pacing": 1}})

    def test_the_certificate_records_the_space_it_certifies(self):
        table = certificate(INFORMED, frozenset(), OPERATORS, 64)
        self.assertGreater(table["states"], 1)
        self.assertEqual(len(table["graph_digest"]), 64)
        # It bounds a symbolic space, and refuses to grow past its declared limit.
        with self.assertRaises(ContractError):
            certificate(INFORMED, frozenset(), OPERATORS, 2)


if __name__ == "__main__":
    unittest.main()
