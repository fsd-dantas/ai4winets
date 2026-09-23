import tempfile
import unittest
from pathlib import Path

from ecora.boundary import Boundary
from ecora.contracts import Record, validate
from ecora.metrics import (claim_churn, coordination_overhead, coordination_starvation,
                           deadlock_epochs, measurements, oscillation, read_run,
                           reasoning_effort, repeated_actions, stability)
from ecora.model import FiniteModel, Link
from ecora.runner import Run, Streams, closed_loop_environment
from ecora.store import ArtifactStore

CAPABILITIES = {("site-1", "queue_occupancy"): "observe.ami.queue",
                ("site-1", "path_state"): "observe.shared.path",
                ("site-1", "pacing_profile"): "observe.ami.pacing",
                ("site-1/lte", "path_probe"): "observe.probe.lte",
                ("site-1/alternative", "path_probe"): "observe.probe.alternative",
                ("site-1", "scada_response"): "observe.scada.response",
                ("site-1/selected_path", "actuator_version"): "observe.shared.path_version",
                ("site-1/pacing_profile", "actuator_version"): "observe.ami.pacing_version"}
LIMITS = {"stability_window_s": 1.0, "action_churn_limit": 2,
          "claim_churn_limit": 4, "stale_retry_limit": 2}
PERIOD = 0.5


def epoch(index, *, applied=(), decisions=(), traces=None, plan=None):
    """A synthetic epoch of recorded evidence, shaped as read_run would return it.

    Decisions imply a proposal that asked for a change unless a plan says otherwise, since
    a refusal only means something when something was requested.
    """
    commands = [{"command_id": f"c{index}:{n}", "target": "site-1", "operator": operator,
                 "arguments": {"path": value}} for n, (operator, value) in enumerate(applied)]
    if plan is None and decisions:
        plan = {"steps": [{"operator": "select_path"}], "estimated_cost": 2}
    return {"index": index, "commands": commands,
            "receipts": [{"command_id": c["command_id"], "disposition": "applied"}
                         for c in commands],
            "decisions": list(decisions), "traces": traces or {},
            **({"plan": plan} if plan else {})}


def decision(proposal_id, disposition):
    return {"proposal_id": proposal_id, "disposition": disposition,
            "reason": {"code": "x", "detail": "y"}, "conflicting_proposal_ids": []}


