import copy
import json
import unittest

from ecora import calibration, ns3build
from ecora.contracts import ContractError
from ecora.scenario import SCENARIOS, build_world, load


def point(loss, rate, direction="up", run=1, competitors=0):
    return {"loss_db": loss, "goodput_bps": rate, "direction": direction, "rng_run": run,
            "competitors": competitors, "window_s": [1.0, 6.0], "payload_bytes": 544,
            "offered_bps": 20e6, "received_bytes": 0}


class DerivationTests(unittest.TestCase):
    """What a table may be derived from, and what it refuses."""

    def test_a_table_steps_where_the_median_changes_and_reaches_the_cliff(self):
        points = [point(0, 100), point(10, 100), point(20, 60), point(30, 0),
                  point(0, 50, competitors=2), point(20, 20, competitors=2),
                  point(30, 0, competitors=2)]
        table = calibration.derive_table(points)
        self.assertEqual(table["capacity_bps"], 100)
        self.assertEqual([(e["competing_ues"], e["extra_loss_db"], e["capacity_bps"])
                          for e in table["rate_table"]],
                         [(0, 0, 100), (0, 20, 60), (0, 30, 0),
                          (2, 0, 50), (2, 20, 20), (2, 30, 0)])

    def test_the_median_is_not_moved_by_one_stray_run(self):
        points = [point(0, 100, run=r) for r in (1, 2, 3)]
        points += [point(50, 0, run=1), point(50, 870, run=2), point(50, 0, run=3)]
        self.assertEqual(calibration.derive_table(points)["rate_table"][-1]["capacity_bps"], 0)

    def test_a_rate_that_rises_with_loss_or_load_is_refused(self):
        for points in ([point(0, 100), point(10, 120), point(20, 0)],
                       [point(0, 100), point(20, 0),
                        point(0, 150, competitors=1), point(20, 0, competitors=1)]):
            with self.subTest(points=points), self.assertRaises(ContractError):
                calibration.derive_table(points)

    def test_a_grid_that_never_reaches_the_cliff_is_refused(self):
        with self.assertRaises(ContractError):
            calibration.derive_table([point(0, 100), point(20, 60)])


@unittest.skipUnless(calibration.DATASET.is_file(), "no committed calibration dataset")
class CommittedCalibrationTests(unittest.TestCase):
    """The dataset in the repository, and the scenarios that cite it."""

    @classmethod
    def setUpClass(cls):
        cls.dataset = calibration.verify(calibration.load())

    def test_it_was_measured_with_the_manifests_build(self):
        manifest = ns3build.load()
        self.assertEqual(self.dataset["simulator_build_id"], manifest["simulator_build_id"])
        self.assertEqual(self.dataset["model_hash"], manifest["model_hash"])
        self.assertEqual(self.dataset["calibrate_source_sha256"],
                         manifest["sources"]["ecora-calibrate/ecora-calibrate.cc"])

    def test_a_tampered_point_breaks_it(self):
        altered = copy.deepcopy(self.dataset)
        altered["points"][0]["goodput_bps"] += 1
        with self.assertRaises(ContractError):
            calibration.verify(altered)

    def test_every_scenario_reads_the_lte_leg_through_this_dataset(self):
        for path in sorted(SCENARIOS.glob("s*.json")):
            with self.subTest(scenario=path.stem):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(calibration.apply(data, self.dataset), data,
                                 "the scenario's LTE interpretation is the measured one")
                logical = calibration.lte_leg(data)["logical"]
                self.assertEqual(logical["calibration"], self.dataset["dataset_hash"])

    def test_a_table_measured_on_one_radio_says_nothing_about_another(self):
        data = json.loads((SCENARIOS / "s0-nominal.json").read_text(encoding="utf-8"))
        calibration.lte_leg(data)["radio"]["ue_tx_dbm"] = 20
        with self.assertRaises(ContractError):
            calibration.apply(data, self.dataset)

    def test_the_degraded_condition_is_degraded_and_not_silent(self):
        """S1's declared conditions fall in the measured table's live, constrained region."""
        model = build_world(load(SCENARIOS / "s1-degraded-primary.json"))
        rate = model.lookup("lte", 48, 5)
        self.assertGreater(rate, 0, "the leg still delivers")
        self.assertLess(rate, 100000, "and delivers less than SCADA and AMI together need")


if __name__ == "__main__":
    unittest.main()
