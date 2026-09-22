import tempfile
import unittest
from pathlib import Path

from ecora.boundary import Boundary
from ecora.contracts import ContractError, Record
from ecora.model import FiniteModel, Link
from ecora.runner import Run, Streams, closed_loop_environment
from ecora.store import ArtifactStore

CAPABILITIES = {("site-1", "queue_occupancy"): "observe.ami.queue",
                ("site-1", "path_state"): "observe.shared.path",
                ("site-1/lte", "path_probe"): "observe.probe.lte",
                ("site-1/alternative", "path_probe"): "observe.probe.alternative"}
PERIOD = 0.5
EPOCHS = 4


def world():
    return FiniteModel(
        sites=["site-1"],
        links={"lte": Link("lte", 1000000, 0.010, 65536),
               "alternative": Link("alternative", 1000000, 0.010, 65536)},
        egress=Link("egress", 256000, 0.001, 65536),
        scada_period_s=0.1, ami_period_s=1.0, scada_bytes=512, ami_bytes=512,
        scada_deadline_s=0.25, ami_deadline_s=10.0)


class StreamTests(unittest.TestCase):
    def test_controller_draws_do_not_move_the_exogenous_streams(self):
        plan = {"seed": 7}
        quiet, busy = Streams(plan), Streams(plan)
        for _ in range(500):
            busy["controller"].random()
        self.assertEqual([quiet["arrivals"].random() for _ in range(20)],
                         [busy["arrivals"].random() for _ in range(20)])
        self.assertEqual([quiet["disturbances"].random() for _ in range(20)],
                         [busy["disturbances"].random() for _ in range(20)])

    def test_streams_are_distinct_and_reproducible_from_the_seed_plan(self):
        first, second = Streams({"seed": 7}), Streams({"seed": 7})
        self.assertEqual(first["arrivals"].random(), second["arrivals"].random())
        self.assertNotEqual(Streams({"seed": 7})["arrivals"].random(),
                            Streams({"seed": 8})["arrivals"].random())
        plan = Streams({"seed": 7})
        self.assertNotEqual(plan["arrivals"].random(), plan["errors"].random())

    def test_an_undeclared_stream_is_refused(self):
        with self.assertRaises(ContractError):
            Streams({"seed": 1})["telepathy"]


class RunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def execute(self, treatment, name, run_id, cache_records=8192):
        model = world()
        registry, study, scenario_set, scenario, caps = closed_loop_environment(model, period_s=PERIOD)
        store = ArtifactStore(Path(self.temp.name) / name, cache_records=cache_records)
        self.addCleanup(store.close)
        run = registry.admit(study, scenario_set, scenario, caps, treatment, run_id)
        boundary = Boundary(store, registry, run)
        dataset = Run(boundary, model, streams=Streams(study.data["seed_manifest"]),
                      capability_ids=CAPABILITIES, period_s=PERIOD, epochs=EPOCHS,
                      assembly=study.data["assembly"]).execute()
        return store, model, dataset

    def test_a_run_produces_a_traceable_report(self):
        store, _, dataset = self.execute("null_baseline", "trace", "run:trace")
        report = Record.from_dict(store.messages(dataset)[0].data["payload"])
        self.assertEqual(report.kind, "AssuranceReport")
        self.assertEqual(report.data["contributing_run_ids"], ["run:trace"])
        # Every claim resolves to the frozen benchmark it was measured against.
        self.assertEqual(report.data["scenario_set_version"], "1")
        # The whole lineage is reachable from the final dataset.
        self.assertEqual(store.dataset(dataset).data["terminal_status"], "ok")
        integrity = store.verify()
        self.assertGreater(integrity["datasets"], EPOCHS)
        self.assertEqual(report.data["claims"][0]["verdict"], "inconclusive")

    def test_two_runs_of_the_same_treatment_are_byte_identical(self):
        first, _, _ = self.execute("null_baseline", "repeat-a", "run:repeat")
        second, _, _ = self.execute("null_baseline", "repeat-b", "run:repeat")
        self.assertEqual(first.head(), second.head())

    def test_only_an_arm_that_concluded_from_evidence_can_act(self):
        """A mutation needs precondition evidence, and a Null diagnosis supplies none.

        The closed-loop arm binds the action stage to the world but reasons with the Null
        diagnosis, whose first-candidate guess carries no support. It therefore cannot act,
        and that is the contract holding rather than a missing capability.
        """
        suppressed_store, suppressed_model, _ = self.execute("closed_loop", "open", "run:open")
        applied_store, applied_model, _ = self.execute("expert", "closed", "run:closed")
        # No evidence-backed conclusion, so no command and no mutation.
        self.assertEqual(suppressed_model.truth()["selected_path"]["site-1"], "lte")
        self.assertEqual(suppressed_model.path_version["site-1"], 0)
        # The arm that reasons over relayed evidence reaches and applies a command.
        self.assertEqual(applied_model.truth()["selected_path"]["site-1"], "alternative")
        self.assertGreater(applied_model.path_version["site-1"], 0)
        # The two runs differ in evidence as well as in what the world ended up doing.
        self.assertNotEqual(suppressed_store.head(), applied_store.head())

    def test_an_applied_receipt_cites_evidence_the_run_actually_exports(self):
        store, model, _ = self.execute("expert", "evidence", "run:evidence")
        receipts = []
        for index in range(EPOCHS):
            dataset = store.dataset(f"dataset:action:{index}")
            for message in store.messages(dataset.data["dataset_id"]):
                payload = Record.from_dict(message.data["payload"])
                if payload.kind == "ActionReceipt" and payload.data["disposition"] == "applied":
                    receipts.append(payload.data)
        self.assertTrue(receipts, "the closed loop should apply at least one command")
        exported = set()
        for label in (*range(EPOCHS), "closing"):
            for message in store.messages(f"dataset:ingest:{label}"):
                batch = Record.from_dict(message.data["payload"])
                exported.update(o["observation_id"] for o in batch.data["observations"])
        for receipt in receipts:
            for observation_id in receipt["application_observation_ids"]:
                self.assertIn(observation_id, exported)

    def probed(self, name, disturbances=(), treatment="eco", epochs=3):
        model = FiniteModel(
            sites=["site-1"],
            links={"lte": Link("lte", 1000000, 0.010, 65536),
                   "alternative": Link("alternative", 1000000, 0.010, 65536)},
            egress=Link("egress", 256000, 0.001, 65536),
            scada_period_s=0.1, ami_period_s=1.0, scada_bytes=512, ami_bytes=512,
            scada_deadline_s=0.25, ami_deadline_s=10.0, disturbances=disturbances)
        registry, study, scenario_set, scenario, caps = closed_loop_environment(
            model, period_s=PERIOD)
        store = ArtifactStore(Path(self.temp.name) / name)
        self.addCleanup(store.close)
        run = registry.admit(study, scenario_set, scenario, caps, treatment, f"run:{name}")
        boundary = Boundary(store, registry, run)
        Run(boundary, model, streams=Streams(study.data["seed_manifest"]),
            capability_ids=CAPABILITIES, period_s=PERIOD, epochs=epochs,
            assembly=study.data["assembly"]).execute()
        return store, model

    def test_a_probed_leg_can_be_switched_to_and_an_unprobed_one_cannot(self):
        """The whole chain: probe, diagnosis, projection, plan, command, world.

        With both legs answering, the planner reaches the goal and the switch is applied.
        Take the alternative leg's service away and its probe stops answering, so its
        reachability is unknown, the edge is prohibited and nothing is applied. Only that
        leg is refused: the one still answering stays viable.
        """
        store, model = self.probed("probe-healthy")
        problem = Record.from_dict(
            store.messages("dataset:assemble-planning:0")[0].data["payload"]).data
        plan = Record.from_dict(store.messages("dataset:planning:0")[0].data["payload"]).data
        self.assertEqual(problem["unknown_predicates"], [])
        self.assertEqual(plan["goal_status"], "achieved_in_model")
        self.assertEqual(model.truth()["selected_path"]["site-1"], "alternative")

        silent, unmoved = self.probed(
            "probe-silent",
            disturbances=({"at_s": 0.0, "site": "site-1", "leg": "alternative", "rate_bps": 0},))
        problem = Record.from_dict(
            silent.messages("dataset:assemble-planning:0")[0].data["payload"]).data
        plan = Record.from_dict(silent.messages("dataset:planning:0")[0].data["payload"]).data
        self.assertEqual(problem["unknown_predicates"], ["reachable:site-1:alternative"])
        self.assertIn("reachable:site-1:lte", problem["known_predicates"])
        self.assertEqual(plan["goal_status"], "unknown")
        self.assertEqual([step["operator"] for step in plan["steps"]], ["no_op"])
        self.assertEqual(unmoved.truth()["selected_path"]["site-1"], "lte")
        self.assertEqual(unmoved.path_version["site-1"], 0)

    def test_the_showcase_runs_and_reports_every_arm(self):
        """It is demonstrated live, so a silent break is worse than a slow test."""
        import io
        from contextlib import redirect_stdout
        from ecora.__main__ import main
        captured = io.StringIO()
        with redirect_stdout(captured):
            main(["showcase", str(Path(self.temp.name) / "showcase"), "--epochs", "2"])
        printed = captured.getvalue()
        for expected in ("null_baseline", "closed_loop", "observing", "expert", "blackboard",
                         "relayed", "concluded", "activations",
                         "differs from the one above it in exactly one binding", "Provenance",
                         "Nothing here is a network result"):
            with self.subTest(expected=expected):
                self.assertIn(expected, printed)
        # Each step of the chain must name the single binding that changed.
        self.assertIn("null.action -> model.action", printed)
        self.assertIn("null.telemetry -> telemetry.projection", printed)
        self.assertIn("null.diagnosis -> experts.single_engine", printed)
        self.assertIn("experts.single_engine -> experts.blackboard", printed)
        # The RQ-E comparison is the point of the last two rows.
        self.assertIn("conclusions agree : True", printed)
        self.assertIn("single_engine", printed)
        # The arms must actually diverge, or the demonstration shows nothing.
        self.assertIn("lte", printed)
        self.assertIn("alternative", printed)

    def test_the_showcase_refuses_to_overwrite_an_existing_directory(self):
        from ecora.__main__ import main
        target = Path(self.temp.name) / "twice"
        (target / "observing").mkdir(parents=True)
        with self.assertRaises(SystemExit):
            main(["showcase", str(target)])

    def test_the_record_cache_is_transparent_to_the_evidence(self):
        """A cache too small to hold the working set must change nothing but the timing."""
        cached, _, _ = self.execute("expert", "cache-warm", "run:cache")
        cold, _, _ = self.execute("expert", "cache-cold", "run:cache", cache_records=1)
        self.assertEqual(cached.head(), cold.head())
        self.assertEqual(cached.verify(), cold.verify())

    def test_stage_state_carries_forward_between_epochs(self):
        store, _, _ = self.execute("null_baseline", "state", "run:state")
        previous = store.invocation("diagnosis:0").data["next_state_hash"]
        for index in range(1, EPOCHS):
            invocation = store.invocation(f"diagnosis:{index}")
            self.assertEqual(invocation.data["prior_state_hash"], previous)
            previous = invocation.data["next_state_hash"]


if __name__ == "__main__":
    unittest.main()
