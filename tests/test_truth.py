import tempfile
import unittest
from pathlib import Path

from ecora.boundary import Boundary
from ecora.contracts import ContractError, Record
from ecora.model import FiniteModel, Link
from ecora.runner import ORACLE, Run, Streams, closed_loop_environment
from ecora.store import ArtifactStore
from ecora.truth import TruthPort, truth_binding

CAPABILITIES = {("site-1", "queue_occupancy"): "observe.ami.queue",
                ("site-1", "path_state"): "observe.shared.path",
                ("site-1", "pacing_profile"): "observe.ami.pacing",
                ("site-1/lte", "path_probe"): "observe.probe.lte",
                ("site-1/alternative", "path_probe"): "observe.probe.alternative"}
PERIOD = 0.5

TRUTHS = [{"capability_id": "truth.ami.queue_occupancy", "kind": "truth", "target": "site-1",
           "service": "ami", "name": "queue_occupancy", "unit": "byte",
           "evidence_refs": ["fixture:truth"]},
          {"capability_id": "truth.shared.path_state", "kind": "truth", "target": "site-1",
           "service": "shared", "name": "path_state", "unit": "id",
           "evidence_refs": ["fixture:truth"]}]
OBSERVE = [{"capability_id": "observe.ami.queue", "kind": "observe", "target": "site-1",
            "service": "ami", "name": "queue_occupancy", "unit": "byte",
            "evidence_refs": ["fixture:observation"]}]


def world():
    return FiniteModel(
        sites=["site-1"],
        links={"lte": Link("lte", 1000000, 0.010, 65536),
               "alternative": Link("alternative", 1000000, 0.010, 65536)},
        egress=Link("egress", 256000, 0.001, 65536),
        scada_period_s=0.1, ami_period_s=1.0, scada_bytes=512, ami_bytes=512,
        scada_deadline_s=0.25, ami_deadline_s=10.0)


class PortTests(unittest.TestCase):
    def setUp(self):
        self.model = world().advance_to(1.0)
        self.port = TruthPort(self.model, [*TRUTHS, *OBSERVE])

    def test_it_opens_only_what_a_truth_capability_grants(self):
        self.assertEqual(self.port.granted(),
                         ["truth.ami.queue_occupancy", "truth.shared.path_state"])
        # An observe capability is not a key to the truth port.
        with self.assertRaises(ContractError) as caught:
            self.port.read("observe.ami.queue", 1.0)
        self.assertIn("no truth capability grants", str(caught.exception))
        with self.assertRaises(ContractError):
            self.port.read("truth.ami.everything", 1.0)

    def test_it_serves_the_present_and_refuses_the_future_and_the_past(self):
        self.port.read("truth.shared.path_state", 1.0)
        for at in (1.5, 0.5, 0.0):
            with self.subTest(at=at), self.assertRaises(ContractError) as caught:
                self.port.read("truth.shared.path_state", at)
            self.assertIn("current state only", str(caught.exception))

    def test_a_read_is_exact_current_state_and_carries_its_lineage(self):
        observation = self.port.read("truth.shared.path_state", 1.0)
        self.assertEqual(observation["value"], self.model.truth()["selected_path"]["site-1"])
        self.assertEqual(observation["evidence_kind"], "simulator_truth")
        self.assertEqual(observation["privileged_source_refs"],
                         ["truth:path_state:site-1:1.0"])
        self.assertIn("not deployable evidence", observation["assumptions"][0])

    def test_every_read_is_logged(self):
        self.port.read("truth.shared.path_state", 1.0)
        self.port.read("truth.ami.queue_occupancy", 1.0)
        self.assertEqual([entry["name"] for entry in self.port.log],
                         ["path_state", "queue_occupancy"])
        accounting = self.port.accounting()
        self.assertEqual((accounting["reads"], accounting["regime"]), (2, "oracle_state"))
        self.assertIn("not evidence any controller could obtain", accounting["note"])

    def test_the_port_holds_nothing_a_future_could_be_read_from(self):
        """It projects current state, so there is no schedule or calendar in it to peek at."""
        exposed = set(self.model.truth())
        for forbidden in ("calendar", "disturbances", "schedule", "random", "future"):
            self.assertNotIn(forbidden, exposed)
        self.assertFalse(hasattr(self.port, "_calendar"))


class OracleArmTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def run_arm(self, treatment, name, epochs=2):
        model = world()
        registry, study, scenario_set, scenario, caps = closed_loop_environment(
            model, period_s=PERIOD)
        store = ArtifactStore(Path(self.temp.name) / name)
        self.addCleanup(store.close)
        run = registry.admit(study, scenario_set, scenario, caps, treatment, f"run:{name}")
        boundary = Boundary(store, registry, run)
        Run(boundary, model, streams=Streams(study.data["seed_manifest"]),
            capability_ids=CAPABILITIES, period_s=PERIOD, epochs=epochs,
            assembly=study.data["assembly"]).execute()
        return store, model, registry, study

    def test_truth_taints_every_stage_downstream_of_it(self):
        """A provider cannot shed the label by emitting an otherwise ordinary record."""
        store, _, _, _ = self.run_arm("oracle", "tainted")
        for stage in ("telemetry", "diagnosis", "planning", "resolution", "action"):
            with self.subTest(stage=stage):
                dataset = store.dataset(f"dataset:{stage}:0").data
                self.assertEqual(dataset["information_regime"], "oracle_state")
                self.assertTrue(dataset["privileged_source_refs"])
        self.assertEqual(store.dataset("dataset:assurance").data["information_regime"],
                         "oracle_state")

    def test_the_contract_limited_arm_stays_unprivileged(self):
        store, _, _, _ = self.run_arm("eco", "clean")
        for stage in ("telemetry", "diagnosis", "action"):
            dataset = store.dataset(f"dataset:{stage}:0").data
            self.assertEqual(dataset["information_regime"], "contract_only")
            self.assertEqual(dataset["privileged_source_refs"], [])

    def test_the_oracle_relays_exact_truth_where_the_projection_relays_evidence(self):
        privileged, model, _, _ = self.run_arm("oracle", "exact")
        ordinary, _, _, _ = self.run_arm("eco", "evidenced")

        def relayed(store):
            payload = Record.from_dict(
                store.messages("dataset:telemetry:0")[0].data["payload"]).data
            return {o["metric"]: o["evidence_kind"] for o in payload["observations"]}

        self.assertTrue(all(kind == "simulator_truth" for kind in relayed(privileged).values()))
        self.assertTrue(all(kind == "measured" for kind in relayed(ordinary).values()))

    def test_truth_cannot_be_handed_to_an_ordinary_provider(self):
        """Two guards, and either alone would be enough to refuse it.

        Editing a binding's capabilities is caught because they must match the registered
        provider spec. Registering a spec that legitimately holds truth and then binding
        it at contract_only is caught because truth and an ordinary regime cannot coexist.
        """
        registry, study, scenario_set, scenario, caps = closed_loop_environment(
            world(), period_s=PERIOD)
        edited = study.data
        treatment = next(t for t in edited["treatments"] if t["treatment_id"] == "eco")
        binding = next(b for b in treatment["bindings"] if b["stage_id"] == "diagnosis")
        binding["capability_ids"] = sorted([*binding["capability_ids"],
                                            "truth.ami.queue_occupancy"])
        with self.assertRaises(ContractError) as caught:
            registry.admit(Record("StudyManifest", edited), scenario_set, scenario, caps,
                           "eco", "run:edited")
        self.assertIn("binding/spec mismatch", str(caught.exception))

        registry, study, scenario_set, scenario, caps = closed_loop_environment(
            world(), period_s=PERIOD)
        declared = study.data
        treatment = next(t for t in declared["treatments"] if t["treatment_id"] == "eco")
        binding = next(b for b in treatment["bindings"] if b["stage_id"] == "diagnosis")
        spec = Record("ProviderSpec", {
            "stage_id": "diagnosis", "provider_id": binding["provider_id"],
            "provider_version": "smuggled-v1", "arm": binding["arm"],
            "input_types": binding["input_types"], "output_types": binding["output_types"],
            "state_schema_version": "1",
            "capability_ids": sorted([*binding["capability_ids"], "truth.ami.queue_occupancy"]),
            "direct_truth_access": False})
        registry.register(spec, lambda: None)
        binding.update({"provider_version": "smuggled-v1",
                        "capability_ids": spec.data["capability_ids"]})
        with self.assertRaises(ContractError) as caught:
            registry.admit(Record("StudyManifest", declared), scenario_set, scenario, caps,
                           "eco", "run:declared")
        self.assertIn("truth capability granted to ordinary provider", str(caught.exception))

    def test_an_oracle_cannot_declare_a_read_it_was_not_granted(self):
        from ecora.registry import Registry
        port = TruthPort(world(), TRUTHS)
        with self.assertRaises(ContractError) as caught:
            truth_binding(Registry(), port, ["truth.ami.queue_occupancy"],
                          {"reads": ["truth.ami.everything"]})
        self.assertIn("no truth capability grants", str(caught.exception))
        with self.assertRaises(ContractError):
            truth_binding(Registry(), port, [], {"reads": []})


if __name__ == "__main__":
    unittest.main()
