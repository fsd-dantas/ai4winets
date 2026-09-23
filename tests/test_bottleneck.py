import unittest

from ecora import bottleneck
from ecora.contracts import ContractError
from ecora.scenario import SCENARIOS, build_world, load
from ecora.simulator import Ns3World

BASE = load(SCENARIOS / "s0-nominal.json")


class InstrumentationTests(unittest.TestCase):
    """The queue instrumentation accounts for every datagram and every byte-second."""

    def test_every_arrival_departs_is_dropped_or_is_still_held(self):
        model = build_world(bottleneck.variant(BASE, 48000, "normal")).advance_to(8.0)
        for name, queue in model.queues().items():
            held = len(model._queues[tuple(name.split("/")) if not name.startswith("egress")
                                      else ("egress", "egress", name.split("/")[1])].pending)
            waiting = sum(s["arrivals"] - s["departures"] - s["drops"]
                          for s in queue["by_service"].values())
            with self.subTest(queue=name):
                # A departure is counted when transmission starts, so the head of a busy
                # queue has departed and is still held.
                self.assertIn(waiting, (held, held - 1))
                self.assertLessEqual(queue["occupancy_mean_bytes"], queue["occupancy_peak_bytes"])
                self.assertLessEqual(queue["occupancy_peak_bytes"], queue["queue_limit_bytes"])

    def test_classes_are_counted_apart_at_the_shared_queue(self):
        egress = build_world(bottleneck.variant(BASE, 256000, "normal")).advance_to(8.0).queues()["egress/up"]
        self.assertEqual(set(egress["by_service"]), {"scada", "ami"})
        downlink = build_world(bottleneck.variant(BASE, 256000, "normal")).advance_to(8.0).queues()["egress/down"]
        self.assertEqual(set(downlink["by_service"]), {"scada"}, "only requests travel down")


class PilotTests(unittest.TestCase):
    def test_a_variant_changes_only_what_the_pilot_varies(self):
        variant = bottleneck.variant(BASE, 64000, "minimum").data
        self.assertEqual(variant["topology"]["egress"]["capacity_bps"], 64000)
        self.assertEqual(variant["topology"]["initial_pacing"], "minimum")
        self.assertEqual(variant["topology"]["legs"], BASE.data["topology"]["legs"])
        self.assertEqual(variant["disturbances"], BASE.data["disturbances"])
        self.assertNotEqual(variant["scenario_id"], BASE.data["scenario_id"])

    def test_labels_separate_contention_from_overload(self):
        def cell(capacity, pacing, ratio):
            return {"capacity_bps": capacity, "pacing": pacing,
                    "outcome": {"services": {"scada": {"on_time_ratio": ratio}}}}
        cells = [cell(40, "normal", 0), cell(40, "minimum", 0.5),
                 cell(60, "normal", 0.2), cell(60, "minimum", 1.0),
                 cell(90, "normal", 1.0), cell(90, "minimum", 1.0)]
        labels = bottleneck.labels(cells)
        self.assertEqual(labels["attainable_capacity_bps"], {"normal": 90, "minimum": 60})
        self.assertEqual(labels["contended_capacities_bps"], [60],
                         "40 is overload: SCADA fails even with AMI throttled")


def scada_on_time(scenario, pacing, world="finite"):
    import copy
    data = copy.deepcopy(scenario.data)
    data["topology"]["initial_pacing"] = pacing
    run = bottleneck.run_finite if world == "finite" else bottleneck.run_simulated
    return run(data)["services"]["scada"]["on_time_ratio"]


class ScenarioSetTests(unittest.TestCase):
    """The set holds one egress contention case and one deliberate overload case."""

    def test_s9_is_contention_that_pacing_relieves(self):
        s9 = load(SCENARIOS / "s9-contended-egress.json")
        self.assertLess(scada_on_time(s9, "normal"), bottleneck.SERVICE_TARGET)
        self.assertGreaterEqual(scada_on_time(s9, "minimum"), bottleneck.SERVICE_TARGET)

    def test_s5_is_overload_that_no_pacing_relieves(self):
        s5 = load(SCENARIOS / "s5-narrow-egress.json")
        for pacing in ("normal", "restricted", "minimum"):
            with self.subTest(pacing=pacing):
                self.assertLess(scada_on_time(s5, pacing), bottleneck.SERVICE_TARGET)


