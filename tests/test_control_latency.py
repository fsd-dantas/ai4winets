import tempfile
import unittest
from pathlib import Path

from ecora.__main__ import CAPABILITIES
from ecora.boundary import Boundary
from ecora.contracts import ContractError, Record
from ecora.runner import Continuation, Run, Schedule, Streams, closed_loop_environment
from ecora.scenario import SCENARIOS, build_world, load
from ecora.store import ArtifactStore
from ecora.study import Study, resolve

SCENARIO = load(SCENARIOS / "s1-degraded-primary.json")
BASELINE = resolve("baseline")
DELAYED = resolve("delayed-control")
EPOCHS = 6


def payloads(store, dataset_id):
    return [Record.from_dict(m.data["payload"]) for m in store.messages(dataset_id)]


def execute(root, study, treatment, *, latency_s=None, label=""):
    """One finite-world run on S1. The run identity omits the label, so two runs of the
    same configuration in different directories are comparable record for record."""
    model = build_world(SCENARIO)
    registry, manifest, scenario_set, scenario, caps = closed_loop_environment(
        model, scenario=SCENARIO, study=study, latency_s=latency_s)
    name = f"{study.study_id}-{treatment}".replace(":", "_")
    directory = Path(root) / f"{name}{label}"
    run = registry.admit(manifest, scenario_set, scenario, caps, treatment, f"run:{name}")
    with ArtifactStore(directory) as store:
        executed = Run(Boundary(store, registry, run), model,
                       streams=Streams(manifest.data["seed_manifest"]),
                       capability_ids=CAPABILITIES,
                       period_s=manifest.data["control"]["decision_period_s"],
                       epochs=EPOCHS, assembly=manifest.data["assembly"],
                       predicate_map=study.predicate_map)
        executed.execute()
    return {"store": ArtifactStore(directory), "model": model, "run": executed}


class ScheduleTests(unittest.TestCase):
    """Where a dispatch falls relative to the observations around it."""

    def test_a_barrier_command_is_first_seen_at_the_next_epoch(self):
        schedule = Schedule(0.5, 0)
        for index in range(10):
            self.assertEqual(schedule.evidence_index(schedule.dispatch_at(index)), index + 1)

    def test_a_latency_equal_to_the_period_lands_before_the_next_observation(self):
        # 0.1 is not exact in binary, so the sums drift from the grid; the tie rule must
        # still put every dispatch on the grid rather than on either side of it.
        schedule = Schedule(0.1, 0.1)
        for index in range(50):
            dispatched = schedule.dispatch_at(index)
            self.assertTrue(schedule.due(dispatched, schedule.decision_at(index + 1)))
            self.assertEqual(schedule.evidence_index(dispatched), index + 1)

    def test_a_latency_beyond_the_period_is_seen_one_epoch_later(self):
        short, long = Schedule(0.5, 0.01), Schedule(0.5, 0.6)
        for index in range(10):
            self.assertEqual(short.evidence_index(short.dispatch_at(index)), index + 1)
            self.assertEqual(long.evidence_index(long.dispatch_at(index)), index + 2)


class StudyControlTests(unittest.TestCase):
    def test_every_declared_study_states_its_timing(self):
        for study in (BASELINE, DELAYED):
            with self.subTest(study=study.study_id):
                self.assertGreater(study.control["decision_period_s"], 0)
                self.assertGreaterEqual(study.control["control_latency_s"], 0)

    def test_a_study_without_control_is_refused(self):
        data = {k: v for k, v in BASELINE.data.items() if k != "control"}
        with self.assertRaises(ContractError):
            Study(data)

    def test_a_latency_every_command_would_outlive_is_refused(self):
        """A latency at the command validity makes every command stale on arrival."""
        data = {**BASELINE.data, "control": {**BASELINE.control, "control_latency_s": 1}}
        with self.assertRaises(ContractError) as caught:
            Study(data)
        self.assertIn("expire before dispatch", str(caught.exception))


