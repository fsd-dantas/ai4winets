import tempfile
import unittest
from pathlib import Path

from ecora.boundary import Boundary
from ecora.contracts import ContractError, Record
from ecora.model import FiniteModel, Link
from ecora.runner import ORACLE, ORACLE_READS, Run, Streams, closed_loop_environment
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

    def test_a_diagnosis_oracle_cannot_shed_the_label_by_its_output_type(self):
        """A DiagnosisRecord carries no observations, and must still be tainted.

        Harvesting lineage from the payload would work for telemetry and silently fail for
        a diagnosis, a plan or a receipt. A truth-holding provider declares what it read,
        so the label follows the access rather than the shape of the output.
        """
        store, _, _, _ = self.run_arm("oracle_diagnosis", "labelled")
        diagnosis = store.dataset("dataset:diagnosis:0").data
        self.assertEqual(diagnosis["information_regime"], "oracle_state")
        self.assertEqual(len(diagnosis["privileged_source_refs"]), len(ORACLE_READS))
        # And it reaches everything downstream of it.
        for stage in ("planning", "resolution", "action"):
            with self.subTest(stage=stage):
                self.assertEqual(store.dataset(f"dataset:{stage}:0").data["information_regime"],
                                 "oracle_state")

    def test_a_truth_holding_provider_that_declares_no_read_is_refused(self):
        from ecora.registry import ProviderResult
        registry, study, scenario_set, scenario, caps = closed_loop_environment(
            world(), period_s=PERIOD)
        binding = next(b for t in study.data["treatments"] if t["treatment_id"] == "oracle"
                       for b in t["bindings"] if b["stage_id"] == "telemetry")
        entry = registry.resolve(binding)
        object.__setattr__(entry, "factory",
                           lambda: type("Silent", (), {"invoke": lambda self, *a: ProviderResult(
                               (), {}, {"organisation": "oracle_state"})})())
        store = ArtifactStore(Path(self.temp.name) / "silent")
        self.addCleanup(store.close)
        run = registry.admit(study, scenario_set, scenario, caps, "oracle", "run:silent")
        boundary = Boundary(store, registry, run)
        result = boundary.invoke("telemetry", "telemetry:0", [], watermark_s=0)
        self.assertEqual(result.data["terminal_status"], "rejected")
        self.assertIn("declared no read", result.data["reason"]["detail"])

    def test_the_oracle_measures_headroom_only_where_the_contract_loses_something(self):
        """The first headroom number, and it is zero here, which is the finding.

        With every signal relayed faithfully, exact truth concludes exactly what the
        contract-limited arm concludes: the observation contract is sufficient for these
        predicates in this state. Make the evidence stale and the gap appears.
        """
        informed, _, _, _ = self.run_arm("oracle_diagnosis", "informed")
        limited, _, _, _ = self.run_arm("eco", "limited")

        def concluded(store):
            payload = Record.from_dict(
                store.messages("dataset:diagnosis:0")[0].data["payload"]).data
            return sorted(h["label"] for h in payload["hypotheses"] if h["status"] == "supported")

        self.assertEqual(concluded(informed), concluded(limited),
                         "no headroom where the contract relays everything")
        self.assertTrue(concluded(informed), "and both actually concluded something")

    def test_stale_evidence_opens_a_gap_exact_truth_does_not_have(self):
        from ecora.runner import observation_batch
        for treatment, name in (("eco", "stale-limited"), ("oracle_diagnosis", "stale-informed")):
            model = world()
            registry, study, scenario_set, scenario, caps = closed_loop_environment(
                model, period_s=PERIOD)
            store = ArtifactStore(Path(self.temp.name) / name)
            self.addCleanup(store.close)
            run = registry.admit(study, scenario_set, scenario, caps, treatment, f"run:{name}")
            boundary = Boundary(store, registry, run)
            model.advance_to(0.0)
            boundary.ingest("ingest", observation_batch(model, CAPABILITIES, 0.0, PERIOD, 0),
                            watermark_s=0.0)
            model.advance_to(3.0)
            telemetry = boundary.invoke("telemetry", "telemetry", ["dataset:ingest"],
                                        watermark_s=3.0)
            diagnosis = boundary.invoke("diagnosis", "diagnosis",
                                        [telemetry.data["dataset_id"]], watermark_s=3.0)
            payload = Record.from_dict(
                store.messages(diagnosis.data["dataset_id"])[0].data["payload"]).data
            labels = sorted(h["label"] for h in payload["hypotheses"] if h["status"] == "supported")
            if treatment == "eco":
                self.assertEqual(labels, [], "stale evidence supports no conclusion")
            else:
                self.assertTrue(labels, "exact truth is never stale")

    def test_an_oracle_cannot_declare_a_read_it_was_not_granted(self):
        from ecora.registry import Registry
        port = TruthPort(world(), TRUTHS)
        with self.assertRaises(ContractError) as caught:
            truth_binding(Registry(), port, ["truth.ami.queue_occupancy"],
                          {"reads": ["truth.ami.everything"]})
        self.assertIn("no truth capability grants", str(caught.exception))
        with self.assertRaises(ContractError):
            truth_binding(Registry(), port, [], {"reads": []})


class Message:
    def __init__(self, record):
        self.data = {"payload": record.to_dict(), "scope": SCOPE,
                     "stage_invocation_id": "result", "output_dataset_id": "dataset:result"}