@unittest.skipUnless(bottleneck.DATASET.is_file(), "no committed pilot dataset")
class CommittedPilotTests(unittest.TestCase):
    """What the recorded pilot establishes, in each world."""

    @classmethod
    def setUpClass(cls):
        cls.pilot = bottleneck.load_dataset()

    def test_a_tampered_dataset_is_refused(self):
        import json
        import tempfile
        from pathlib import Path
        altered = dict(self.pilot, pilot_version="other")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pilot.json"
            path.write_text(json.dumps(altered), encoding="utf-8")
            with self.assertRaises(ContractError):
                bottleneck.load_dataset(path)

    def test_both_worlds_show_a_shared_bottleneck_that_pacing_relieves(self):
        for world, result in self.pilot["results"].items():
            with self.subTest(world=world):
                self.assertTrue(result["labels"]["contended_capacities_bps"],
                                "some capacity serves SCADA only while AMI is throttled")
                by = {(c["capacity_bps"], c["pacing"]): c["outcome"] for c in result["cells"]}
                for capacity in {c for c, _ in by}:
                    throttled = by[(capacity, "minimum")]["services"]["scada"]["on_time"]
                    normal = by[(capacity, "normal")]["services"]["scada"]["on_time"]
                    self.assertGreaterEqual(throttled, normal,
                                            f"throttling AMI never hurts SCADA ({capacity} bit/s)")

    def test_the_wait_is_at_the_egress_where_the_classes_meet(self):
        """Where contention decides the outcome, AMI's load shows up as SCADA's egress wait."""
        for world, result in self.pilot["results"].items():
            by = {(c["capacity_bps"], c["pacing"]): c["outcome"] for c in result["cells"]}
            for capacity in result["labels"]["contended_capacities_bps"]:
                wait = {pacing: by[(capacity, pacing)]["egress"]["up"]["by_service"]["scada"]["delay_mean_s"]
                        for pacing in ("normal", "minimum")}
                with self.subTest(world=world, capacity=capacity):
                    self.assertGreater(wait["normal"], 10 * wait["minimum"], wait)

    def test_the_worlds_agree_where_full_service_starts(self):
        normal = {world: result["labels"]["attainable_capacity_bps"]["normal"]
                  for world, result in self.pilot["results"].items()}
        self.assertEqual(len(set(normal.values())), 1, normal)


try:
    from test_simulator_adapter import AVAILABLE
except ImportError:
    from tests.test_simulator_adapter import AVAILABLE


@unittest.skipUnless(AVAILABLE, "no ns-3 simulator build is available on this host")
class SimulatedQueueTests(unittest.TestCase):
    def test_the_simulated_egress_accounts_for_what_it_carried(self):
        with Ns3World.start(bottleneck.variant(BASE, 64000, "normal")) as world:
            world.advance_to(4.0)
            queues = world.queues()
        egress = queues["egress/up"]
        self.assertTrue(egress["instrumented"])
        self.assertEqual(set(egress["by_service"]), {"scada", "ami"})
        for service, stats in egress["by_service"].items():
            with self.subTest(service=service):
                self.assertGreaterEqual(stats["arrivals"], stats["departures"] + stats["drops"])
        self.assertFalse(queues["site-1/lte/up"]["instrumented"],
                         "the RLC buffer is reported as not instrumented, not estimated")

    def test_s9_and_s5_hold_their_character_in_the_simulator(self):
        s9 = load(SCENARIOS / "s9-contended-egress.json")
        self.assertLess(scada_on_time(s9, "normal", "simulated"), bottleneck.SERVICE_TARGET)
        self.assertGreaterEqual(scada_on_time(s9, "minimum", "simulated"), bottleneck.SERVICE_TARGET)
        s5 = load(SCENARIOS / "s5-narrow-egress.json")
        self.assertLess(scada_on_time(s5, "minimum", "simulated"), bottleneck.SERVICE_TARGET)


if __name__ == "__main__":
    unittest.main()
