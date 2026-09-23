import copy
import tempfile
import unittest
from pathlib import Path

from ecora.__main__ import CAPABILITIES
from ecora.boundary import Boundary
from ecora.contracts import Record
from ecora.runner import Run, Streams, closed_loop_environment, observation_batch
from ecora.scenario import SCENARIOS, build_world, load
from ecora.simulator import Ns3World, SimulatorClient, SimulatorRefusal
from ecora.store import ArtifactStore
from ecora.study import resolve

try:
    from test_simulator_adapter import AVAILABLE, BUILD, Stub
except ImportError:
    from tests.test_simulator_adapter import AVAILABLE, BUILD, Stub


class AdapterTests(unittest.TestCase):
    """What the adapter does with grants and identities, without a simulator."""

    def test_grants_travel_in_order_and_identities_use_the_shared_scheme(self):
        exported = [{"subject": "site-1", "metric": "path_state", "value": "lte"},
                    {"subject": "site-1/lte", "metric": "path_probe", "value": 0.02}]

        def answer(request):
            result = {"observations": exported} if request["kind"] == "observe" else {}
            return {"request_id": request["request_id"], "kind": request["kind"],
                    "build_id": BUILD, "status": "ok", "result": result}
        stub = Stub(answer)
        world = Ns3World.__new__(Ns3World)
        world.client, world.now = SimulatorClient(stub, stub, BUILD), 1.5
        grants = {("site-1", "path_state"): "observe.shared.path",
                  ("site-1/lte", "path_probe"): "observe.probe.lte"}
        observed = world.observations(capability_ids=grants, window_s=0.5)
        self.assertEqual(stub.requests[0]["grants"],
                         [{"subject": "site-1", "metric": "path_state",
                           "capability_id": "observe.shared.path"},
                          {"subject": "site-1/lte", "metric": "path_probe",
                           "capability_id": "observe.probe.lte"}])
        self.assertEqual([o["observation_id"] for o in observed],
                         ["observation:site-1:path_state:1.5",
                          "observation:site-1/lte:path_probe:1.5"])


@unittest.skipUnless(AVAILABLE, "no ns-3 simulator build is available on this host")
class ObserveTests(unittest.TestCase):
    """The simulator's evidence, held to the same telemetry contract as the finite world's."""

    def test_every_scenario_exports_contract_valid_evidence(self):
        for path in sorted(SCENARIOS.glob("s*.json")):
            with self.subTest(scenario=path.stem), Ns3World.start(load(path)) as world:
                for at in (0.5, 2.0):
                    world.advance_to(at)
                    batch = observation_batch(world, CAPABILITIES, at, 0.5, 0).data
                    self.assertEqual(len(batch["observations"]), len(CAPABILITIES))

    def test_only_what_is_granted_is_exported(self):
        with Ns3World.start(load(SCENARIOS / "s0-nominal.json")) as world:
            world.advance_to(1.0)
            observed = world.observations(
                capability_ids={("site-1/lte", "path_probe"): "observe.probe.lte"})
        self.assertEqual([(o["subject"], o["metric"], o["capability_id"]) for o in observed],
                         [("site-1/lte", "path_probe", "observe.probe.lte")])

    def test_a_signal_or_subject_the_world_does_not_hold_is_refused(self):
        with Ns3World.start(load(SCENARIOS / "s0-nominal.json")) as world:
            world.advance_to(1.0)
            for grants, code in (({("site-1", "link_measurement"): "x"}, "unsupported_signal"),
                                 ({("site-9", "path_state"): "x"}, "unknown_subject"),
                                 ({("site-1/satellite", "path_probe"): "x"}, "unknown_subject")):
                with self.subTest(code=code), self.assertRaises(SimulatorRefusal) as caught:
                    world.observations(capability_ids=grants)
                self.assertEqual(caught.exception.code, code)

    def test_a_silent_leg_answers_no_probe_and_a_live_one_does(self):
        with Ns3World.start(load(SCENARIOS / "s2-silent-primary.json")) as world:
            world.advance_to(3.0)
            by_leg = {o["subject"]: o for o in world.observations(capability_ids={
                ("site-1/lte", "path_probe"): "observe.probe.lte",
                ("site-1/alternative", "path_probe"): "observe.probe.alternative"})}
        self.assertEqual(by_leg["site-1/lte"]["quality"], "missing")
        self.assertEqual(by_leg["site-1/lte"]["missing_reason"]["code"], "probe_timeout")
        alternative = by_leg["site-1/alternative"]
        self.assertEqual(alternative["quality"], "observed")
        self.assertLess(alternative["value"], 0.15)
        self.assertLessEqual(alternative["window"]["end_s"], alternative["event_time_s"])

    def test_the_local_queue_is_measured_on_the_alternative_and_derived_on_lte(self):
        base = load(SCENARIOS / "s0-nominal.json").data
        for path, kind in (("lte", "derived"), ("alternative", "measured")):
            data = copy.deepcopy(base)
            data["topology"]["initial_path"] = path
            with self.subTest(path=path), Ns3World.start(data) as world:
                world.advance_to(1.0)
                queue, = world.observations(
                    capability_ids={("site-1", "queue_occupancy"): "observe.ami.queue"})
                self.assertEqual(queue["evidence_kind"], kind)
                self.assertEqual(queue["formula"] is not None, kind == "derived")


