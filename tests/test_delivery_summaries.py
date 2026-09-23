import unittest

from ecora.model import DELIVERY_SUMMARY_DELAY_S
from ecora.scenario import SCENARIOS, build_world, load
from ecora.simulator import Ns3World

try:
    from test_simulator_adapter import AVAILABLE
except ImportError:
    from tests.test_simulator_adapter import AVAILABLE

GRANT = {("site-1", "scada_response"): "observe.scada.response",
         ("site-1", "queue_occupancy"): "observe.ami.queue"}
DEADLINE_S = 0.25


def summary(world, at):
    world.advance_to(at)
    return {o["metric"]: o for o in world.observations(capability_ids=GRANT, window_s=0.5)}


class SummaryTests(unittest.TestCase):
    """The centre's delivery summary, as a site receives it."""

    def test_a_summary_describes_the_window_ending_one_delay_ago(self):
        observed = summary(build_world(load(SCENARIOS / "s0-nominal.json")), 2.0)["scada_response"]
        self.assertAlmostEqual(observed["event_time_s"], 2.0 - DELIVERY_SUMMARY_DELAY_S)
        self.assertEqual(observed["window"]["end_s"], observed["event_time_s"])
        self.assertAlmostEqual(observed["window"]["end_s"] - observed["window"]["start_s"], 0.5)
        self.assertLess(observed["value"], DEADLINE_S)

    def test_no_completion_is_no_evidence_rather_than_a_fast_response(self):
        observed = summary(build_world(load(SCENARIOS / "s2-silent-primary.json")), 3.0)["scada_response"]
        self.assertEqual(observed["quality"], "missing")
        self.assertIsNone(observed["value"])
        self.assertEqual(observed["missing_reason"]["code"], "no_completion")

    def test_it_reveals_contention_the_sites_own_queue_cannot_show(self):
        """S9: the backlog is at the shared egress, so the site's queue stays near empty."""
        seen = summary(build_world(load(SCENARIOS / "s9-contended-egress.json")), 3.0)
        self.assertLessEqual(seen["queue_occupancy"]["value"], 32, "at most a probe in flight")
        self.assertGreater(seen["scada_response"]["value"], DEADLINE_S)


@unittest.skipUnless(AVAILABLE, "no ns-3 simulator build is available on this host")
class SimulatedSummaryTests(unittest.TestCase):
    def test_the_simulator_reports_the_same_three_conditions(self):
        with Ns3World.start(load(SCENARIOS / "s0-nominal.json")) as world:
            self.assertLess(summary(world, 3.0)["scada_response"]["value"], DEADLINE_S)
        with Ns3World.start(load(SCENARIOS / "s9-contended-egress.json")) as world:
            seen = summary(world, 3.0)
            self.assertEqual(seen["queue_occupancy"]["value"], 0)
            self.assertGreater(seen["scada_response"]["value"], DEADLINE_S)
        with Ns3World.start(load(SCENARIOS / "s2-silent-primary.json")) as world:
            self.assertEqual(summary(world, 3.0)["scada_response"]["quality"], "missing")


if __name__ == "__main__":
    unittest.main()
