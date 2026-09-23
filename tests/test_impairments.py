import copy
import unittest

from ecora.contracts import ContractError
from ecora.scenario import SCENARIOS, build_world, load, verify_impairments
from ecora.simulator import Ns3World, SimulatorRefusal
from ecora.truth import PROJECTIONS

try:
    from test_simulator_adapter import AVAILABLE
except ImportError:
    from tests.test_simulator_adapter import AVAILABLE

TRANSIENT = load(SCENARIOS / "s3-transient-primary.json")
# Commands a controller might send to impair or restore a leg. None is in the catalog.
IMPAIRING = [{"operator": operator, "target": "site-1", "expected_state_version": 0,
              "arguments": {"leg": "lte", **arguments}}
             for operator, arguments in (("radio_loss", {"extra_loss_db": 0}),
                                         ("cell_load", {"competing_ues": 0}),
                                         ("rate", {"rate_bps": 1000000}),
                                         ("restore", {}))]
# Uncontrolled S3: clean before the load, silent under it, clean again once restored.
WINDOWS = {"before": (0.0, 1.0), "impaired": (2.0, 5.0), "restored": (6.0, 11.0)}


def scada(world):
    world.advance_to(14.0)
    cohorts = world.cohorts([{"cohort_id": name, "service": "scada", "deadline_s": 0,
                              "generation_window": {"start_s": a, "end_s": b}}
                             for name, (a, b) in WINDOWS.items()])
    return {c["cohort_id"]: c["delivered_on_time"] / c["generated"] for c in cohorts}


class LedgerTests(unittest.TestCase):
    """Every scheduled impairment takes effect once, on time, leaving the declared condition."""

    def test_every_scenario_applies_its_schedule_in_the_finite_world(self):
        for path in sorted(SCENARIOS.glob("s*.json")):
            scenario = load(path)
            with self.subTest(scenario=path.stem):
                world = build_world(scenario).advance_to(8.0)
                ledger = verify_impairments(world.impairments(), scenario, 8.0)
                self.assertEqual(len(ledger), len(scenario.data["disturbances"]))

    def test_restoration_is_an_applied_impairment_and_keeps_the_other_condition(self):
        ledger = build_world(TRANSIENT).advance_to(8.0).impairments()
        restored = ledger[-1]
        self.assertEqual((restored["kind"], restored["applied_at_s"]), ("cell_load", 5.0))
        self.assertEqual(restored["condition"], {"extra_loss_db": 48, "competing_ues": 0})

    def test_only_what_is_due_is_applied(self):
        world = build_world(TRANSIENT).advance_to(3.0)
        self.assertEqual(len(verify_impairments(world.impairments(), TRANSIENT, 3.0)), 2)

    def test_a_ledger_that_disagrees_with_the_schedule_is_refused(self):
        ledger = build_world(TRANSIENT).advance_to(8.0).impairments()
        late = copy.deepcopy(ledger)
        late[2]["applied_at_s"] = 5.5
        missing = ledger[:2]
        unchanged = copy.deepcopy(ledger)
        unchanged[2]["condition"]["competing_ues"] = 5
        for name, bad in (("late", late), ("missing", missing), ("no effect", unchanged)):
            with self.subTest(case=name), self.assertRaises(ContractError):
                verify_impairments(bad, TRANSIENT, 8.0)

    def test_impairment_and_restoration_show_in_delivery_not_only_in_the_ledger(self):
        """Independent verification: the effect is measured through traffic."""
        ratios = scada(build_world(TRANSIENT))
        self.assertEqual(ratios["before"], 1.0)
        self.assertLess(ratios["impaired"], 0.5)
        self.assertEqual(ratios["restored"], 1.0)


class AuthorityTests(unittest.TestCase):
    """The hooks are the scenario's; no controller port can reach or read them."""

    def test_no_command_can_impair_or_restore_a_leg(self):
        world = build_world(TRANSIENT).advance_to(2.0)
        before = world.impairments()
        for command in IMPAIRING:
            with self.subTest(operator=command["operator"]):
                self.assertEqual(world.apply(command), (False, "unsupported_operator"))
        self.assertEqual(world.impairments(), before)

    def test_no_observation_or_truth_projection_exports_a_leg_condition(self):
        world = build_world(TRANSIENT).advance_to(2.0)
        conditions = ("extra_loss_db", "competing_ues", "rate_bps", "impairments")
        for metric in conditions:
            with self.subTest(metric=metric):
                self.assertEqual(world.observations(capability_ids={("site-1/lte", metric): "x"}), [])
                self.assertNotIn(metric, PROJECTIONS)
        self.assertFalse(set(world.truth()) & set(conditions))


@unittest.skipUnless(AVAILABLE, "no ns-3 simulator build is available on this host")
class SimulatedTests(unittest.TestCase):
    def test_the_simulator_applies_every_schedule_and_reads_back_what_the_finite_world_does(self):
        for path in sorted(SCENARIOS.glob("s*.json")):
            scenario = load(path)
            with self.subTest(scenario=path.stem), Ns3World.start(scenario) as world:
                world.advance_to(8.0)
                ledger = verify_impairments(world.impairments(), scenario, 8.0)
                finite = build_world(scenario).advance_to(8.0).impairments()
                self.assertEqual([e["condition"] for e in ledger], [e["condition"] for e in finite])

    def test_impairment_and_restoration_show_in_simulated_delivery(self):
        with Ns3World.start(TRANSIENT) as world:
            ratios = scada(world)
        self.assertGreaterEqual(ratios["before"], 0.9)
        self.assertLess(ratios["impaired"], 0.5)
        self.assertEqual(ratios["restored"], 1.0)

    def test_no_command_or_observation_reaches_a_leg_condition(self):
        with Ns3World.start(TRANSIENT) as world:
            world.advance_to(2.0)
            before = world.impairments()
            for command in IMPAIRING:
                with self.subTest(operator=command["operator"]):
                    self.assertEqual(world.apply(command), (False, "unsupported_operator"))
            for metric in ("extra_loss_db", "competing_ues", "impairments"):
                with self.subTest(metric=metric), self.assertRaises(SimulatorRefusal) as caught:
                    world.observations(capability_ids={("site-1", metric): "x"})
                self.assertEqual(caught.exception.code, "unsupported_signal")
            self.assertEqual(world.impairments(), before)


if __name__ == "__main__":
    unittest.main()