@unittest.skipUnless(AVAILABLE, "no ns-3 simulator build is available on this host")
class PipelineTests(unittest.TestCase):
    """The decision pipeline, unchanged, over the simulator's evidence."""

    def run_treatment(self, world, scenario, treatment, epochs=4):
        knowledge = resolve("baseline")
        registry, study, scenario_set, frozen, caps = closed_loop_environment(
            world, period_s=0.5, scenario=scenario, study=knowledge)
        directory = tempfile.mkdtemp()
        with ArtifactStore(Path(directory) / treatment) as store:
            run = registry.admit(study, scenario_set, frozen, caps, treatment, f"run:{treatment}")
            Run(Boundary(store, registry, run), world,
                streams=Streams(study.data["seed_manifest"]), capability_ids=CAPABILITIES,
                period_s=0.5, epochs=epochs, assembly=study.data["assembly"],
                predicate_map=knowledge.predicate_map).execute()
            diagnoses = []
            for index in range(epochs):
                payload = Record.from_dict(store.messages(f"dataset:diagnosis:{index}")[0].data["payload"])
                diagnoses.append(sorted(h["label"] for h in payload.data["hypotheses"]
                                        if h["status"] == "supported"))
            action = [store.dataset(f"dataset:action:{i}").data["terminal_status"]
                      for i in range(epochs)]
        return diagnoses, action

    def test_both_worlds_reach_the_same_diagnosis_from_their_own_evidence(self):
        """Same rules, each world's own evidence at the same moments, nobody acting.

        Compared without actuation because the finite world can apply a switch the
        simulator cannot yet, after which the two worlds are rightly in different states.
        """
        from ecora.experts import expert_binding
        from ecora.registry import Registry

        class Message:
            def __init__(self, record):
                self.data = {"payload": record.to_dict()}

        class Snapshot:
            data = {"state": {}}

        class Context:
            def __init__(self, configuration, watermark):
                self.data = {"configuration": configuration, "decision_watermark_s": watermark}

        rules = resolve("baseline").rules

        def diagnose(world, at):
            batch = Record("TelemetryBatch", observation_batch(world, CAPABILITIES, at, 0.5, 0).data)
            registry = Registry()
            binding = expert_binding(registry, [], rules, "blackboard")
            result = registry.resolve(binding).factory().invoke(
                [Message(batch)], Snapshot(), Context(binding["configuration"], at))
            return sorted(h["label"] for h in result.outputs[0].data["hypotheses"]
                          if h["status"] == "supported")

        # Including the transition: at S2's disturbance, 1.0 s, both worlds still hold the
        # last acknowledged probe as evidence, because both probes are real traffic with the
        # same timeout and validity. Before B22a the finite probe saw the silence at once.
        for name in ("s0-nominal", "s2-silent-primary"):
            scenario = load(SCENARIOS / f"{name}.json")
            finite = build_world(scenario)
            with self.subTest(scenario=name), Ns3World.start(scenario) as simulated:
                for at in (0.5, 1.0, 1.2, 2.0, 3.0):
                    finite.advance_to(at)
                    simulated.advance_to(at)
                    self.assertEqual(diagnose(finite, at), diagnose(simulated, at), f"at {at} s")

    def test_the_pipelines_decision_is_applied_in_the_simulator(self):
        """Before B23 this switch was refused; the simulator now applies it."""
        scenario = load(SCENARIOS / "s2-silent-primary.json")
        with Ns3World.start(scenario) as world:
            _, action = self.run_treatment(world, scenario, "blackboard")
            state = world.actuator_state()
        self.assertNotIn("rejected", action)
        self.assertEqual(state["selected_path"]["site-1"], "alternative")


if __name__ == "__main__":
    unittest.main()
