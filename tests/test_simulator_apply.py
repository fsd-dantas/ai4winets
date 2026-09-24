import tempfile
import unittest
from pathlib import Path

from ecora.__main__ import CAPABILITIES
from ecora.boundary import Boundary
from ecora.contracts import Record
from ecora.runner import Run, Streams, closed_loop_environment
from ecora.scenario import SCENARIOS, build_world, load
from ecora.simulator import Ns3World
from ecora.store import ArtifactStore
from ecora.study import resolve

try:
    from test_simulator_adapter import AVAILABLE
except ImportError:
    from tests.test_simulator_adapter import AVAILABLE

KNOWLEDGE = resolve("baseline")
COMMANDS = {
    "switch": {"operator": "select_path", "target": "site-1", "arguments": {"path": "alternative"},
               "expected_state_version": 0},
    "unknown_path": {"operator": "select_path", "target": "site-1", "arguments": {"path": "satellite"},
                     "expected_state_version": 0},
    "unknown_target": {"operator": "select_path", "target": "site-9", "arguments": {"path": "lte"}},
    "restrict": {"operator": "set_ami_pacing", "target": "site-1", "arguments": {"profile": "restricted"},
                 "expected_state_version": 0},
    "unknown_profile": {"operator": "set_ami_pacing", "target": "site-1", "arguments": {"profile": "fast"},
                        "expected_state_version": 0},
    "missing_version": {"operator": "select_path", "target": "site-1", "arguments": {"path": "lte"}},
    "stale_version": {"operator": "select_path", "target": "site-1", "arguments": {"path": "lte"},
                      "expected_state_version": 7},
    "stale_pacing": {"operator": "set_ami_pacing", "target": "site-1",
                     "arguments": {"profile": "minimum"}, "expected_state_version": 0},
    "unsupported": {"operator": "publish_mark", "target": "site-1", "arguments": {}},
    "no_op": {"operator": "no_op", "target": "site-1", "arguments": {}},
}


def run(world, scenario, treatment, epochs, knowledge=KNOWLEDGE):
    registry, study, scenario_set, frozen, caps = closed_loop_environment(
        world, period_s=0.5, scenario=scenario, study=knowledge)
    with ArtifactStore(Path(tempfile.mkdtemp()) / treatment) as store:
        admitted = registry.admit(study, scenario_set, frozen, caps, treatment, f"run:{treatment}")
        Run(Boundary(store, registry, admitted), world,
            streams=Streams(study.data["seed_manifest"]), capability_ids=CAPABILITIES,
            period_s=0.5, epochs=epochs, assembly=study.data["assembly"],
            predicate_map=knowledge.predicate_map).execute()
        # An epoch whose dispatch fell after the run closed has no action dataset.
        dispatched = set(store.dataset_ids())
        receipts = [Record.from_dict(m.data["payload"]).data for i in range(epochs)
                    if f"dataset:action:{i}" in dispatched
                    for m in store.messages(f"dataset:action:{i}")
                    if Record.from_dict(m.data["payload"]).kind == "ActionReceipt"]
    return receipts


class ReceiptTests(unittest.TestCase):
    def test_a_receipt_states_the_actuators_readback_and_never_reads_truth(self):
        """Truth is the privileged channel; a receipt must not need it."""
        scenario = load(SCENARIOS / "s2-silent-primary.json")
        world = build_world(scenario)

        def refused():
            raise AssertionError("an ordinary action provider read simulator truth")
        world.truth = refused
        receipts = run(world, scenario, "planner", epochs=4)
        applied = [r for r in receipts if r["disposition"] == "applied"]
        self.assertTrue(applied)
        self.assertEqual(applied[-1]["resulting_state"], world.actuator_state()["selected_path"])


@unittest.skipUnless(AVAILABLE, "no ns-3 simulator build is available on this host")
class ApplyTests(unittest.TestCase):
    """The simulator applies the catalog as the finite world does, and says so."""

    def test_both_worlds_apply_and_refuse_the_same_commands_alike(self):
        scenario = load(SCENARIOS / "s0-nominal.json")
        finite = build_world(scenario).advance_to(1.0)
        with Ns3World.start(scenario) as simulated:
            simulated.advance_to(1.0)
            for name, command in COMMANDS.items():
                with self.subTest(command=name):
                    self.assertEqual(simulated.apply(command), finite.apply(command))
            self.assertEqual(simulated.actuator_state(), finite.actuator_state())

    def test_an_applied_command_is_what_later_evidence_shows(self):
        with Ns3World.start(load(SCENARIOS / "s0-nominal.json")) as world:
            world.advance_to(1.0)
            self.assertEqual(world.apply(COMMANDS["switch"]), (True, None))
            self.assertEqual(world.apply(COMMANDS["restrict"]), (True, None))
            world.advance_to(1.5)
            seen = {o["metric"]: o["value"] for o in world.observations(capability_ids={
                ("site-1", "path_state"): "observe.shared.path",
                ("site-1", "pacing_profile"): "observe.ami.pacing"})}
        self.assertEqual(seen, {"path_state": "alternative", "pacing_profile": "restricted"})

    def test_an_admitted_switch_changes_the_world_and_a_suppressed_one_does_not(self):
        """Adapter acceptance 2, in the simulator: the consequence is measured, not assumed."""
        scenario = load(SCENARIOS / "s2-silent-primary.json")
        window = [{"cohort_id": "c", "service": "scada", "deadline_s": 0,
                   "generation_window": {"start_s": 1.0, "end_s": 4.0}}]
        outcomes = {}
        for treatment in ("null_baseline", "planner"):
            with Ns3World.start(scenario) as world:
                receipts = run(world, scenario, treatment, epochs=10)
                cohort = world.cohorts(window)[0]
                outcomes[treatment] = (world.actuator_state(), receipts,
                                       cohort["delivered_on_time"] / cohort["generated"])
        null_state, null_receipts, null_ratio = outcomes["null_baseline"]
        state, receipts, ratio = outcomes["planner"]
        self.assertEqual((null_state["selected_path"]["site-1"], null_state["path_version"]["site-1"]),
                         ("lte", 0), "suppression leaves the actuator where it was")
        self.assertFalse([r for r in null_receipts if r["disposition"] == "applied"])
        self.assertEqual(state["selected_path"]["site-1"], "alternative")
        applied = [r for r in receipts if r["disposition"] == "applied"]
        self.assertEqual(applied[-1]["resulting_state"], state["selected_path"])
        self.assertEqual(null_ratio, 0.0)
        self.assertEqual(ratio, 1.0, "SCADA recovers once the switch is applied")

    def test_a_decision_overtaken_in_flight_is_refused_stale_in_both_worlds(self):
        """B25: with dispatch 0.6 s after a 0.5 s epoch, the next decision reads the version
        the first has not yet changed. Both worlds apply one and refuse the other, alike."""
        scenario = load(SCENARIOS / "s1-degraded-primary.json")
        delayed = resolve("delayed-control")

        def outcome(receipts):
            return [(r["disposition"], r["applied_at_s"],
                     r["reason"]["code"] if r["reason"] else None) for r in receipts]
        finite = build_world(scenario)
        expected = outcome(run(finite, scenario, "planner", 6, delayed))
        with Ns3World.start(scenario) as world:
            simulated = outcome(run(world, scenario, "planner", 6, delayed))
            state = world.actuator_state()
        self.assertIn("stale_version", [code for _, _, code in expected])
        self.assertEqual(simulated, expected)
        self.assertEqual(state["path_version"]["site-1"],
                         sum(d == "applied" for d, _, _ in simulated))


if __name__ == "__main__":
    unittest.main()
