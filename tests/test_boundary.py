from functools import partial
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ecora.boundary import Boundary
from ecora.contracts import ContractError, Record, canonical, decode, digest
from ecora.fixtures import (batch, command, fixture_environment, observation, planning_problem,
                            reason, result_input)
from ecora.registry import ProviderResult
from ecora.store import ArtifactStore


class OutcomeProvider:
    def __init__(self, mode):
        self.mode = mode

    def invoke(self, inputs, prior, context):
        if self.mode == "error":
            raise RuntimeError("Synthetic provider failure")
        if self.mode == "timeout":
            raise TimeoutError("Synthetic timeout")
        if self.mode == "bad_output":
            return ProviderResult((command(),), {}, {})
        if self.mode == "bad_state":
            return ProviderResult((), {"bad": float("nan")}, {})
        if self.mode == "bad_terminal":
            return ProviderResult((Record("BoundaryOutcome", {"status": "no_op", "reason": reason()}),), {}, {})
        if self.mode == "fake_privilege":
            obs = observation(evidence_kind="simulator_truth", privileged_source_refs=["truth:invented"])
            return ProviderResult((batch("TelemetryBatch", [obs]),), {}, {})
        return ProviderResult((), {}, {}, self.mode, None if self.mode == "ok" else reason())


def replace_provider(environment, stage, factory):
    registry, study, scenario_set, scenario, caps = environment
    data = study.data
    binding = next(b for b in data["treatments"][0]["bindings"] if b["stage_id"] == stage)
    spec = Record("ProviderSpec", registry.resolve(binding).spec.data | {"provider_id": f"fixture.test.{stage}"})
    registry.register(spec, factory)
    binding["provider_id"] = spec.data["provider_id"]
    return registry, Record("StudyManifest", data), scenario_set, scenario, caps


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def setup_boundary(self, environment=None, name="main", treatment="reference", run_id="run:fixture"):
        registry, study, scenario_set, scenario, caps = environment or fixture_environment()
        root = Path(self.temp.name) / name
        store = ArtifactStore(root)
        self.addCleanup(store.close)
        run = registry.admit(study, scenario_set, scenario, caps, treatment, run_id)
        return store, Boundary(store, registry, run)

    def source(self, boundary, suffix="", payload=None, watermark=0):
        return boundary.ingest(f"source{suffix}", batch() if payload is None else payload, watermark_s=watermark)

    def test_configuration_substitution_changes_provider_without_orchestration_change(self):
        labels = []
        for treatment in ("reference", "substitution"):
            store, boundary = self.setup_boundary(name=treatment, treatment=treatment, run_id=f"run:{treatment}")
            source = self.source(boundary)
            telemetry = boundary.invoke("telemetry", "t", [source.data["dataset_id"]], watermark_s=0)
            result = boundary.invoke("diagnosis", "d", [telemetry.data["dataset_id"]], watermark_s=0)
            self.assertEqual(result.data["terminal_status"], "ok")
            payload = Record.from_dict(store.messages(result.data["dataset_id"])[0].data["payload"])
            labels.append(payload.data["hypotheses"][0]["label"])
            self.assertEqual(result.data["source_dataset_ids"], [telemetry.data["dataset_id"]])
            self.assertEqual(store.verify()["datasets"], 3)
        self.assertEqual(labels, ["fixture_a", "fixture_b"])

    def test_all_seven_stages_compose_through_assembled_inputs(self):
        store, boundary = self.setup_boundary()
        source = self.source(boundary)
        stages = {"harness": source.data["dataset_id"]}
        stages["telemetry"] = boundary.invoke(
            "telemetry", "t", [stages["harness"]], watermark_s=0).data["dataset_id"]
        stages["diagnosis"] = boundary.invoke(
            "diagnosis", "d", [stages["telemetry"]], watermark_s=0).data["dataset_id"]
        # Planning consumes a PlanningProblem built from the retained DiagnosisRecord.
        stages["problem"] = boundary.assemble(
            "assemble-plan", "planning", [stages["diagnosis"]], planning_problem(),
            watermark_s=0).data["dataset_id"]
        stages["planning"] = boundary.invoke(
            "planning", "p", [stages["problem"]], watermark_s=0).data["dataset_id"]
        stages["resolution"] = boundary.invoke(
            "resolution", "r", [stages["planning"]], watermark_s=0).data["dataset_id"]
        stages["action"] = boundary.invoke(
            "action", "a", [stages["resolution"]], watermark_s=0).data["dataset_id"]
        stages["cohorts"] = boundary.assemble(
            "assemble-result", "result", [stages["action"]], result_input(),
            watermark_s=0).data["dataset_id"]
        stages["result"] = boundary.invoke(
            "result", "res", [stages["cohorts"]], watermark_s=0).data["dataset_id"]
        stages["assurance"] = boundary.invoke(
            "assurance", "as", [stages["result"]], watermark_s=0).data["dataset_id"]
        for name, dataset_id in stages.items():
            with self.subTest(stage=name):
                self.assertEqual(store.dataset(dataset_id).data["terminal_status"], "ok")
        report = Record.from_dict(store.messages(stages["assurance"])[0].data["payload"])
        self.assertEqual(report.kind, "AssuranceReport")
        self.assertEqual(report.data["claims"][0]["verdict"], "inconclusive")
        self.assertEqual(report.data["contributing_run_ids"], ["run:fixture"])

    def test_null_arm_runs_every_stage_and_reports_inconclusively(self):
        store, boundary = self.setup_boundary(treatment="null_baseline", run_id="run:null")
        source = self.source(boundary)
        datasets = {}
        datasets["telemetry"] = boundary.invoke(
            "telemetry", "n-t", [source.data["dataset_id"]], watermark_s=0).data["dataset_id"]
        datasets["diagnosis"] = boundary.invoke(
            "diagnosis", "n-d", [datasets["telemetry"]], watermark_s=0).data["dataset_id"]
        datasets["problem"] = boundary.assemble(
            "n-assemble-plan", "planning", [datasets["diagnosis"]], planning_problem(),
            watermark_s=0).data["dataset_id"]
        datasets["planning"] = boundary.invoke(
            "planning", "n-p", [datasets["problem"]], watermark_s=0).data["dataset_id"]
        datasets["resolution"] = boundary.invoke(
            "resolution", "n-r", [datasets["planning"]], watermark_s=0).data["dataset_id"]
        datasets["action"] = boundary.invoke(
            "action", "n-a", [datasets["resolution"]], watermark_s=0).data["dataset_id"]
        datasets["cohorts"] = boundary.assemble(
            "n-assemble-result", "result", [datasets["action"]], result_input(),
            watermark_s=0).data["dataset_id"]
        datasets["result"] = boundary.invoke(
            "result", "n-res", [datasets["cohorts"]], watermark_s=0).data["dataset_id"]
        datasets["assurance"] = boundary.invoke(
            "assurance", "n-as", [datasets["result"]], watermark_s=0).data["dataset_id"]
        for stage, dataset_id in datasets.items():
            with self.subTest(stage=stage):
                self.assertEqual(store.dataset(dataset_id).data["terminal_status"], "ok")
                self.assertEqual(store.dataset(dataset_id).data["arm"],
                                 "null" if stage in ("telemetry", "diagnosis", "planning",
                                                     "resolution", "action", "result",
                                                     "assurance") else "proposed")

        def payload(stage, index=0):
            return Record.from_dict(store.messages(datasets[stage])[index].data["payload"])

        # Null telemetry declares zero coverage and names what it withheld.
        telemetry = payload("telemetry")
        self.assertEqual(telemetry.data["observations"], [])
        self.assertEqual(telemetry.data["completeness"], 0)
        self.assertEqual(telemetry.data["omitted_metrics"], ["queue_occupancy"])
        # A first-candidate guess carries no supporting evidence.
        hypothesis = payload("diagnosis").data["hypotheses"][0]
        self.assertEqual(hypothesis["label"], "queue_pressure")
        self.assertEqual((hypothesis["status"], hypothesis["support_ids"]), ("unknown", []))
        # A one-step plan is structurally valid while leaving the goal unmet.
        plan = payload("planning")
        self.assertEqual(len(plan.data["steps"]), 1)
        self.assertEqual(plan.data["goal_status"], "unmet")
        # The mutation is admitted, then suppressed rather than applied.
        self.assertEqual(payload("resolution").data["decisions"][0]["disposition"], "admit")
        receipt = payload("action")
        self.assertEqual(receipt.data["disposition"], "suppressed")
        self.assertIsNone(receipt.data["applied_at_s"])
        # No service outcome is extracted and no requirement is decided.
        self.assertEqual(payload("result").data["measurements"], [])
        report = payload("assurance")
        self.assertEqual([c["verdict"] for c in report.data["claims"]], ["inconclusive"])
        self.assertEqual(report.data["contributing_dataset_ids"], [datasets["result"]])

    def test_null_resolution_cannot_act_without_precondition_evidence(self):
        store, boundary = self.setup_boundary(treatment="null_baseline", run_id="run:null2")
        source = self.source(boundary)
        problem = boundary.assemble("n2-assemble", "planning", [source.data["dataset_id"]],
                                    planning_problem(known_predicates=[]), watermark_s=0)
        planning = boundary.invoke("planning", "n2-p", [problem.data["dataset_id"]], watermark_s=0)
        resolution = boundary.invoke("resolution", "n2-r", [planning.data["dataset_id"]], watermark_s=0)
        record = Record.from_dict(store.messages(resolution.data["dataset_id"])[0].data["payload"])
        self.assertEqual(record.data["command_ids"], [])
        self.assertEqual(record.data["decisions"][0]["disposition"], "defer")
        self.assertEqual(len(store.messages(resolution.data["dataset_id"])), 1)

    def test_assembled_input_cannot_depart_from_the_frozen_study(self):
        store, boundary = self.setup_boundary()
        source = self.source(boundary)
        departures = [
            ("planning", planning_problem(goals=["selected_lte"]), "goals"),
            ("planning", planning_problem(expansion_budget=999), "expansion_budget"),
            ("planning", planning_problem(action_costs={"select_path": 99}), "action_costs"),
            ("result", result_input(cohorts=[{
                "cohort_id": "cohort:ami", "service": "ami",
                "generation_window": {"start_s": 0, "end_s": 5},
                "generated": 1, "delivered_on_time": 0, "delivered_late": 0, "lost": 0,
                "pending": 1, "duplicate_deliveries": 0, "censored": True, "deadline_s": 10}]),
             "window"),
        ]
        for index, (destination, payload, label) in enumerate(departures):
            with self.subTest(field=label), self.assertRaises(ContractError):
                boundary.assemble(f"depart-{index}", destination,
                                  [source.data["dataset_id"]], payload, watermark_s=0)
        # Only the measured counts are free to vary from run to run.
        accepted = boundary.assemble("counted", "result", [source.data["dataset_id"]],
                                     result_input(), watermark_s=0)
        self.assertEqual(accepted.data["terminal_status"], "ok")

    def test_records_the_next_stage_cannot_consume_terminate_as_evidence(self):
        store, boundary = self.setup_boundary()
        source = self.source(boundary)
        telemetry = boundary.invoke("telemetry", "t", [source.data["dataset_id"]], watermark_s=0)
        diagnosis = boundary.invoke("diagnosis", "d", [telemetry.data["dataset_id"]], watermark_s=0)
        message = store.messages(diagnosis.data["dataset_id"])[0]
        self.assertEqual(Record.from_dict(message.data["payload"]).kind, "DiagnosisRecord")
        self.assertEqual(message.data["destination_stage"], "sink")

    def test_delivery_completion_is_per_consumer(self):
        store, boundary = self.setup_boundary()
        source = self.source(boundary)
        telemetry = boundary.invoke("telemetry", "t", [source.data["dataset_id"]], watermark_s=0)
        resolution = boundary.invoke("resolution", "r", [telemetry.data["dataset_id"]], watermark_s=0)
        messages = store.messages(resolution.data["dataset_id"])
        self.assertGreaterEqual(len(messages), 1)
        invocation = messages[0].data["stage_invocation_id"]
        for index, message in enumerate(messages):
            store.deliver(message, f"consumer-{index}", lambda m: None,
                          destination=message.data["destination_stage"], watermark_s=0)
        if len(messages) > 1:
            self.assertNotEqual(store._states[invocation], "Delivered")

    def test_every_terminal_alternative_is_durable(self):
        expected = {"ok": "empty", "empty": "empty", "no_op": "no_op", "rejected": "rejected",
                    "error": "error", "timeout": "timeout", "bad_output": "rejected",
                    "bad_state": "rejected", "bad_terminal": "rejected"}
        for mode, outcome in expected.items():
            with self.subTest(mode=mode):
                env = replace_provider(fixture_environment(), "telemetry", partial(OutcomeProvider, mode))
                store, boundary = self.setup_boundary(env, name=mode)
                source = self.source(boundary)
                result = boundary.invoke("telemetry", "terminal", [source.data["dataset_id"]], watermark_s=0)
                self.assertEqual(result.data["terminal_status"], outcome)
                messages = store.messages(result.data["dataset_id"])
                self.assertEqual(len(messages), 1)
                payload = Record.from_dict(messages[0].data["payload"])
                self.assertEqual(payload.kind, "BoundaryOutcome")
                self.assertEqual(payload.data["status"], outcome)
                root = store.root
                store.close()
                with ArtifactStore(root) as reopened:
                    self.assertEqual(reopened.dataset(result.data["dataset_id"]), result)
                    self.assertEqual(reopened.verify()["datasets"], 2)

    def test_unavailable_input_is_rejected_before_provider_sees_it(self):
        store, boundary = self.setup_boundary()
        source = self.source(boundary, payload=batch(watermark=2), watermark=2)
        result = boundary.invoke("telemetry", "future", [source.data["dataset_id"]], watermark_s=1)
        self.assertEqual(result.data["terminal_status"], "rejected")
        self.assertIn("unavailable", result.data["reason"]["detail"])

    def test_stale_command_cannot_reach_action_provider(self):
        store, boundary = self.setup_boundary()
        source = boundary.ingest("command-source", command(), destination="action", watermark_s=0)
        result = boundary.invoke("action", "expired", [source.data["dataset_id"]], watermark_s=2)
        self.assertEqual(result.data["terminal_status"], "rejected")
        self.assertIn("stale", result.data["reason"]["detail"])

    def test_distinct_invocations_cannot_dispatch_same_command_twice(self):
        store, boundary = self.setup_boundary()
        source = boundary.ingest("command-source", command(), destination="action", watermark_s=0)
        first = boundary.invoke("action", "first-action", [source.data["dataset_id"]], watermark_s=0)
        second = boundary.invoke("action", "duplicate-action", [source.data["dataset_id"]], watermark_s=0)
        self.assertEqual(first.data["terminal_status"], "ok")
        self.assertEqual(second.data["terminal_status"], "rejected")
        self.assertIn("idempotency", second.data["reason"]["detail"])
        self.assertEqual(sum(e["event"] == "DispatchIntent" for e in store._events), 1)
        root = store.root
        store.close()
        with ArtifactStore(root) as reopened:
            b2 = Boundary(reopened, boundary.registry, boundary.run)
            third = b2.invoke("action", "restart-action", [source.data["dataset_id"]], watermark_s=0)
            self.assertEqual(third.data["terminal_status"], "rejected")

    def test_local_observation_scope_cannot_be_forged(self):
        store, boundary = self.setup_boundary()
        for change in ({"subject": "site-2"}, {"service": "scada"}, {"capability_id": "unknown"}):
            with self.subTest(change=change), self.assertRaises(ContractError):
                self.source(boundary, payload=batch(observations=[observation(**change)]))
        self.assertEqual(store.verify()["datasets"], 0)

    def test_duplicate_invocation_does_not_execute_again(self):
        store, boundary = self.setup_boundary()
        source = self.source(boundary)
        boundary.invoke("telemetry", "same", [source.data["dataset_id"]], watermark_s=0)
        with self.assertRaises(ContractError):
            boundary.invoke("telemetry", "same", [source.data["dataset_id"]], watermark_s=0)
        self.assertEqual(store.verify()["datasets"], 2)

    def test_duplicate_delivery_is_suppressed_after_restart(self):
        store, boundary = self.setup_boundary()
        source = self.source(boundary)
        message = store.messages(source.data["dataset_id"])[0]
        effects = []
        self.assertTrue(store.deliver(message, "consumer", effects.append, destination="telemetry", watermark_s=0))
        self.assertFalse(store.deliver(message, "consumer", effects.append, destination="telemetry", watermark_s=0))
        root = store.root
        store.close()
        with ArtifactStore(root) as reopened:
            self.assertFalse(reopened.deliver(message, "consumer", effects.append, destination="telemetry", watermark_s=0))
        self.assertEqual(len(effects), 1)

    def test_unknown_delivery_is_not_retried_and_out_of_order_is_rejected(self):
        store, boundary = self.setup_boundary()
        first = self.source(boundary, "a")
        second = self.source(boundary, "b")
        m1, m2 = (store.messages(ds.data["dataset_id"])[0] for ds in (first, second))
        with self.assertRaises(ContractError):
            store.deliver(m2, "consumer", lambda m: None, destination="telemetry", watermark_s=0)
        calls = []
        def interrupted(message):
            calls.append(message)
            raise RuntimeError("after external effect")
        with self.assertRaises(RuntimeError):
            store.deliver(m1, "consumer", interrupted, destination="telemetry", watermark_s=0)
        with self.assertRaises(ContractError):
            store.deliver(m1, "consumer", interrupted, destination="telemetry", watermark_s=0)
        self.assertEqual(len(calls), 1)

    def test_delivery_checks_destination_and_availability(self):
        store, boundary = self.setup_boundary()
        source = self.source(boundary, payload=batch(watermark=1), watermark=1)
        message = store.messages(source.data["dataset_id"])[0]
        for dest, time in (("action", 1), ("telemetry", 0)):
            with self.assertRaises(ContractError):
                store.deliver(message, "consumer", lambda m: None, destination=dest, watermark_s=time)

    def test_privilege_is_transitive_through_ordinary_provider_and_state(self):
        truth_cap = {"capability_id": "truth.ami.queue", "kind": "truth", "target": "site-1", "service": "ami",
                     "name": "queue_occupancy", "unit": "byte", "evidence_refs": ["fixture:truth"]}
        env = fixture_environment(allow_privileged=True, extra_capabilities=(truth_cap,))
        store, boundary = self.setup_boundary(env)
        truth = observation(capability_id=truth_cap["capability_id"], evidence_kind="simulator_truth",
                            privileged_source_refs=["truth:current:0"])
        source = self.source(boundary, payload=batch(observations=[truth]))
        telemetry = boundary.invoke("telemetry", "privileged-t", [source.data["dataset_id"]], watermark_s=0)
        self.assertEqual(telemetry.data["terminal_status"], "ok")
        result = boundary.invoke("diagnosis", "privileged-d", [telemetry.data["dataset_id"]], watermark_s=0)
        self.assertEqual(result.data["terminal_status"], "ok")
        self.assertEqual(result.data["information_regime"], "oracle_state")
        self.assertEqual(result.data["privileged_source_refs"], ["truth:current:0"])
        inv = store.get(store._invocations["privileged-d"])
        state_hash = inv.data["next_state_hash"]
        later = boundary.invoke("diagnosis", "privileged-state", [], watermark_s=0, prior_state_hash=state_hash)
        self.assertEqual(later.data["privileged_source_refs"], ["truth:current:0"])
        message = store.messages(result.data["dataset_id"])[0]
        with self.assertRaises(ContractError):
            store.deliver(message, "ordinary", lambda m: None, destination="planning", watermark_s=0)

    def test_privileged_input_denied_and_invented_truth_rejected(self):
        truth_cap = {"capability_id": "truth.ami.queue", "kind": "truth", "target": "site-1", "service": "ami",
                     "name": "queue_occupancy", "unit": "byte", "evidence_refs": ["fixture:truth"]}
        store, boundary = self.setup_boundary(fixture_environment(extra_capabilities=(truth_cap,)))
        truth = observation(capability_id=truth_cap["capability_id"], evidence_kind="simulator_truth",
                            privileged_source_refs=["truth:current:0"])
        source = self.source(boundary, payload=batch(observations=[truth]))
        result = boundary.invoke("telemetry", "denied", [source.data["dataset_id"]], watermark_s=0)
        self.assertEqual(result.data["terminal_status"], "rejected")
        self.assertEqual(result.data["privileged_source_refs"], ["truth:current:0"])
        env = replace_provider(fixture_environment(), "telemetry", partial(OutcomeProvider, "fake_privilege"))
        _, boundary2 = self.setup_boundary(env, name="fake")
        source2 = self.source(boundary2)
        result2 = boundary2.invoke("telemetry", "fake", [source2.data["dataset_id"]], watermark_s=0)
        self.assertEqual(result2.data["terminal_status"], "rejected")

    def test_corrupt_object_and_truncated_journal_are_detected(self):
        store, boundary = self.setup_boundary()
        source = self.source(boundary)
        path = store.objects / f"{source.content_hash}.json"
        path.write_bytes(b"{}")
        # An ordinary read is served from the record cache and does not revalidate, so a
        # file whose contents changed underneath the process survives it. Detecting that
        # is the audit's job, and a reopen's; both must refuse this store.
        self.assertEqual(store.get(source.content_hash), source)
        with self.assertRaises(ContractError):
            store.verify()
        root = store.root
        store.close()
        with self.assertRaises(ContractError):
            ArtifactStore(root)
        store2, _ = self.setup_boundary(name="truncated")
        root2 = store2.root
        store2.close()
        with (root2 / "journal.jsonl").open("ab") as stream:
            stream.write(b'{"partial":')
        with self.assertRaises(ContractError):
            ArtifactStore(root2)

    def test_deleted_ancestor_invalidates_downstream_consumption(self):
        store, boundary = self.setup_boundary()
        source = self.source(boundary)
        telemetry = boundary.invoke("telemetry", "telemetry", [source.data["dataset_id"]], watermark_s=0)
        ancestor_message = store.messages(source.data["dataset_id"])[0]
        (store.objects / f"{ancestor_message.content_hash}.json").unlink()
        with self.assertRaises(ContractError):
            boundary.invoke("diagnosis", "dangling", [telemetry.data["dataset_id"]], watermark_s=0)
        self.assertEqual(store._events[-1]["event"], "IntegrityFailure")

    def test_writer_lock_and_partial_invocation_quarantine(self):
        store, boundary = self.setup_boundary()
        with self.assertRaises(ContractError):
            ArtifactStore(store.root)
        store.append("InputRecorded", {"invocation_id": "unfinished", "input_dataset_ids": [], "record_hashes": []})
        store.append("Started", {"invocation_id": "unfinished"})
        root = store.root
        store.close()
        with self.assertRaises(ContractError):
            ArtifactStore(root)

    def test_journal_write_failure_prevents_provider_execution(self):
        store, boundary = self.setup_boundary()
        source = self.source(boundary)
        with patch("ecora.store.os.fsync", side_effect=OSError("synthetic disk failure")):
            with self.assertRaises(OSError):
                boundary.invoke("telemetry", "disk-failure", [source.data["dataset_id"]], watermark_s=0)
        self.assertEqual(len(store._datasets), 1)

    def test_cross_run_input_logged_as_integrity_failure(self):
        store, boundary = self.setup_boundary()
        source = self.source(boundary)
        run = boundary.registry.admit(boundary.run.study, boundary.run.scenario_set, boundary.run.scenario,
                                     boundary.run.capabilities, "reference", "run:other")
        other = Boundary(store, boundary.registry, run)
        with self.assertRaises(ContractError):
            other.invoke("telemetry", "cross-run", [source.data["dataset_id"]], watermark_s=0)
        self.assertEqual(store._events[-1]["event"], "IntegrityFailure")
        self.assertEqual(len(store._datasets), 1)
