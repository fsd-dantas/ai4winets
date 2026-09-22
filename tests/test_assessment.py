import unittest

from ecora.assessment import (AssuranceProvider, ResultProvider, assessment_binding,
                              cohort_measurements)
from ecora.contracts import ContractError, Record
from ecora.registry import Registry

SCOPE = {"study_id": "study:fixture", "scenario_set_version": "1",
         "scenario_set_hash": "a" * 64, "scenario_id": "scenario:fixture",
         "scenario_revision": "1", "scenario_hash": "b" * 64, "run_id": "run:fixture"}

REQUIREMENT = {"requirement_id": "req:delivery", "target": "site-1", "service": "ami",
               "metric": "within_age_delivery", "unit": "ratio", "comparator": "ge",
               "threshold": 0.99, "window_s": 10, "denominator": "generated readings",
               "missingness_limit": 0}


def cohort(**changes):
    data = {"cohort_id": "cohort:ami", "generation_window": {"start_s": 0, "end_s": 1},
            "generated": 10, "delivered_on_time": 10, "delivered_late": 0, "lost": 0,
            "pending": 0, "duplicate_deliveries": 0, "censored": False, "deadline_s": 10}
    return {**data, **changes}


class Message:
    def __init__(self, kind, payload, scope=None):
        self.data = {"payload": Record(kind, payload).to_dict(), "scope": scope or SCOPE,
                     "stage_invocation_id": "result", "output_dataset_id": "dataset:result"}


class Snapshot:
    def __init__(self):
        self.data = {"state": {}}


class Context:
    def __init__(self, configuration, watermark=1.0):
        self.data = {"configuration": configuration, "decision_watermark_s": watermark}


def extract(cohorts, receipts=()):
    inputs = [Message("ResultInput", {"receipt_ids": list(receipts), "observation_ids": [],
                                      "cohorts": cohorts})]
    result = ResultProvider().invoke(inputs, Snapshot(), Context({}))
    return result.outputs[0].data, result.trace


def evaluate(measurements, requirements=(REQUIREMENT,), cohorts=None):
    window = {"start_s": 0, "end_s": 1}
    record = {"before_window": window, "after_window": window,
              "cohorts": cohorts if cohorts is not None else [cohort()],
              "measurements": measurements, "action_ids": [], "uncertainty": "Synthetic."}
    result = AssuranceProvider().invoke([Message("ResultRecord", record)], Snapshot(),
                                        Context({"requirements": list(requirements)}))
    return result.outputs[0].data, result.trace


def measurement(metric, value, numerator=10, denominator=10, quality=None):
    return {"metric": metric, "unit": "ratio", "value": value,
            "quality": quality or ("measured" if value is not None else "unknown"),
            "numerator": numerator, "denominator": denominator}


class ExtractionTests(unittest.TestCase):
    def test_it_reports_the_ratios_the_cohorts_support(self):
        record, trace = extract([cohort(generated=10, delivered_on_time=8, delivered_late=1,
                                        lost=1, pending=0)])
        values = {m["metric"]: m["value"] for m in record["measurements"]}
        self.assertAlmostEqual(values["within_age_delivery"], 0.8)
        self.assertAlmostEqual(values["late_delivery"], 0.1)
        self.assertAlmostEqual(values["loss"], 0.1)
        self.assertEqual(trace["population"], 10)

    def test_a_ratio_without_a_population_is_unknown_and_not_perfect(self):
        """Zero delivered out of zero generated is not full delivery."""
        record, _ = extract([cohort(generated=0, delivered_on_time=0, delivered_late=0,
                                    lost=0, pending=0)])
        delivery = next(m for m in record["measurements"]
                        if m["metric"] == "within_age_delivery")
        self.assertIsNone(delivery["value"])
        self.assertEqual(delivery["quality"], "unknown")

    def test_a_censored_cohort_is_named_in_the_uncertainty(self):
        record, trace = extract([cohort(censored=True)])
        self.assertIn("cohort:ami", record["uncertainty"])
        self.assertEqual(trace["censored"], ["cohort:ami"])
        clean, _ = extract([cohort(censored=False)])
        self.assertIn("No cohort was censored", clean["uncertainty"])

    def test_withheld_demand_is_carried_as_outstanding(self):
        record, _ = extract([cohort(generated=10, delivered_on_time=6, delivered_late=0,
                                    lost=0, pending=4)])
        values = {m["metric"]: m["value"] for m in record["measurements"]}
        self.assertAlmostEqual(values["outstanding"], 0.4)
        self.assertAlmostEqual(values["within_age_delivery"], 0.6)


