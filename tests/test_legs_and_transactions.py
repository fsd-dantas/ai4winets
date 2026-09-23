import json
import unittest

from ecora.contracts import ContractError, Record
from ecora.model import FiniteModel, Link
from ecora.scenario import SCENARIOS, build_world, load

NOMINAL = json.loads((SCENARIOS / "s0-nominal.json").read_text(encoding="utf-8"))


def with_disturbance(entry):
    return {**NOMINAL, "disturbances": [entry]}


def world(**changes):
    settings = {"sites": ["site-1"],
                "links": {"lte": Link("lte", 1000000, 0.010, 65536),
                          "alternative": Link("alternative", 1000000, 0.010, 65536)},
                "egress": Link("egress", 256000, 0.001, 65536),
                "scada_period_s": 0.1, "ami_period_s": 1.0, "scada_bytes": 512,
                "ami_bytes": 512, "scada_deadline_s": 0.25, "ami_deadline_s": 10.0,
                "rate_tables": {"lte": [(0, 0, 1000000), (50, 0, 32000), (200, 0, 0),
                                        (0, 5, 200000), (48, 5, 68000), (49, 5, 0)]}}
    return FiniteModel(**{**settings, **changes})


class LegKindTests(unittest.TestCase):
    """ADR-29: a disturbance must be one its leg can take."""

    def test_an_lte_leg_has_no_rate_to_change(self):
        with self.assertRaises(ContractError) as caught:
            Record("ScenarioSpec", with_disturbance(
                {"at_s": 1.0, "site": "site-1", "leg": "lte", "kind": "rate", "rate_bps": 0}))
        self.assertIn("cannot apply to a lte leg", str(caught.exception))

    def test_a_point_to_point_leg_has_no_radio(self):
        with self.assertRaises(ContractError) as caught:
            Record("ScenarioSpec", with_disturbance(
                {"at_s": 1.0, "site": "site-1", "leg": "alternative", "kind": "radio_loss",
                 "extra_loss_db": 50}))
        self.assertIn("cannot apply to a point_to_point leg", str(caught.exception))

    def test_an_lte_leg_must_position_every_site(self):
        legs = [{**leg, "radio": {**leg["radio"], "site_positions_m": {}}}
                if leg["kind"] == "lte" else leg for leg in NOMINAL["topology"]["legs"]]
        with self.assertRaises(ContractError):
            Record("ScenarioSpec", {**NOMINAL, "topology": {**NOMINAL["topology"], "legs": legs}})

    def test_every_lte_leg_in_the_set_is_declared_by_radio_and_not_by_rate(self):
        for path in sorted(SCENARIOS.glob("s*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for leg in data["topology"]["legs"]:
                if leg["kind"] == "lte":
                    with self.subTest(scenario=path.name):
                        self.assertNotIn("capacity_bps", leg)
                        self.assertIn("radio", leg)

    def test_radio_loss_takes_the_largest_declared_loss_not_above_it(self):
        model = world()
        for loss, expected in ((0, 1000000), (49.9, 1000000), (50, 32000), (120, 32000),
                               (200, 0), (500, 0)):
            with self.subTest(loss=loss):
                self.assertEqual(model.rate_for({"site": "site-1", "leg": "lte",
                                                 "kind": "radio_loss",
                                                 "extra_loss_db": loss}), expected)

    def test_load_and_loss_combine_and_each_keeps_the_other(self):
        """A cell load does not undo a radio loss, and a loss does not undo a load."""
        model = world(disturbances=[
            {"at_s": 0.1, "site": "site-1", "leg": "lte", "kind": "radio_loss", "extra_loss_db": 48},
            {"at_s": 0.2, "site": "site-1", "leg": "lte", "kind": "cell_load", "competing_ues": 5},
            {"at_s": 0.3, "site": "site-1", "leg": "lte", "kind": "cell_load", "competing_ues": 0}])
        rate = lambda: model._queues[("site-1", "lte", "up")].rate_bps
        model.advance_to(0.15)
        self.assertEqual(rate(), 1000000, "48 dB alone is above no declared unloaded loss entry")
        model.advance_to(0.25)
        self.assertEqual(rate(), 68000, "the load applies at the loss the leg already has")
        model.advance_to(0.35)
        self.assertEqual(rate(), 1000000, "removing the load keeps the loss")
        # Between declared load levels, the lower level's table applies.
        self.assertEqual(model.lookup("lte", 48, 7), 68000)
        self.assertEqual(model.lookup("lte", 48, 4), 1000000)

    def test_a_leg_with_no_table_cannot_take_a_radio_condition(self):
        for disturbance in ({"kind": "radio_loss", "extra_loss_db": 50},
                            {"kind": "cell_load", "competing_ues": 5}):
            with self.subTest(kind=disturbance["kind"]), self.assertRaises(ContractError):
                world(rate_tables={}).rate_for({"site": "site-1", "leg": "lte", **disturbance})

    def test_cell_load_applies_only_to_an_lte_leg_and_within_range(self):
        with self.assertRaises(ContractError) as caught:
            Record("ScenarioSpec", with_disturbance(
                {"at_s": 1.0, "site": "site-1", "leg": "alternative", "kind": "cell_load",
                 "competing_ues": 5}))
        self.assertIn("cannot apply to a point_to_point leg", str(caught.exception))
        with self.assertRaises(ContractError) as caught:
            Record("ScenarioSpec", with_disturbance(
                {"at_s": 1.0, "site": "site-1", "leg": "lte", "kind": "cell_load",
                 "competing_ues": 36}))
        self.assertIn("valid range", str(caught.exception))

    def test_a_disturbance_changes_both_directions(self):
        model = world(disturbances=[{"at_s": 0.5, "site": "site-1", "leg": "lte",
                                     "kind": "radio_loss", "extra_loss_db": 200}])
        # The last answer before the loss stays evidence for its validity, as a real
        # probe's would; once that has passed, a silent leg answers in neither direction.
        model.advance_to(1.2)
        self.assertIsNone(model.probe("site-1", "lte"), "a silent leg answers in neither direction")
        self.assertIsNotNone(model.probe("site-1", "alternative"))


class TransactionTests(unittest.TestCase):
    """SCADA is a round trip, and the transaction is the obligation."""

    def test_a_transaction_completes_only_when_its_response_arrives(self):
        model = world().advance_to(2.0)
        scada = [p for p in model.generated if p.service == "scada"]
        self.assertTrue(all(p.kind == "request" for p in scada))
        for obligation, at, _ in model.delivered:
            if obligation.service == "scada":
                # Down, processed, up: never sooner than both propagation delays and the
                # site's processing.
                self.assertGreaterEqual(at - obligation.generated_s,
                                        2 * 0.010 + 2 * 0.001 + model.processing_delay_s)

    def test_a_lost_request_loses_the_transaction(self):
        model = world(disturbances=[{"at_s": 0.0, "site": "site-1", "leg": "lte",
                                     "kind": "radio_loss", "extra_loss_db": 200}])
        model.advance_to(3.0)
        delivered = {o.packet_id for o, _, _ in model.delivered if o.service == "scada"}
        self.assertEqual(delivered, set(), "no request crosses a silent leg, so none completes")

    def test_the_request_keeps_the_leg_it_was_released_on(self):
        model = world()
        model.advance_to(0.0)
        in_flight = [p for p in model.generated if p.service == "scada"]
        self.assertEqual(in_flight[0].route[-1], ("site-1", "lte", "down"))
        model.apply({"operator": "select_path", "target": "site-1",
                     "arguments": {"path": "alternative"}})
        model.advance_to(0.2)
        later = [p for p in model.generated if p.service == "scada"][-1]
        self.assertEqual(later.route[-1], ("site-1", "alternative", "down"))
        self.assertEqual(in_flight[0].route[-1], ("site-1", "lte", "down"))

    def test_the_scenario_set_still_produces_the_conditions_it_declares(self):
        """Uncontrolled, over eight seconds: S0 clean, S1 and S2 breaking SCADA."""
        def on_time(name):
            model = build_world(load(SCENARIOS / f"{name}.json")).advance_to(8.0)
            settled = [p for p in model.generated
                       if p.service == "scada" and p.deadline_s <= 8.0]
            ids = {p.packet_id for p in settled}
            return sum(1 for o, _, ok in model.delivered if o.packet_id in ids and ok) / len(settled)
        self.assertEqual(on_time("s0-nominal"), 1.0)
        self.assertLess(on_time("s1-degraded-primary"), 0.5)
        self.assertLess(on_time("s2-silent-primary"), 0.5)


if __name__ == "__main__":
    unittest.main()