class BehaviourTests(unittest.TestCase):
    def test_a_setting_returning_to_a_value_it_left_is_a_reversal(self):
        flapping = [epoch(0, applied=[("select_path", "alternative")]),
                    epoch(1, applied=[("select_path", "lte")]),
                    epoch(2, applied=[("select_path", "alternative")])]
        self.assertEqual(oscillation(flapping), 1)
        settling = [epoch(0, applied=[("select_path", "alternative")]),
                    epoch(1, applied=[("select_path", "alternative")])]
        self.assertEqual(oscillation(settling), 0)

    def test_reapplying_a_value_already_held_is_churn_without_change(self):
        repeating = [epoch(i, applied=[("select_path", "alternative")]) for i in range(3)]
        self.assertEqual(repeated_actions(repeating), 2)
        self.assertEqual(oscillation(repeating), 0, "repetition is not oscillation")

    def test_an_epoch_that_refused_every_proposal_is_deadlocked(self):
        stalled = [epoch(0, decisions=[decision("p:a", "defer"), decision("p:b", "defer")]),
                   epoch(1, decisions=[decision("p:a", "admit")]),
                   epoch(2, decisions=[decision("p:a", "defer")])]
        self.assertEqual(deadlock_epochs(stalled), [0, 2])
        # An epoch with no proposals at all is quiet, not deadlocked.
        self.assertEqual(deadlock_epochs([epoch(0)]), [])

    def test_a_settled_controller_is_not_reported_as_stuck(self):
        """A no-op proposal being refused is nothing anyone lost.

        Once its goal holds, a planner proposes no_op and the resolver has nothing to
        issue. Reading that as deadlock or starvation would report a system that had
        finished as one that could not proceed.
        """
        finished = [{**epoch(index, decisions=[decision("p:a", "defer")]),
                     "plan": {"steps": [{"operator": "no_op"}], "estimated_cost": 0}}
                    for index in range(3)]
        self.assertEqual(deadlock_epochs(finished), [])
        self.assertEqual(coordination_starvation(finished)[0], 0)
        # A refused proposal that did ask for a change is still counted.
        blocked = [{**epoch(index, decisions=[decision("p:a", "defer")]),
                    "plan": {"steps": [{"operator": "select_path"}], "estimated_cost": 2}}
                   for index in range(3)]
        self.assertEqual(deadlock_epochs(blocked), [0, 1, 2])
        self.assertEqual(coordination_starvation(blocked)[0], 3)

    def test_coordination_starvation_counts_consecutive_refusals(self):
        history = [epoch(0, decisions=[decision("p:a", "admit"), decision("p:b", "defer")]),
                   epoch(1, decisions=[decision("p:a", "admit"), decision("p:b", "defer")]),
                   epoch(2, decisions=[decision("p:a", "admit"), decision("p:b", "defer")]),
                   epoch(3, decisions=[decision("p:a", "defer"), decision("p:b", "admit")])]
        worst, per_agent = coordination_starvation(history)
        self.assertEqual(worst, 3)
        self.assertEqual(per_agent["p:b"], 3)
        self.assertEqual(per_agent["p:a"], 1)

    def test_starvation_follows_the_agent_not_the_proposal_identity(self):
        """A fresh proposal id each epoch must not reset an agent's wait."""
        renamed = [{**epoch(index, decisions=[decision(f"proposal:{index}", "defer")]),
                    "proposals": {f"proposal:{index}": "agent:site-1:ami"}}
                   for index in range(4)]
        worst, per_agent = coordination_starvation(renamed)
        self.assertEqual(worst, 4)
        self.assertEqual(per_agent, {"agent:site-1:ami": 4})

    def test_service_starvation_is_reported_unknown_rather_than_guessed(self):
        values, _ = measurements([epoch(0)], LIMITS, PERIOD)
        service = next(m for m in values if m["metric"] == "service_starvation_s")
        self.assertIsNone(service["value"])
        self.assertEqual(service["quality"], "unknown")

    def test_stability_ignores_service_and_reports_its_own_bounds(self):
        quiet = [epoch(i) for i in range(2)]
        settled, detail = stability(quiet, LIMITS, PERIOD)
        self.assertTrue(settled)
        self.assertEqual(detail["action_changes"], 0)
        busy = [epoch(0, applied=[("select_path", "alternative")]),
                epoch(1, applied=[("select_path", "lte")]),
                epoch(2, applied=[("select_path", "alternative")])]
        settled, detail = stability(busy, {**LIMITS, "action_churn_limit": 1}, PERIOD)
        self.assertFalse(settled)
        self.assertGreater(detail["action_changes"], 1)

    def test_an_incomplete_window_yields_no_stability_verdict(self):
        settled, detail = stability([epoch(0)], {**LIMITS, "stability_window_s": 10.0}, PERIOD)
        self.assertIsNone(settled, "a partial window must not be scored as stable")
        self.assertIn("no full stability window", detail["reason"])

    def test_the_measurements_fit_a_result_record(self):
        values, _ = measurements([epoch(0, applied=[("select_path", "alternative")])],
                                 LIMITS, PERIOD)
        window = {"start_s": 0, "end_s": 1}
        validate("ResultRecord", {
            "before_window": window, "after_window": window, "cohorts": [],
            "measurements": values, "action_ids": [], "uncertainty": "Synthetic."})


class RecordedRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def run_one(self, treatment, name, epochs=4):
        model = FiniteModel(
            sites=["site-1"],
            links={"lte": Link("lte", 1000000, 0.010, 65536),
                   "alternative": Link("alternative", 1000000, 0.010, 65536)},
            egress=Link("egress", 256000, 0.001, 65536),
            scada_period_s=0.1, ami_period_s=1.0, scada_bytes=512, ami_bytes=512,
            scada_deadline_s=0.25, ami_deadline_s=10.0)
        registry, study, scenario_set, scenario, caps = closed_loop_environment(
            model, period_s=PERIOD)
        store = ArtifactStore(Path(self.temp.name) / name)
        self.addCleanup(store.close)
        run = registry.admit(study, scenario_set, scenario, caps, treatment, f"run:{name}")
        boundary = Boundary(store, registry, run)
        Run(boundary, model, streams=Streams(study.data["seed_manifest"]),
            capability_ids=CAPABILITIES, period_s=PERIOD, epochs=epochs,
            assembly=study.data["assembly"]).execute()
        return read_run(store, epochs)

    def test_it_measures_a_recorded_run_from_its_evidence_alone(self):
        recorded = self.run_one("eco", "recorded")
        effort = reasoning_effort(recorded)
        self.assertGreater(effort["activations"], 0, "the expert arm reasoned")
        overhead = coordination_overhead(recorded)
        self.assertEqual(overhead["transport"], "ideal_local")
        self.assertGreater(overhead["mark_writes"], 0)
        values, report = measurements(recorded, LIMITS, PERIOD)
        self.assertIn("no service outcome is consulted", report["note"])
        self.assertTrue(all(m["quality"] in ("measured", "unknown") for m in values))

    def test_it_reads_the_churn_the_two_planners_actually_differ_by(self):
        """The Null planner reapplies its switch; the symbolic planner stops."""
        repeating = self.run_one("blackboard", "churn-null")
        settling = self.run_one("eco", "churn-planned")
        self.assertGreater(repeated_actions(repeating), repeated_actions(settling))
        # Neither flaps: repetition is not the same failure as oscillation.
        self.assertEqual(oscillation(repeating), 0)
        self.assertEqual(oscillation(settling), 0)


if __name__ == "__main__":
    unittest.main()