class EvaluationTests(unittest.TestCase):
    def test_a_requirement_is_met_or_violated_on_its_comparator(self):
        report, _ = evaluate([measurement("within_age_delivery", 1.0),
                              measurement("outstanding", 0.0)])
        claim = report["claims"][0]
        self.assertEqual(claim["verdict"], "met")
        self.assertTrue(claim["evidence_refs"], "a conclusive claim must cite evidence")
        report, _ = evaluate([measurement("within_age_delivery", 0.5),
                              measurement("outstanding", 0.0)])
        self.assertEqual(report["claims"][0]["verdict"], "violated")

    def test_a_requirement_without_a_measurement_is_inconclusive(self):
        report, trace = evaluate([measurement("outstanding", 0.0)])
        claim = report["claims"][0]
        self.assertEqual(claim["verdict"], "inconclusive")
        self.assertEqual(claim["reason"]["code"], "no_measurement")
        self.assertEqual(claim["evidence_refs"], [])
        self.assertEqual(trace["evaluable"], 0)

    def test_an_unmeasured_value_is_inconclusive_not_failing(self):
        report, _ = evaluate([measurement("within_age_delivery", None),
                              measurement("outstanding", 0.0)])
        self.assertEqual(report["claims"][0]["verdict"], "inconclusive")
        self.assertEqual(report["claims"][0]["reason"]["code"], "unmeasured")

    def test_an_empty_population_cannot_satisfy_a_ratio_requirement(self):
        report, _ = evaluate([measurement("within_age_delivery", None, 0, 0),
                              measurement("outstanding", 0.0)])
        self.assertEqual(report["claims"][0]["verdict"], "inconclusive")

    def test_coverage_below_the_declared_limit_blocks_a_verdict(self):
        """Delivery can look perfect while most of the demand is still outstanding."""
        report, _ = evaluate([measurement("within_age_delivery", 1.0),
                              measurement("outstanding", 0.4)])
        claim = report["claims"][0]
        self.assertEqual(claim["verdict"], "inconclusive")
        self.assertEqual(claim["reason"]["code"], "coverage_below_limit")

    def test_the_report_says_how_much_it_could_evaluate(self):
        report, _ = evaluate([measurement("outstanding", 0.0)])
        self.assertTrue(any("1 requirements were evaluable" in line
                            for line in report["limitations"]))
        self.assertTrue(any("inconclusive requirement is not a passing one" in line
                            for line in report["limitations"]))

    def test_the_requirements_are_frozen_in_the_binding_not_chosen_by_the_provider(self):
        binding = assessment_binding(Registry(), [], {"requirements": [REQUIREMENT]},
                                     "assurance")
        self.assertEqual(binding["configuration"]["requirements"], [REQUIREMENT])
        self.assertEqual(binding["arm"], "proposed")
        with self.assertRaises(ContractError):
            assessment_binding(Registry(), [], {"requirements": []}, "assurance")
        with self.assertRaises(ContractError):
            assessment_binding(Registry(), [], {"requirements": [
                {**REQUIREMENT, "comparator": "approximately"}]}, "assurance")

    def test_no_assessment_provider_exists_for_a_decision_stage(self):
        with self.assertRaises(ContractError):
            assessment_binding(Registry(), [], {}, "planning")


if __name__ == "__main__":
    unittest.main()
