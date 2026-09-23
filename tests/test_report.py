import json
import tempfile
import unittest
from pathlib import Path

from ecora.__main__ import CAPABILITIES
from ecora.boundary import Boundary
from ecora.report import render, run_report
from ecora.runner import Run, Streams, closed_loop_environment
from ecora.scenario import SCENARIOS, build_world, load
from ecora.store import ArtifactStore
from ecora.study import resolve

PERIOD = 0.5
EPOCHS = 2
SCENARIO = load(SCENARIOS / "s1-degraded-primary.json")
KNOWLEDGE = resolve("baseline")


class RunReportTests(unittest.TestCase):
    """B37: four kinds of finding, reported apart and read only from the store."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.reports = {}
        for treatment in ("null_baseline", "assured", "oracle_diagnosis", "oracle_assurance"):
            model = build_world(SCENARIO)
            registry, study, scenario_set, scenario, caps = closed_loop_environment(
                model, period_s=PERIOD, scenario=SCENARIO, study=KNOWLEDGE)
            with ArtifactStore(Path(cls.temp.name) / treatment) as store:
                run = registry.admit(study, scenario_set, scenario, caps, treatment,
                                     f"run:{treatment}")
                Run(Boundary(store, registry, run), model,
                    streams=Streams(study.data["seed_manifest"]), capability_ids=CAPABILITIES,
                    period_s=PERIOD, epochs=EPOCHS, assembly=study.data["assembly"],
                    predicate_map=KNOWLEDGE.predicate_map).execute()
                cls.reports[treatment] = run_report(store)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_every_report_carries_the_four_sections(self):
        for treatment, report in self.reports.items():
            with self.subTest(treatment=treatment):
                for section in ("service_outcomes", "coordination_stability",
                                "missing_evidence", "privileged_information"):
                    self.assertIn(section, report)
                self.assertEqual(report["epochs"], EPOCHS)
                self.assertEqual(report["decision_period_s"], PERIOD)

    def test_an_inconclusive_requirement_is_missing_evidence_and_never_a_pass(self):
        for treatment, report in self.reports.items():
            with self.subTest(treatment=treatment):
                service, missing = report["service_outcomes"], report["missing_evidence"]
                inconclusive = [c for c in service["claims"] if c["verdict"] == "inconclusive"]
                self.assertEqual(missing["inconclusive"], inconclusive)
                self.assertEqual(service["verdicts"]["inconclusive"], len(inconclusive))
                self.assertEqual(sum(service["verdicts"].values()), len(service["claims"]))

    def test_the_null_arm_reports_what_it_could_not_see(self):
        report = self.reports["null_baseline"]
        missing = report["missing_evidence"]
        self.assertEqual(len(missing["telemetry_gaps"]), EPOCHS)
        self.assertEqual(missing["diagnosis_without_support"], list(range(EPOCHS)))
        self.assertTrue(missing["no_service_extraction"])
        self.assertEqual(report["service_outcomes"]["verdicts"]["met"], 0)

    def test_a_contract_limited_run_carries_no_privileged_result(self):
        for treatment in ("null_baseline", "assured"):
            with self.subTest(treatment=treatment):
                report = self.reports[treatment]
                self.assertFalse(report["privileged_information"]["present"])
                self.assertTrue(report["service_outcomes"]["deployable"])
        self.assertEqual(set(self.reports["assured"]["service_outcomes"]["by_service"]),
                         {"scada", "ami"})

    def test_a_verdict_resting_on_truth_is_labelled_where_it_is_reported(self):
        """Privilege follows lineage, so it reaches the verdict even from upstream."""
        for treatment, first in (("oracle_assurance", "result"),
                                 ("oracle_diagnosis", "diagnosis")):
            with self.subTest(treatment=treatment):
                report = self.reports[treatment]
                privileged = report["privileged_information"]
                self.assertTrue(privileged["present"])
                self.assertIn(first, privileged["by_stage"])
                self.assertIn("assurance", privileged["by_stage"])
                self.assertFalse(report["service_outcomes"]["deployable"])
                self.assertIn("PRIVILEGED", render(report))
        # Truth read at extraction does not taint the stages that decided before it.
        self.assertNotIn("diagnosis",
                         self.reports["oracle_assurance"]["privileged_information"]["by_stage"])

    def test_stability_is_reported_beside_service_and_consults_none_of_it(self):
        for report in self.reports.values():
            stability = report["coordination_stability"]
            self.assertTrue(stability["measured"])
            self.assertIn("no service outcome is consulted", stability["note"])
            service_metrics = {metric for metrics in report["service_outcomes"]["by_service"].values()
                               for metric in metrics}
            self.assertFalse(service_metrics & set(stability["metrics"]))

    def test_the_report_is_regenerated_from_the_store_alone(self):
        """Reopening the artifacts, with no model in reach, reproduces the report exactly."""
        path = Path(self.temp.name) / "assured"
        with ArtifactStore(path) as store:
            again = run_report(store)
        self.assertEqual(json.dumps(again, sort_keys=True),
                         json.dumps(self.reports["assured"], sort_keys=True))


if __name__ == "__main__":
    unittest.main()
