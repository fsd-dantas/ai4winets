import tempfile
import unittest
from pathlib import Path

from ecora.boundary import Boundary
from ecora.contracts import ContractError, Record
from ecora.model import FiniteModel, Link
from ecora.runner import Continuation, Run, Streams, closed_loop_environment
from ecora.store import ArtifactStore

CAPABILITIES = {("site-1", "queue_occupancy"): "observe.ami.queue",
                ("site-1", "path_state"): "observe.shared.path",
                ("site-1", "pacing_profile"): "observe.ami.pacing",
                ("site-1/lte", "path_probe"): "observe.probe.lte",
                ("site-1/alternative", "path_probe"): "observe.probe.alternative",
                ("site-1", "scada_response"): "observe.scada.response",
                ("site-1/selected_path", "actuator_version"): "observe.shared.path_version",
                ("site-1/pacing_profile", "actuator_version"): "observe.ami.pacing_version"}
PERIOD = 0.5
EPOCHS = 4
BRANCH = 2


def world(alt_bps=1000000):
    return FiniteModel(
        sites=["site-1"],
        links={"lte": Link("lte", 1000000, 0.010, 65536),
               "alternative": Link("alternative", alt_bps, 0.010, 65536)},
        egress=Link("egress", 256000, 0.001, 65536),
        scada_period_s=0.1, ami_period_s=1.0, scada_bytes=512, ami_bytes=512,
        scada_deadline_s=0.25, ami_deadline_s=10.0)


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def run_one(self, treatment, name, run_id, *, model=None, start_epoch=0, store=None):
        model = model or world()
        registry, study, scenario_set, scenario, caps = closed_loop_environment(model, period_s=PERIOD)
        if store is None:
            store = ArtifactStore(Path(self.temp.name) / name)
            self.addCleanup(store.close)
        run = registry.admit(study, scenario_set, scenario, caps, treatment, run_id)
        boundary = Boundary(store, registry, run)
        dataset = Run(boundary, model, streams=Streams(study.data["seed_manifest"]),
                      capability_ids=CAPABILITIES, period_s=PERIOD, epochs=EPOCHS,
                      assembly=study.data["assembly"], start_epoch=start_epoch).execute()
        return store, model, dataset

    def continuation(self, store, alt_bps=1000000):
        return Continuation(store, build_model=lambda: world(alt_bps),
                            capability_ids=CAPABILITIES, period_s=PERIOD)

    def test_a_recorded_prefix_regenerates_and_verifies(self):
        """The recorded run applied a path switch, so regeneration must reapply it.

        If applied commands were not replayed, the regenerated world would still be on the
        original leg and the recorded path_state observations would not match, so this
        test fails rather than passing on a prefix that merely looks plausible.
        """
        store, original, _ = self.run_one("expert", "recorded", "run:recorded")
        rebuilt = self.continuation(store).regenerate(BRANCH)
        self.assertEqual(rebuilt.truth()["selected_path"], {"site-1": "alternative"})
        # Regeneration leaves the clock at the prefix's last event: the last replayed epoch,
        # or a command dispatched after it. The branch epoch is the one that advances past
        # that, so no epoch is skipped or replayed twice.
        self.assertGreaterEqual(rebuilt.now, (BRANCH - 1) * PERIOD)
        self.assertLess(rebuilt.now, BRANCH * PERIOD)
        self.assertGreater(len(self.continuation(store).applied_commands(0)), 0)

    def test_a_prefix_that_does_not_reproduce_refuses_to_branch(self):
        store, _, _ = self.run_one("expert", "diverge", "run:diverge")
        # Rebuild with a slower alternative leg. The recorded run switches onto it in its
        # first epoch, so from the second epoch the observed queue backs up and cannot
        # reproduce. Verification therefore has to catch a prefix whose first epoch matched.
        with self.assertRaises(ContractError) as caught:
            self.continuation(store, alt_bps=16000).regenerate(BRANCH)
        self.assertIn("diverges", str(caught.exception))

    def test_an_action_changing_branch_generates_its_own_outcomes(self):
        recorded_store, recorded_model, recorded_dataset = self.run_one(
            "expert", "origin", "run:origin")
        branched = self.continuation(recorded_store).regenerate(BRANCH)
        branch_store, branch_model, branch_dataset = self.run_one(
            "null_baseline", "branch", "run:branch", model=branched, start_epoch=BRANCH)

        # The branch continued the verified world rather than restarting it.
        self.assertEqual(branch_model.truth()["selected_path"], {"site-1": "alternative"})
        # It stopped acting from the branch point, so its version count stops advancing.
        self.assertLess(branch_model.path_version["site-1"],
                        recorded_model.path_version["site-1"])
        # It produced its own report under its own run identity.
        report = Record.from_dict(branch_store.messages(branch_dataset)[0].data["payload"])
        self.assertEqual(report.data["contributing_run_ids"], ["run:branch"])
        self.assertNotEqual(branch_store.head(), recorded_store.head())

    def test_a_branch_produces_no_evidence_before_its_branch_point(self):
        store, _, _ = self.run_one("expert", "prior", "run:prior")
        branched = self.continuation(store).regenerate(BRANCH)
        branch_store, _, _ = self.run_one("null_baseline", "after", "run:after",
                                          model=branched, start_epoch=BRANCH)
        for index in range(BRANCH):
            with self.subTest(epoch=index), self.assertRaises(ContractError):
                branch_store.dataset(f"dataset:ingest:{index}")
        for index in range(BRANCH, EPOCHS):
            self.assertEqual(branch_store.dataset(f"dataset:ingest:{index}")
                             .data["terminal_status"], "ok")

    def test_a_closed_loop_branch_is_not_offered_as_a_replayed_payload(self):
        store, _, _ = self.run_one("expert", "refuse", "run:refuse")
        registry, study, scenario_set, scenario, caps = closed_loop_environment(
            world(), period_s=PERIOD)
        run = registry.admit(study, scenario_set, scenario, caps, "expert", "run:refuse2")
        refused = ArtifactStore(Path(self.temp.name) / "refuse2")
        self.addCleanup(refused.close)
        boundary = Boundary(refused, registry, run)
        with self.assertRaises(ContractError) as caught:
            boundary.replay("replay:branch", "telemetry", mode="closed_loop_branch",
                            source_store=store, source_dataset_id="dataset:ingest:0")
        self.assertIn("verified prefix", str(caught.exception))

    def test_component_substitution_reruns_a_stage_on_its_recorded_inputs(self):
        store, _, _ = self.run_one("expert", "substitute", "run:substitute")
        registry, study, scenario_set, scenario, caps = closed_loop_environment(
            world(), period_s=PERIOD)
        run = registry.admit(study, scenario_set, scenario, caps, "null_baseline", "run:sub")
        other = ArtifactStore(Path(self.temp.name) / "sub")
        self.addCleanup(other.close)
        boundary = Boundary(other, registry, run)
        played = boundary.replay("sub:telemetry", "telemetry", mode="component_substitution",
                                 source_store=store, source_dataset_id="dataset:ingest:0")
        substituted = boundary.invoke("telemetry", "telemetry:substituted",
                                      [played.data["dataset_id"]], watermark_s=0)
        self.assertEqual(substituted.data["terminal_status"], "ok")
        self.assertEqual(other.messages(played.data["dataset_id"])[0].data["replay"]["mode"],
                         "component_substitution")
        # The Null telemetry arm withholds what the recorded adapter supplied.
        output = Record.from_dict(other.messages(substituted.data["dataset_id"])[0].data["payload"])
        self.assertEqual(output.data["observations"], [])
        self.assertEqual(output.data["omitted_metrics"],
                         ["actuator_version", "pacing_profile", "path_probe", "path_state",
                          "queue_occupancy", "scada_response"])


if __name__ == "__main__":
    unittest.main()
