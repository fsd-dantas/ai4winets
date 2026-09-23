import json
import unittest
from pathlib import Path

from ecora.contracts import ContractError, Record
from ecora.fixtures import fixture_environment
from ecora.model import FiniteModel, Link
from ecora.scenario import (SCENARIOS, build_world, catalogue, describe_world, load,
                            verify_world)

ROOT = Path(__file__).resolve().parents[1]


def spec(**changes):
    data = json.loads((SCENARIOS / "s0-nominal.json").read_text(encoding="utf-8"))
    return Record("ScenarioSpec", {**data, **changes})


def topology(**changes):
    data = json.loads((SCENARIOS / "s0-nominal.json").read_text(encoding="utf-8"))
    return spec(topology={**data["topology"], **changes})


def delivered(world, horizon=8.0):
    world.advance_to(horizon)
    return len(world.delivered), sum(1 for _, _, on_time in world.delivered if not on_time)


class BuildingTests(unittest.TestCase):
    def test_the_world_comes_from_the_scenario_and_not_from_code(self):
        data = json.loads((SCENARIOS / "s0-nominal.json").read_text(encoding="utf-8"))
        # The site end of a transaction is its destination; of a reading, its source. The
        # LTE leg positions every site, so moving the site moves its position too.
        legs = [{**leg, "radio": {**leg["radio"], "site_positions_m": {"site-a": [100, 0, 0]}}}
                if leg["kind"] == "lte" else leg for leg in data["topology"]["legs"]]
        moved = Record("ScenarioSpec", {
            **data,
            "topology": {**data["topology"], "sites": ["site-a"], "legs": legs,
                         "initial_path": "alternative", "initial_pacing": "restricted"},
            "flows": [{**flow, "destination": "site-a"} if flow["pattern"] == "request_response"
                      else {**flow, "source": "site-a"} for flow in data["flows"]]})
        world = build_world(moved)
        self.assertEqual(world.sites, ("site-a",))
        self.assertEqual(world.path["site-a"], "alternative")
        self.assertEqual(world.pacing["site-a"], "restricted")

    def test_changing_a_scenario_changes_behaviour_with_no_code_change(self):
        """The point of the loader: a different declared world runs differently."""
        nominal, _ = delivered(build_world(spec()))
        silent, _ = delivered(build_world(load(SCENARIOS / "s2-silent-primary.json")))
        self.assertLess(silent, nominal, "a silent serving leg must deliver less")
        _, late = delivered(build_world(load(SCENARIOS / "s1-degraded-primary.json")))
        self.assertGreater(late, 0, "a degraded serving leg must put traffic past its deadline")

    def test_every_published_scenario_builds_and_matches_what_it_declares(self):
        found = catalogue(SCENARIOS)
        self.assertGreaterEqual(len(found), 2)
        for scenario_id, scenario in found.items():
            with self.subTest(scenario=scenario_id):
                verify_world(build_world(scenario), scenario)

    def test_a_scenario_the_finite_world_cannot_build_is_refused(self):
        """The contract fixture is a valid scenario and not a runnable world."""
        _, _, _, fixture, _ = fixture_environment()
        with self.assertRaises(ContractError):
            build_world(fixture)
        with self.assertRaises(ContractError):
            build_world(topology(legs=[{"leg_id": "lte", "capacity_bps": 1000,
                                        "delay_s": 0.01, "queue_limit_bytes": 1024},
                                       {"leg_id": "spare", "capacity_bps": 1000,
                                        "delay_s": 0.01, "queue_limit_bytes": 1024}],
                                 initial_path="lte"))
        with self.assertRaises(ContractError):
            build_world(topology(initial_pacing="unhurried"))

    def test_a_scenario_that_names_what_it_does_not_declare_is_refused(self):
        with self.assertRaises(ContractError):
            topology(initial_path="microwave")
        with self.assertRaises(ContractError):
            spec(disturbances=[{"at_s": 1.0, "site": "site-1", "leg": "microwave",
                                "rate_bps": 0}])
        with self.assertRaises(ContractError):
            spec(disturbances=[{"at_s": 1.0, "site": "site-9", "leg": "lte", "rate_bps": 0}])


class DescriptionTests(unittest.TestCase):
    def test_a_scenario_describes_the_world_it_built(self):
        """Round trip: the description of a world built from a scenario is that scenario."""
        for scenario_id, scenario in catalogue(SCENARIOS).items():
            with self.subTest(scenario=scenario_id):
                data = scenario.data
                derived = describe_world(
                    build_world(scenario), scenario_id=scenario_id, revision=data["revision"],
                    requirements=data["requirements"], initial_state=data["initial_state"],
                    required_capability_ids=data["required_capability_ids"],
                    parameter_set_hash=data["parameter_set_hash"])
                self.assertEqual(derived.content_hash, scenario.content_hash)

    def test_a_described_world_carries_the_disturbances_it_will_apply(self):
        scenario = load(SCENARIOS / "s3-transient-primary.json")
        derived = describe_world(build_world(scenario))
        self.assertEqual(derived.data["disturbances"], scenario.data["disturbances"])


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.scenario = spec()

    def world(self, **changes):
        arguments = {"sites": ["site-1"],
                     "links": {"lte": Link("lte", 1000000, 0.010, 65536),
                               "alternative": Link("alternative", 1000000, 0.010, 65536)},
                     "egress": Link("egress", 256000, 0.001, 65536),
                     "scada_period_s": 0.1, "ami_period_s": 1.0, "scada_bytes": 512,
                     "ami_bytes": 512, "scada_deadline_s": 0.25, "ami_deadline_s": 10.0,
                     "scada_request_bytes": 128, "scada_processing_delay_s": 0.001,
                     }
        # The LTE interpretation is the scenario's own, whatever it was calibrated to, so a
        # recalibration does not turn this hand-built world into a mismatch.
        lte = next(leg for leg in self.scenario.data["topology"]["legs"] if leg["kind"] == "lte")
        arguments["links"]["lte"] = Link("lte", lte["logical"]["capacity_bps"],
                                         lte["logical"]["delay_s"], lte["queue_limit_bytes"])
        arguments["rate_tables"] = {"lte": [(r["extra_loss_db"], r["competing_ues"], r["capacity_bps"])
                                            for r in lte["logical"]["rate_table"]]}
        return FiniteModel(**{**arguments, **changes})

    def test_a_matching_world_passes_and_is_returned(self):
        world = self.world()
        self.assertIs(verify_world(world, self.scenario), world)

    def test_a_world_that_is_not_the_scenario_is_refused_field_by_field(self):
        for changes, named in (({"ami_period_s": 2.0}, "periods"),
                               ({"scada_bytes": 1024}, "sizes"),
                               ({"scada_deadline_s": 0.5}, "deadlines"),
                               ({"sites": ["site-1", "site-2"]}, "sites"),
                               ({"egress": Link("egress", 44000, 0.001, 65536)}, "egress")):
            with self.subTest(field=named):
                with self.assertRaises(ContractError) as refused:
                    verify_world(self.world(**changes), self.scenario)
                self.assertIn(named, str(refused.exception))

    def test_a_leg_the_scenario_did_not_declare_is_refused(self):
        legs = {"lte": Link("lte", 500000, 0.010, 65536),
                "alternative": Link("alternative", 1000000, 0.010, 65536)}
        with self.assertRaises(ContractError):
            verify_world(self.world(links=legs), self.scenario)


if __name__ == "__main__":
    unittest.main()