class Snapshot:
    def __init__(self):
        self.data = {"state": {}}


class Context:
    def __init__(self, configuration, watermark):
        self.data = {"configuration": configuration, "decision_watermark_s": watermark}


SCOPE = {"study_id": "study:fixture", "scenario_set_version": "1",
         "scenario_set_hash": "a" * 64, "scenario_id": "scenario:fixture",
         "scenario_revision": "1", "scenario_hash": "b" * 64, "run_id": "run:fixture"}


class AssessmentOracleTests(unittest.TestCase):
    """The references stage-arms.md designates for the last two stages."""

    def setUp(self):
        from ecora.scenario import SCENARIOS, build_world, load as load_scenario
        from ecora.study import resolve
        self.study = resolve("baseline")
        self.world = build_world(load_scenario(SCENARIOS / "s1-degraded-primary.json"))
        self.world.advance_to(2.5)
        self.cohorts = self.study.assembly["result"]["cohorts"]

    def port(self, capabilities=None):
        from ecora.fixtures import fixture_environment
        from ecora.truth import TruthPort
        _, _, _, _, caps = fixture_environment()
        declared = caps.data["capabilities"] if capabilities is None else capabilities
        return TruthPort(self.world, declared)

    def invoke(self, stage, configuration, port=None):
        from ecora.registry import Registry
        from ecora.truth import oracle_assessment_binding
        port = port or self.port()
        registry = Registry()
        binding = oracle_assessment_binding(registry, port, port.granted(),
                                            configuration, stage)
        message = Message(Record("ResultRecord", {
            "before_window": {"start_s": 0, "end_s": 2.5},
            "after_window": {"start_s": 2.5, "end_s": 2.5},
            "cohorts": [], "measurements": [], "action_ids": [],
            "uncertainty": "Synthetic."}))
        return port, registry.resolve(binding).factory().invoke(
            [message], Snapshot(), Context(binding["configuration"], 2.5))

    def test_it_counts_the_event_record_and_declares_the_read(self):
        port, result = self.invoke("result", {"cohorts": self.cohorts})
        record = result.outputs[0].data
        self.assertEqual(len(record["cohorts"]), len(self.cohorts))
        services = {m["service"] for m in record["measurements"]}
        self.assertEqual(services, {"scada", "ami"})
        self.assertTrue(result.trace["privileged_source_refs"],
                        "a truth-holding provider must declare what it read")
        self.assertTrue(all(reference.startswith("truth:cohort_record:")
                            for reference in result.trace["privileged_source_refs"]))

    def test_an_oracle_without_its_grant_is_unsupported_not_substituted(self):
        """An Oracle cell that cannot be served says so rather than becoming Proposed."""
        ordinary = [c for c in self.port().__dict__["_capabilities"].values()
                    if c["name"] != "cohort_record"]
        _, result = self.invoke("result", {"cohorts": self.cohorts},
                                port=self.port(ordinary))
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.reason["code"], "no_truth_capability")
        self.assertEqual(result.outputs, ())

    def test_the_evaluator_scores_the_studys_requirements_and_not_its_own(self):
        requirements = [{"requirement_id": "req:ami-delivery", "target": "site-1",
                         "service": "ami", "metric": "within_age_delivery", "unit": "ratio",
                         "comparator": "ge", "threshold": 0.95, "window_s": 10,
                         "denominator": "generated readings", "missingness_limit": 0.05}]
        _, result = self.invoke("assurance", {"cohorts": self.cohorts,
                                              "requirements": requirements})
        report = result.outputs[0].data
        self.assertEqual([c["requirement_id"] for c in report["claims"]],
                         ["req:ami-delivery"])
        self.assertTrue(result.trace["privileged_source_refs"])

    def test_an_assessment_oracle_needs_the_cohorts_it_counts(self):
        from ecora.registry import Registry
        from ecora.truth import oracle_assessment_binding
        with self.assertRaises(ContractError):
            oracle_assessment_binding(Registry(), self.port(), [], {}, "result")
        with self.assertRaises(ContractError):
            oracle_assessment_binding(Registry(), self.port(), [],
                                      {"cohorts": self.cohorts}, "assurance")
        with self.assertRaises(ContractError):
            oracle_assessment_binding(Registry(), self.port(), [],
                                      {"cohorts": self.cohorts}, "planning")

    def test_censoring_reports_the_run_rather_than_a_blanket_disclaimer(self):
        """An obligation whose deadline has not elapsed is censored; a settled one is not.

        Run on the silent leg, where readings are genuinely outstanding at the stop: on a
        leg that delivers, every reading may already have arrived and nothing is censored.
        """
        from ecora.scenario import SCENARIOS, build_world, load as load_scenario
        silent = build_world(load_scenario(SCENARIOS / "s2-silent-primary.json")).advance_to(2.5)
        cohorts = silent.cohorts(self.cohorts)
        by_id = {c["cohort_id"]: c for c in cohorts}
        self.assertFalse(by_id["cohort:scada:measured"]["censored"],
                         "SCADA deadlines elapsed long before the clock stopped")
        self.assertTrue(by_id["cohort:ami:measured"]["censored"],
                        "an AMI reading still has until its deadline to arrive")


if __name__ == "__main__":
    unittest.main()
