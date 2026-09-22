import unittest

from ecora.contracts import ContractError, Record, validate
from ecora.model import FiniteModel, Link, PACING_BPS


def model(**changes):
    settings = {
        "sites": ["site-1"],
        "links": {"lte": Link("lte", 1000000, 0.010, 65536),
                  "alternative": Link("alternative", 1000000, 0.010, 65536)},
        "egress": Link("egress", 256000, 0.001, 65536),
        "scada_period_s": 0.1, "ami_period_s": 1.0,
        "scada_bytes": 512, "ami_bytes": 512,
        "scada_deadline_s": 0.25, "ami_deadline_s": 10.0,
    }
    return FiniteModel(**{**settings, **changes})


class ModelTests(unittest.TestCase):
    def test_run_is_deterministic_and_repeatable(self):
        first, second = model().advance_to(5.0).truth(), model().advance_to(5.0).truth()
        self.assertEqual(first, second)
        self.assertGreater(first["generated"], 0)
        self.assertGreater(first["delivered"], 0)

    def test_advancing_in_steps_matches_advancing_at_once(self):
        stepwise = model()
        for step in range(50):
            stepwise.advance_to((step + 1) * 0.1)
        self.assertEqual(stepwise.truth(), model().advance_to(5.0).truth())

    def test_the_clock_cannot_move_backwards(self):
        world = model().advance_to(1.0)
        with self.assertRaises(ContractError):
            world.advance_to(0.5)

    def test_no_generated_packet_is_lost_from_the_ledger(self):
        world = model().advance_to(5.0)
        truth = world.truth()
        accounted = truth["delivered"] + truth["dropped"]
        queued = sum(truth["queue_bytes"].values()) + truth["egress_bytes"]
        self.assertLessEqual(accounted, truth["generated"])
        if accounted < truth["generated"]:
            self.assertGreater(queued, 0, "unaccounted demand must still be queued")

    def test_path_selection_changes_the_leg_and_its_version(self):
        world = model().advance_to(1.0)
        command = {"operator": "select_path", "target": "site-1", "arguments": {"path": "alternative"}}
        applied, reason = world.apply(command)
        self.assertTrue(applied)
        self.assertIsNone(reason)
        self.assertEqual(world.truth()["selected_path"]["site-1"], "alternative")
        self.assertEqual(world.path_version["site-1"], 1)

    def test_unknown_target_or_path_is_refused_without_mutating(self):
        world = model().advance_to(1.0)
        before = world.truth()
        for command in ({"operator": "select_path", "target": "site-9", "arguments": {"path": "lte"}},
                        {"operator": "select_path", "target": "site-1", "arguments": {"path": "ka-band"}},
                        {"operator": "set_ami_pacing", "target": "site-1", "arguments": {"profile": "turbo"}}):
            with self.subTest(command=command):
                applied, reason = world.apply(command)
                self.assertFalse(applied)
                self.assertIsNotNone(reason)
        self.assertEqual(world.truth(), before)

    def test_pacing_throttles_ami_only_where_demand_exceeds_the_profile(self):
        """A profile only bites when AMI offers more than it allows.

        At the baseline period AMI offers 4096 bit/s, at or below every declared profile,
        so pacing changes nothing there and an assertion that it did would be asserting
        nothing. Raise the offered load and the profiles separate.
        """
        def delivered_by_service(profile, period):
            world = model(initial_pacing=profile, ami_period_s=period).advance_to(20.0)
            counts = {}
            for packet, _, _ in world.delivered:
                counts[packet.service] = counts.get(packet.service, 0) + 1
            return counts

        quiet = {profile: delivered_by_service(profile, 1.0) for profile in PACING_BPS}
        self.assertEqual(quiet["normal"]["ami"], quiet["restricted"]["ami"],
                         "below every profile, pacing cannot be what makes a difference")

        busy = {profile: delivered_by_service(profile, 0.05) for profile in PACING_BPS}
        self.assertGreater(busy["normal"]["ami"], busy["restricted"]["ami"])
        self.assertGreater(busy["restricted"]["ami"], busy["minimum"]["ami"])
        # SCADA is untouched by the AMI profile. Pacing holds readings at the gateway, so
        # a held reading never sits in the shared queue ahead of a SCADA transaction.
        self.assertEqual(len({counts["scada"] for counts in busy.values()}), 1)

    def test_paced_demand_is_held_rather_than_made_to_disappear(self):
        held, dropped = {}, {}
        for profile in PACING_BPS:
            truth = model(initial_pacing=profile, ami_period_s=0.05).advance_to(20.0).truth()
            held[profile] = truth["held_ami"]["site-1"]
            dropped[profile] = truth["dropped"]
        # A tighter profile withholds more, and none of it is quietly lost.
        self.assertGreater(held["minimum"], held["restricted"])
        self.assertGreater(held["restricted"], held["normal"])
        self.assertEqual(set(dropped.values()), {0})

    def test_a_disturbance_degrades_service_and_the_backlog_then_recovers(self):
        def run(disturbed):
            world = model(disturbances=[
                {"at_s": 1.0, "site": "site-1", "leg": "lte", "rate_bps": 16000},
                {"at_s": 3.0, "site": "site-1", "leg": "lte", "rate_bps": 1000000}]
                if disturbed else [])
            during = world.advance_to(3.0).truth()
            return during, world.advance_to(8.0).truth()

        during_bad, after_bad = run(True)
        during_ok, after_ok = run(False)
        # While the leg is impaired, demand backs up and fewer packets are delivered.
        self.assertLess(during_bad["delivered"], during_ok["delivered"])
        self.assertGreater(sum(during_bad["queue_bytes"].values()), 0)
        # Once it is restored the backlog drains: this is degradation, not loss.
        self.assertEqual(after_bad["delivered"], after_ok["delivered"])
        self.assertEqual(after_bad["dropped"], 0)

    def test_a_probe_answers_on_a_serving_leg_and_not_on_a_silent_one(self):
        world = model().advance_to(1.0)
        self.assertIsNotNone(world.probe("site-1", "lte"))
        self.assertGreater(world.probe("site-1", "lte"), 2 * 0.010)
        silent = model(disturbances=[{"at_s": 0.5, "site": "site-1", "leg": "lte",
                                      "rate_bps": 0}]).advance_to(1.0)
        self.assertIsNone(silent.probe("site-1", "lte"),
                          "a leg with no service must not answer a probe")

    def test_a_silent_leg_holds_its_queue_and_drains_once_restored(self):
        world = model(disturbances=[
            {"at_s": 0.5, "site": "site-1", "leg": "lte", "rate_bps": 0},
            {"at_s": 2.0, "site": "site-1", "leg": "lte", "rate_bps": 1000000}])
        during = world.advance_to(1.5).truth()
        self.assertGreater(sum(during["queue_bytes"].values()), 0)
        after = world.advance_to(6.0).truth()
        self.assertEqual(after["dropped"], 0, "held demand is not lost")
        self.assertGreater(after["delivered"], during["delivered"])

    def test_a_timed_out_probe_is_exported_as_unknown_not_as_a_slow_reply(self):
        world = model(disturbances=[{"at_s": 0.5, "site": "site-1", "leg": "alternative",
                                     "rate_bps": 0}]).advance_to(1.0)
        capabilities = {("site-1/lte", "path_probe"): "observe.probe.lte",
                        ("site-1/alternative", "path_probe"): "observe.probe.alternative"}
        exported = {o["subject"]: o for o in world.observations(capability_ids=capabilities)}
        self.assertEqual(exported["site-1/lte"]["quality"], "observed")
        silent = exported["site-1/alternative"]
        self.assertEqual(silent["quality"], "missing")
        self.assertIsNone(silent["value"])
        self.assertEqual(silent["missing_reason"]["code"], "probe_timeout")

    def test_exported_observations_satisfy_the_telemetry_contract(self):
        world = model().advance_to(2.0)
        capabilities = {("site-1", "queue_occupancy"): "observe.ami.queue",
                        ("site-1", "path_state"): "observe.shared.path"}
        observations = world.observations(capability_ids=capabilities)
        self.assertEqual(len(observations), 2)
        batch = Record("AdapterObservationBatch", {
            "observations": observations, "watermark_s": world.now,
            "window": {"start_s": 0, "end_s": world.now}, "sequence": 0,
            "completeness": 1, "omitted_metrics": []})
        self.assertEqual(batch.kind, "AdapterObservationBatch")

    def test_cohort_counts_balance_against_generated_demand(self):
        world = model().advance_to(5.0)
        spec = [{"cohort_id": "cohort:all", "generation_window": {"start_s": 0, "end_s": 5},
                 "deadline_s": 10}]
        cohorts = world.cohorts(spec)
        validate("ResultInput", {"receipt_ids": [], "observation_ids": [], "cohorts": cohorts})
        cohort = cohorts[0]
        self.assertEqual(cohort["generated"],
                         cohort["delivered_on_time"] + cohort["delivered_late"]
                         + cohort["lost"] + cohort["pending"])
        self.assertGreater(cohort["generated"], 0)


if __name__ == "__main__":
    unittest.main()
