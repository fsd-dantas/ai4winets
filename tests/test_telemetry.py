import tempfile
import unittest
from pathlib import Path

from ecora.boundary import Boundary
from ecora.contracts import ContractError, Record
from ecora.model import FiniteModel, Link
from ecora.registry import Registry
from ecora.runner import PROJECTION, Run, Streams, closed_loop_environment
from ecora.store import ArtifactStore
from ecora.telemetry import projection_binding

CAPABILITIES = {("site-1", "queue_occupancy"): "observe.ami.queue",
                ("site-1", "path_state"): "observe.shared.path",
                ("site-1", "pacing_profile"): "observe.ami.pacing",
                ("site-1/lte", "path_probe"): "observe.probe.lte",
                ("site-1/alternative", "path_probe"): "observe.probe.alternative"}
PERIOD = 0.5


def world():
    return FiniteModel(
        sites=["site-1"],
        links={"lte": Link("lte", 1000000, 0.010, 65536),
               "alternative": Link("alternative", 1000000, 0.010, 65536)},
        egress=Link("egress", 256000, 0.001, 65536),
        scada_period_s=0.1, ami_period_s=1.0, scada_bytes=512, ami_bytes=512,
        scada_deadline_s=0.25, ami_deadline_s=10.0)


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def open(self, name, *, projection=None, extra_capabilities=(), treatment="observing"):
        model = world()
        environment = closed_loop_environment(model, period_s=PERIOD, projection=projection,
                                              extra_capabilities=extra_capabilities)
        registry, study, scenario_set, scenario, caps = environment
        store = ArtifactStore(Path(self.temp.name) / name)
        self.addCleanup(store.close)
        run = registry.admit(study, scenario_set, scenario, caps, treatment, f"run:{name}")
        return store, Boundary(store, registry, run), model, study

    def relayed(self, store, dataset_id):
        return Record.from_dict(store.messages(dataset_id)[0].data["payload"])

    def test_it_relays_the_permitted_local_signals(self):
        store, boundary, model, study = self.open("relay", treatment="expert")
        run = Run(boundary, model, streams=Streams(study.data["seed_manifest"]),
                  capability_ids=CAPABILITIES, period_s=PERIOD, epochs=3,
                  assembly=study.data["assembly"])
        run.execute()
        # At the first instant no probe has been answered, so both are relayed as unknown.
        first = self.relayed(store, "dataset:telemetry:0")
        self.assertEqual(first.data["omitted_metrics"], ["path_probe"])
        batch = self.relayed(store, "dataset:telemetry:1")
        self.assertEqual(batch.data["completeness"], 1)
        self.assertEqual(batch.data["omitted_metrics"], [])
        self.assertEqual(sorted(o["metric"] for o in batch.data["observations"]),
                         ["pacing_profile", "path_probe", "path_probe", "path_state",
                          "queue_occupancy"])
        # Each leg is probed under its own subject, so a rule can say which leg it means.
        self.assertEqual(sorted(o["subject"] for o in batch.data["observations"]
                                if o["metric"] == "path_probe"),
                         ["site-1/alternative", "site-1/lte"])
        self.assertTrue(all(o["quality"] == "observed" for o in batch.data["observations"]))
        # The path switch the closed loop applies becomes visible in what it relays next.
        # The Null planner in this treatment switches at the first epoch; it needs no probe.
        self.assertEqual(
            next(o["value"] for o in first.data["observations"]
                 if o["metric"] == "path_state"), "lte")
        self.assertEqual(
            next(o["value"] for o in batch.data["observations"]
                 if o["metric"] == "path_state"), "alternative")

    def test_an_expected_signal_that_is_absent_becomes_an_explicit_unknown(self):
        """A signal the adapter never supplies is reported as unknown, not omitted silently."""
        projection = {**PROJECTION, "expected": [*PROJECTION["expected"],
                      {"subject": "site-1", "service": "ami", "metric": "goodput", "unit": "bit/s",
                       "capability_id": "observe.ami.goodput"}]}
        extra = ({"capability_id": "observe.ami.goodput", "kind": "observe", "target": "site-1",
                  "service": "ami", "name": "goodput", "unit": "bit/s",
                  "evidence_refs": ["fixture:observation"]},)
        store, boundary, model, study = self.open("absent", projection=projection,
                                                  extra_capabilities=extra)
        Run(boundary, model, streams=Streams(study.data["seed_manifest"]),
            capability_ids=CAPABILITIES, period_s=PERIOD, epochs=2,
            assembly=study.data["assembly"]).execute()
        # Epoch 1, once probes have answered, so only the never-supplied signal is absent.
        batch = self.relayed(store, "dataset:telemetry:1")
        self.assertEqual(batch.data["omitted_metrics"], ["goodput"])
        self.assertLess(batch.data["completeness"], 1)
        absent = next(o for o in batch.data["observations"] if o["metric"] == "goodput")
        self.assertEqual(absent["quality"], "missing")
        self.assertIsNone(absent["value"])
        self.assertEqual(absent["missing_reason"]["code"], "absent")

    def test_a_signal_older_than_the_freshness_bound_is_not_relayed_as_fresh(self):
        store, boundary, model, study = self.open("stale")
        from ecora.runner import observation_batch
        # Ingested once probes have answered, so every signal was fresh when it arrived.
        model.advance_to(0.5)
        boundary.ingest("ingest:old", observation_batch(model, CAPABILITIES, 0.5, PERIOD, 0),
                        watermark_s=0.5)
        # Decide two seconds later, well past the declared 0.5 s bound.
        stale = boundary.invoke("telemetry", "telemetry:stale", ["dataset:ingest:old"],
                                watermark_s=2.5)
        batch = self.relayed(store, stale.data["dataset_id"])
        self.assertEqual(batch.data["completeness"], 0)
        self.assertEqual(batch.data["omitted_metrics"],
                         ["pacing_profile", "path_probe", "path_state", "queue_occupancy"])
        for observation in batch.data["observations"]:
            self.assertEqual(observation["quality"], "missing")
            self.assertEqual(observation["missing_reason"]["code"], "stale")
            self.assertIsNone(observation["value"])

    def test_it_does_not_relay_another_site(self):
        """Local projection: a remote signal is dropped even when the adapter offers it."""
        extra = ({"capability_id": "observe.remote.queue", "kind": "observe", "target": "site-2",
                  "service": "ami", "name": "queue_occupancy", "unit": "byte",
                  "evidence_refs": ["fixture:observation"]},)
        store, boundary, model, study = self.open("remote", extra_capabilities=extra)
        from ecora.fixtures import observation
        remote = observation(observation_id="observation:site-2:queue:0", subject="site-2",
                             capability_id="observe.remote.queue")
        mixed = Record("AdapterObservationBatch", {
            "observations": [observation(), remote], "watermark_s": 0,
            "window": {"start_s": 0, "end_s": 0}, "sequence": 0,
            "completeness": 1, "omitted_metrics": []})
        boundary.ingest("ingest:mixed", mixed, watermark_s=0)
        result = boundary.invoke("telemetry", "telemetry:mixed", ["dataset:ingest:mixed"],
                                 watermark_s=0)
        batch = self.relayed(store, result.data["dataset_id"])
        # The site and what belongs to it are local; another site is not.
        self.assertTrue(all(o["subject"] == "site-1" or o["subject"].startswith("site-1/")
                            for o in batch.data["observations"]))
        self.assertFalse(any(o["subject"].startswith("site-2") for o in batch.data["observations"]))
        trace = store.get(store.invocation("telemetry:mixed").data["trace_hash"]).data["state"]
        self.assertEqual(trace["out_of_neighbourhood"], 1)

    def test_it_cannot_expect_a_signal_it_is_not_permitted_to_observe(self):
        projection = {**PROJECTION, "expected": [
            {"subject": "site-1", "service": "ami", "metric": "link_measurement", "unit": "dBm",
             "capability_id": "observe.radio.power"}]}
        with self.assertRaises(ContractError) as caught:
            projection_binding(Registry(), ["observe.ami.queue"], projection)
        self.assertIn("not permitted to observe", str(caught.exception))

    def test_a_projection_must_declare_what_it_expects(self):
        with self.assertRaises(ContractError):
            projection_binding(Registry(), ["observe.ami.queue"],
                               {**PROJECTION, "expected": []})


if __name__ == "__main__":
    unittest.main()
