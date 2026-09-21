import tempfile
import unittest
from pathlib import Path

from ecora.boundary import Boundary
from ecora.contracts import ContractError, Record
from ecora.fixtures import batch, fixture_environment
from ecora.store import ArtifactStore


def payloads_of(store, dataset_id):
    return [Record.from_dict(m.data["payload"]) for m in store.messages(dataset_id)]


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.environment = fixture_environment()

    def open(self, name, run_id="run:original"):
        registry, study, scenario_set, scenario, caps = self.environment
        store = ArtifactStore(Path(self.temp.name) / name)
        self.addCleanup(store.close)
        run = registry.admit(study, scenario_set, scenario, caps, "reference", run_id)
        return store, Boundary(store, registry, run)

    def record(self, store, boundary, suffix=""):
        """Produce a telemetry dataset and the diagnosis it fed, as recorded evidence."""
        source = boundary.ingest(f"ingest{suffix}", batch(), watermark_s=0)
        telemetry = boundary.invoke("telemetry", f"telemetry{suffix}",
                                    [source.data["dataset_id"]], watermark_s=0)
        diagnosis = boundary.invoke("diagnosis", f"diagnosis{suffix}",
                                    [telemetry.data["dataset_id"]], watermark_s=0)
        return telemetry, diagnosis

    def test_boundary_playback_reproduces_the_downstream_output(self):
        """Replayed into telemetry, whose fixture output depends on what it was given.

        The diagnosis fixture ignores its inputs, so replaying into it would pass whatever
        the replay delivered. Telemetry carries its input through, which makes this test
        able to fail if playback delivered the wrong evidence.
        """
        from ecora.fixtures import observation
        store, boundary = self.open("playback")
        source = boundary.ingest("ingest", batch(), watermark_s=0)
        telemetry = boundary.invoke("telemetry", "telemetry",
                                    [source.data["dataset_id"]], watermark_s=0)
        played = boundary.replay("replay:ingest", "telemetry",
                                 source_dataset_id=source.data["dataset_id"], watermark_s=0)
        again = boundary.invoke("telemetry", "telemetry:replayed",
                                [played.data["dataset_id"]], watermark_s=0)
        original = payloads_of(store, telemetry.data["dataset_id"])
        replayed = payloads_of(store, again.data["dataset_id"])
        self.assertEqual([r.content_hash for r in original], [r.content_hash for r in replayed])

        # Negative control: different recorded evidence must not reproduce that output.
        other = boundary.ingest("ingest:other",
                                batch(observations=[observation(value=4096)]), watermark_s=0)
        elsewhere = boundary.replay("replay:other", "telemetry",
                                    source_dataset_id=other.data["dataset_id"], watermark_s=0)
        differs = boundary.invoke("telemetry", "telemetry:other",
                                  [elsewhere.data["dataset_id"]], watermark_s=0)
        self.assertNotEqual([r.content_hash for r in original],
                            [r.content_hash for r in payloads_of(store, differs.data["dataset_id"])])

    def test_replayed_evidence_names_the_run_and_invocation_it_came_from(self):
        store, boundary = self.open("provenance")
        telemetry, _ = self.record(store, boundary)
        played = boundary.replay("replay:provenance", "diagnosis",
                                 source_dataset_id=telemetry.data["dataset_id"], watermark_s=0)
        replay = store.messages(played.data["dataset_id"])[0].data["replay"]
        self.assertEqual(replay["mode"], "boundary_playback")
        self.assertEqual(replay["original_run_id"], "run:original")
        self.assertEqual(replay["original_invocation_id"], "telemetry")
        # Ordinary evidence stays marked as not replayed, so the two cannot be confused.
        ordinary = store.messages(telemetry.data["dataset_id"])[0].data["replay"]
        self.assertEqual(ordinary["mode"], "none")

    def test_playback_carries_evidence_across_runs_without_joining_their_lineage(self):
        first, boundary = self.open("cross-a", run_id="run:first")
        telemetry, _ = self.record(first, boundary)
        second, other = self.open("cross-b", run_id="run:second")
        played = other.replay("replay:cross", "diagnosis", source_store=first,
                              source_dataset_id=telemetry.data["dataset_id"], watermark_s=0)
        data = second.messages(played.data["dataset_id"])[0].data
        # It belongs to the replay run, and says where it was recorded.
        self.assertEqual(data["scope"]["run_id"], "run:second")
        self.assertEqual(data["replay"]["original_run_id"], "run:first")
        # It claims no lineage in the replay run beyond itself.
        self.assertEqual(second.dataset(played.data["dataset_id"]).data["source_dataset_ids"], [])

    def test_a_dataset_addressing_nothing_to_the_stage_cannot_be_played_back(self):
        store, boundary = self.open("empty")
        _, diagnosis = self.record(store, boundary)
        # A DiagnosisRecord is addressed to sink; planning consumes an assembled input.
        with self.assertRaises(ContractError):
            boundary.replay("replay:empty", "planning",
                            source_dataset_id=diagnosis.data["dataset_id"], watermark_s=0)

    def test_counterfactual_modes_are_refused_rather_than_approximated(self):
        store, boundary = self.open("modes")
        telemetry, _ = self.record(store, boundary)
        for mode in ("component_substitution", "closed_loop_branch"):
            with self.subTest(mode=mode), self.assertRaises(ContractError):
                boundary.replay(f"replay:{mode}", "diagnosis", mode=mode,
                                source_dataset_id=telemetry.data["dataset_id"], watermark_s=0)

    def test_a_provider_resumes_from_its_recorded_state_snapshot(self):
        store, boundary = self.open("state")
        telemetry, diagnosis = self.record(store, boundary)
        # The fixture diagnosis counts the invocations it has seen in its own state.
        first = store.invocation("diagnosis")
        self.assertEqual(store.get(first.data["next_state_hash"]).data["state"], {"seen": 1})
        resumed = boundary.invoke("diagnosis", "diagnosis:resumed",
                                  [telemetry.data["dataset_id"]], watermark_s=0,
                                  prior_state_hash=first.data["next_state_hash"])
        carried = store.invocation("diagnosis:resumed")
        self.assertEqual(carried.data["prior_state_hash"], first.data["next_state_hash"])
        self.assertEqual(store.get(carried.data["next_state_hash"]).data["state"], {"seen": 2})
        self.assertEqual(resumed.data["terminal_status"], "ok")

    def test_replay_cannot_shed_the_privilege_of_what_it_replays(self):
        truth = {"capability_id": "truth.ami.queue", "kind": "truth", "target": "site-1",
                 "service": "ami", "name": "queue_occupancy", "unit": "byte",
                 "evidence_refs": ["fixture:truth"]}
        self.environment = fixture_environment(allow_privileged=True, extra_capabilities=(truth,))
        store, boundary = self.open("privileged")
        from ecora.fixtures import observation
        privileged = observation(capability_id=truth["capability_id"],
                                 evidence_kind="simulator_truth",
                                 privileged_source_refs=["truth:current:0"])
        source = boundary.ingest("ingest:truth", batch(observations=[privileged]), watermark_s=0)
        telemetry = boundary.invoke("telemetry", "telemetry:truth",
                                    [source.data["dataset_id"]], watermark_s=0)
        played = boundary.replay("replay:truth", "diagnosis",
                                 source_dataset_id=telemetry.data["dataset_id"], watermark_s=0)
        self.assertEqual(played.data["information_regime"], "oracle_state")
        self.assertEqual(played.data["privileged_source_refs"], ["truth:current:0"])


if __name__ == "__main__":
    unittest.main()