class DispatchTests(unittest.TestCase):
    """B25: commands reach the actuator a declared latency after the decision."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.runs = {}
        for study in (BASELINE, DELAYED):
            for treatment in ("planner", "blackboard"):
                cls.runs[(study.study_id, treatment)] = cls.execute(study, treatment)

    @classmethod
    def tearDownClass(cls):
        for entry in cls.runs.values():
            entry["store"].close()
        cls.temp.cleanup()

    @classmethod
    def execute(cls, study, treatment, **options):
        return execute(cls.temp.name, study, treatment, **options)

    def receipts(self, key):
        store = self.runs[key]["store"]
        return [p for d in store.dataset_ids() if d.startswith("dataset:action:")
                for p in payloads(store, d) if p.kind == "ActionReceipt"]

    def test_every_dispatch_is_a_latency_after_its_decision(self):
        for (study_id, treatment), entry in self.runs.items():
            latency = (BASELINE if study_id == BASELINE.study_id else DELAYED).control[
                "control_latency_s"]
            store = entry["store"]
            with self.subTest(study=study_id, treatment=treatment):
                dispatched = [d for d in store.dataset_ids() if d.startswith("dataset:action:")]
                self.assertTrue(dispatched)
                for dataset_id in dispatched:
                    index = dataset_id.rsplit(":", 1)[1]
                    decided = store.invocation(f"resolution:{index}").data["decision_watermark_s"]
                    at = store.invocation(f"action:{index}").data["decision_watermark_s"]
                    self.assertAlmostEqual(at - decided, latency, places=9)
                    for receipt in payloads(store, dataset_id):
                        if receipt.kind == "ActionReceipt" and receipt.data["applied_at_s"] is not None:
                            self.assertEqual(receipt.data["applied_at_s"], at)

    def test_a_receipt_cites_only_observations_the_run_exported(self):
        for key, entry in self.runs.items():
            store = entry["store"]
            exported = {o["observation_id"] for d in store.dataset_ids()
                        if d.startswith("dataset:ingest:")
                        for p in payloads(store, d) for o in p.data["observations"]}
            with self.subTest(run=key):
                cited = [i for r in self.receipts(key) for i in r.data["application_observation_ids"]]
                self.assertTrue(cited)
                self.assertLessEqual(set(cited), exported)

    def test_stale_version_is_reachable_only_when_latency_exceeds_the_period(self):
        for key in self.runs:
            codes = [r.data["reason"]["code"] for r in self.receipts(key)
                     if r.data["disposition"] == "rejected"]
            with self.subTest(run=key):
                if key[0] == DELAYED.study_id:
                    self.assertIn("stale_version", codes)
                else:
                    self.assertNotIn("stale_version", codes)

    def test_a_refused_write_changes_nothing(self):
        """The actuator's version counts exactly the writes it applied."""
        for key, entry in self.runs.items():
            applied = sum(r.data["disposition"] == "applied" for r in self.receipts(key))
            with self.subTest(run=key):
                self.assertEqual(entry["model"].path_version["site-1"], applied)

    def test_a_command_is_refused_as_expired_when_dispatch_outlives_it(self):
        """Expiry is checked at dispatch. The study refuses such a latency; an override
        reaches the boundary, which rejects the delivery and the world does not move."""
        entry = self.execute(BASELINE, "planner", latency_s=1.2, label="-expired")
        store = entry["store"]
        self.addCleanup(store.close)
        rejected = [store.dataset(d).data for d in store.dataset_ids()
                    if d.startswith("dataset:action:")
                    and store.dataset(d).data["terminal_status"] == "rejected"]
        self.assertTrue(rejected)
        self.assertTrue(all("stale command" in r["reason"]["detail"] for r in rejected))
        self.assertEqual(entry["model"].path_version["site-1"], 0)

    def test_host_time_is_measured_and_kept_out_of_the_evidence(self):
        again = self.execute(DELAYED, "planner", label="-again")
        self.addCleanup(again["store"].close)
        first = self.runs[(DELAYED.study_id, "planner")]
        self.assertEqual(len(first["run"].host_decision_s), EPOCHS)
        self.assertTrue(all(s > 0 for s in first["run"].host_decision_s))
        # Host time differs between the two runs; the evidence does not.
        self.assertEqual(again["store"].head(), first["store"].head())

    def test_a_command_due_after_the_run_closes_is_reported_in_flight(self):
        entry = self.runs[(DELAYED.study_id, "blackboard")]
        self.assertEqual(entry["run"].undispatched, [EPOCHS - 1])
        self.assertNotIn(f"dataset:action:{EPOCHS - 1}", entry["store"].dataset_ids())
        # The baseline's latency lands every command before the run closes.
        self.assertEqual(self.runs[(BASELINE.study_id, "blackboard")]["run"].undispatched, [])


class ContinuationUnderLatencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def record(self, study, treatment):
        entry = execute(self.temp.name, study, treatment)
        self.addCleanup(entry["store"].close)
        return entry

    def continuation(self, store, study):
        return Continuation(store, build_model=lambda: build_world(SCENARIO),
                            capability_ids=CAPABILITIES,
                            period_s=study.control["decision_period_s"])

    def test_a_prefix_regenerates_with_commands_at_their_dispatch_instants(self):
        entry = self.record(BASELINE, "blackboard")
        for branch in range(1, EPOCHS):
            with self.subTest(branch=branch):
                rebuilt = self.continuation(entry["store"], BASELINE).regenerate(branch)
                # Every write decided before the branch landed before it.
                self.assertEqual(rebuilt.path_version["site-1"],
                                 sum(1 for k in range(branch)
                                     for p in payloads(entry["store"], f"dataset:action:{k}")
                                     if p.kind == "ActionReceipt"
                                     and p.data["disposition"] == "applied"))

    def test_a_branch_is_refused_while_a_command_is_in_flight(self):
        entry = self.record(DELAYED, "blackboard")
        # Blackboard commands every epoch from the first with evidence, and 0.6 s exceeds
        # the 0.5 s period, so some decision is always in flight at a later branch point.
        with self.assertRaises(ContractError) as caught:
            self.continuation(entry["store"], DELAYED).regenerate(EPOCHS - 1)
        self.assertIn("in flight", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
