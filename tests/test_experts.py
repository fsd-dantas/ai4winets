import tempfile
import unittest
from pathlib import Path

from ecora.boundary import Boundary
from ecora.contracts import ContractError, Record
from ecora.experts import expert_binding
from ecora.fixtures import observation
from ecora.model import FiniteModel, Link
from ecora.registry import Registry
from ecora.store import ArtifactStore
from ecora.runner import RULES, closed_loop_environment

PERIOD = 0.5


def world():
    return FiniteModel(
        sites=["site-1"],
        links={"lte": Link("lte", 1000000, 0.010, 65536),
               "alternative": Link("alternative", 1000000, 0.010, 65536)},
        egress=Link("egress", 256000, 0.001, 65536),
        scada_period_s=0.1, ami_period_s=1.0, scada_bytes=512, ami_bytes=512,
        scada_deadline_s=0.25, ami_deadline_s=10.0)


def queue(value):
    return observation(observation_id="observation:queue", metric="queue_occupancy",
                       unit="byte", value=value, capability_id="observe.ami.queue")


def path(value):
    return observation(observation_id="observation:path", subject="site-1", service="shared",
                       metric="path_state", unit="id", value=value,
                       capability_id="observe.shared.path", valid_min=None, valid_max=None)


def absent(metric, unit, capability, service="ami"):
    return observation(observation_id=f"observation:{metric}:unknown", metric=metric, unit=unit,
                       value=None, quality="missing", capability_id=capability, service=service,
                       valid_min=None, valid_max=None,
                       missing_reason={"code": "absent", "detail": "Not supplied."})


class ExpertTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.counter = 0

    def diagnose(self, observations, treatment, *, rules=None, name=None):
        """Feed one immutable snapshot straight to the diagnosis stage."""
        self.counter += 1
        label = name or f"{treatment}{self.counter}"
        registry, study, scenario_set, scenario, caps = closed_loop_environment(
            world(), period_s=PERIOD, rules=rules)
        store = ArtifactStore(Path(self.temp.name) / label)
        self.addCleanup(store.close)
        run = registry.admit(study, scenario_set, scenario, caps, treatment, f"run:{label}")
        boundary = Boundary(store, registry, run)
        batch = Record("TelemetryBatch", {
            "observations": observations, "watermark_s": 0,
            "window": {"start_s": 0, "end_s": 0}, "sequence": 0,
            "completeness": 1 if all(o["quality"] != "missing" for o in observations) else 0,
            "omitted_metrics": sorted({o["metric"] for o in observations if o["quality"] == "missing"})})
        source = boundary.ingest("ingest", batch, destination="diagnosis", watermark_s=0)
        result = boundary.invoke("diagnosis", "diagnosis", [source.data["dataset_id"]], watermark_s=0)
        if result.data["terminal_status"] != "ok":
            return result, None
        return result, Record.from_dict(store.messages(result.data["dataset_id"])[0].data["payload"])

    def labels(self, record):
        return sorted(h["label"] for h in record.data["hypotheses"])

    def test_both_organisations_agree_on_every_snapshot(self):
        """RQ-E's first clause. It can fail: the two run different scheduling entirely."""
        snapshots = {
            "nominal_primary": [queue(1024), path("lte")],
            "nominal_alternative": [queue(1024), path("alternative")],
            "pressure_alternative": [queue(50000), path("alternative")],
            "queue_unknown": [absent("queue_occupancy", "byte", "observe.ami.queue"), path("lte")],
        }
        for name, observations in snapshots.items():
            with self.subTest(snapshot=name):
                _, single = self.diagnose(observations, "expert", name=f"e-{name}")
                _, board = self.diagnose(observations, "blackboard", name=f"b-{name}")
                self.assertEqual(self.labels(single), self.labels(board))
                self.assertEqual([h["status"] for h in single.data["hypotheses"]],
                                 [h["status"] for h in board.data["hypotheses"]])

    def test_their_orchestration_cost_differs(self):
        """RQ-E's second clause, read from the trace rather than assumed."""
        observations = [queue(1024), path("alternative")]
        _, single = self.diagnose(observations, "expert", name="cost-single")
        _, board = self.diagnose(observations, "blackboard", name="cost-board")
        single_trace, board_trace = single.data["rule_trace"][0], board.data["rule_trace"][0]
        self.assertEqual(single_trace["organisation"], "single_engine")
        self.assertEqual(board_trace["organisation"], "blackboard")
        self.assertNotEqual((single_trace["activations"], single_trace["passes"]),
                            (board_trace["activations"], board_trace["passes"]))

    def test_a_chained_rule_waits_for_its_premises(self):
        _, settled = self.diagnose([queue(1024), path("alternative")], "expert", name="chain-yes")
        self.assertIn("settled_on_alternative_path", self.labels(settled))
        # Under pressure the premise is not concluded, so the chained rule cannot fire.
        _, pressed = self.diagnose([queue(50000), path("alternative")], "expert", name="chain-no")
        self.assertIn("local_queue_pressure", self.labels(pressed))
        self.assertNotIn("settled_on_alternative_path", self.labels(pressed))

    def test_unknown_evidence_is_not_read_as_a_negative(self):
        """A rule whose input is missing is unknown, never false."""
        _, record = self.diagnose(
            [absent("queue_occupancy", "byte", "observe.ami.queue"), path("lte")],
            "expert", name="unknown")
        labels = self.labels(record)
        # Neither queue conclusion may be drawn from an absent measurement.
        self.assertNotIn("local_queue_pressure", labels)
        self.assertNotIn("local_queue_nominal", labels)
        self.assertIn("on_primary_path", labels)

    def test_no_evaluable_rule_yields_an_explicit_insufficient_evidence(self):
        _, record = self.diagnose(
            [absent("queue_occupancy", "byte", "observe.ami.queue"),
             absent("path_state", "id", "observe.shared.path", "shared")],
            "expert", name="nothing")
        self.assertEqual(self.labels(record), ["insufficient_evidence"])
        self.assertEqual(record.data["hypotheses"][0]["status"], "unknown")
        self.assertEqual(record.data["hypotheses"][0]["support_ids"], [])

    def test_a_contradiction_is_settled_by_priority_and_recorded(self):
        rules = {"activation_budget": 50, "rules": [
            {"rule_id": "weak", "requires": ["queue_occupancy"],
             "condition": {"metric": "queue_occupancy", "op": "ge", "value": 0},
             "concludes": "quiet", "priority": 1, "contradicts": ["busy"],
             "explanation": "Low priority."},
            {"rule_id": "strong", "requires": ["queue_occupancy"],
             "condition": {"metric": "queue_occupancy", "op": "ge", "value": 0},
             "concludes": "busy", "priority": 9, "contradicts": ["quiet"],
             "explanation": "High priority."}]}
        for treatment in ("expert", "blackboard"):
            with self.subTest(treatment=treatment):
                _, record = self.diagnose([queue(1024)], treatment, rules=rules,
                                          name=f"priority-{treatment}")
                self.assertEqual(self.labels(record), ["busy"])
                self.assertEqual(record.data["unresolved_conflicts"], [])
                inhibited = record.data["rule_trace"][0]["inhibited"]
                self.assertTrue(any(entry["reason"] == "lower_priority" for entry in inhibited))

    def test_equal_authority_on_a_contradiction_stays_unresolved(self):
        rules = {"activation_budget": 50, "rules": [
            {"rule_id": "left", "requires": ["queue_occupancy"],
             "condition": {"metric": "queue_occupancy", "op": "ge", "value": 0},
             "concludes": "quiet", "priority": 5, "contradicts": ["busy"],
             "explanation": "Equal authority."},
            {"rule_id": "right", "requires": ["queue_occupancy"],
             "condition": {"metric": "queue_occupancy", "op": "ge", "value": 0},
             "concludes": "busy", "priority": 5, "contradicts": ["quiet"],
             "explanation": "Equal authority."}]}
        for treatment in ("expert", "blackboard"):
            with self.subTest(treatment=treatment):
                _, record = self.diagnose([queue(1024)], treatment, rules=rules,
                                          name=f"tie-{treatment}")
                self.assertEqual(record.data["unresolved_conflicts"], ["left", "right"])
                # Neither contradictory conclusion is asserted as supported.
                self.assertNotIn("quiet", self.labels(record))

    def test_an_exhausted_activation_budget_is_a_typed_refusal(self):
        rules = {"activation_budget": 2, "rules": RULES["rules"]}
        for treatment in ("expert", "blackboard"):
            with self.subTest(treatment=treatment):
                result, record = self.diagnose([queue(1024), path("lte")], treatment,
                                               rules=rules, name=f"budget-{treatment}")
                self.assertEqual(result.data["terminal_status"], "rejected")
                self.assertEqual(result.data["reason"]["code"], "activation_budget")

    def test_a_rule_inventory_is_checked_before_it_is_bound(self):
        duplicate = {"rules": [dict(RULES["rules"][0]), dict(RULES["rules"][0])]}
        with self.assertRaises(ContractError):
            expert_binding(Registry(), ["observe.ami.queue"], duplicate)
        mistyped = {"rules": [{**RULES["rules"][0],
                               "condition": {"metric": "queue_occupancy", "op": "approximately",
                                             "value": 1}}]}
        with self.assertRaises(ContractError):
            expert_binding(Registry(), ["observe.ami.queue"], mistyped)
        untested = {"rules": [{**RULES["rules"][0], "requires": ["path_state"]}]}
        with self.assertRaises(ContractError):
            expert_binding(Registry(), ["observe.ami.queue"], untested)
        with self.assertRaises(ContractError):
            expert_binding(Registry(), ["observe.ami.queue"], {"rules": []})


if __name__ == "__main__":
    unittest.main()
