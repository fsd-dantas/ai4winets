"""Cohort-based outcome extraction and requirement evaluation.

These are the Proposed providers for the last two stages. Until now both had only a Null
arm, so every run ended inconclusive by construction rather than by finding: there was
nothing in the pipeline that could have reached a verdict.

Two rules shape them, and both exist to stop a report from being more confident than its
evidence.

Extraction reports what the cohorts support and nothing beyond it. A ratio needs a
population, so a cohort with no generated demand yields an unknown measurement rather than
a perfect one; dividing zero by zero into a hundred per cent is the oldest way to make a
result look good.

Evaluation reaches a verdict only where a measurement exists and was actually measured. A
requirement whose evidence is missing, unknown, or thinner than its declared missingness
limit is inconclusive and says which, because an unevaluated requirement quietly counted
as passing is how a study comes to claim more coverage than it has.

The assurance provider does not own the study's scoring rules. Its requirements and
comparators are frozen in its binding, so substituting it cannot change what passing
means; an always-positive reporter would still be scored by the evaluator the study fixes.
"""

from functools import partial

from .contracts import Record, digest, require
from .registry import ProviderResult
from .schema import INPUT_TYPES, OUTPUT_TYPES

VERSION = "assessment-v1"


def _measure(metric, service, unit, value, numerator=0, denominator=0):
    known = value is not None
    return {"metric": metric, "service": service, "unit": unit, "value": value,
            "quality": "measured" if known else "unknown",
            "numerator": numerator, "denominator": denominator}


def cohort_measurements(cohorts):
    """What the cohorts support, per service class, with their populations attached.

    Per service and never pooled. A cohort of SCADA commands and one of AMI readings have
    different deadlines and different requirements, so one ratio drawn across both answers
    no requirement either of them declares while looking like it answers two.
    """
    counted, measurements, totals = {}, [], {}
    for cohort in cohorts:
        service = cohort["service"]
        tally = counted.setdefault(service, dict.fromkeys(
            ("generated", "on_time", "late", "lost", "pending"), 0))
        for name, field in (("generated", "generated"), ("on_time", "delivered_on_time"),
                            ("late", "delivered_late"), ("lost", "lost"),
                            ("pending", "pending")):
            tally[name] += cohort[field]
            totals[name] = totals.get(name, 0) + cohort[field]
    for service in sorted(counted):
        tally = counted[service]
        generated = tally["generated"]

        def ratio(name, count, generated=generated, service=service):
            # A ratio without a population is not zero and not one; it is unknown.
            return _measure(name, service, "ratio",
                            count / generated if generated else None, count, generated)

        measurements.append(ratio("within_age_delivery", tally["on_time"]))
        measurements.append(ratio("late_delivery", tally["late"]))
        measurements.append(ratio("loss", tally["lost"]))
        measurements.append(ratio("outstanding", tally["pending"]))
        measurements.append(_measure("generated", service, "count", generated))
    return measurements, {**totals, "by_service": counted}


class ResultProvider:
    """Cohort-based measured outcome extraction from the assembled result input."""

    def invoke(self, inputs, prior_state, context):
        watermark = context.data["decision_watermark_s"]
        supplied = next((Record.from_dict(m.data["payload"]) for m in inputs
                         if Record.from_dict(m.data["payload"]).kind == "ResultInput"), None)
        if supplied is None:
            return ProviderResult((), {}, {"extraction": "cohort"}, "no_op",
                                  {"code": "no_input", "detail": "No cohort specification was supplied."})
        cohorts = supplied.data["cohorts"]
        measurements, totals = cohort_measurements(cohorts)
        censored = [c["cohort_id"] for c in cohorts if c["censored"]]
        record = Record("ResultRecord", {
            "before_window": {"start_s": 0, "end_s": watermark},
            "after_window": {"start_s": watermark, "end_s": watermark},
            "cohorts": cohorts, "measurements": measurements,
            "action_ids": supplied.data["receipt_ids"],
            "uncertainty": ("Censored cohorts: " + ", ".join(censored)) if censored
            else "No cohort was censored in this extraction."})
        return ProviderResult((record,), {}, {"extraction": "cohort", "cohorts": len(cohorts),
                                              "population": totals.get("generated", 0),
                                              "censored": censored})


_COMPARE = {"le": lambda value, threshold: value <= threshold,
            "ge": lambda value, threshold: value >= threshold}


class AssuranceProvider:
    """Requirement evaluation against extracted outcomes, with explicit coverage."""

    def invoke(self, inputs, prior_state, context):
        config = context.data["configuration"]
        result = next((Record.from_dict(m.data["payload"]) for m in inputs
                       if Record.from_dict(m.data["payload"]).kind == "ResultRecord"), None)
        scope = inputs[0].data["scope"] if inputs else None
        if result is None or scope is None:
            return ProviderResult((), {}, {"evaluator": VERSION}, "no_op",
                                  {"code": "no_result", "detail": "No result evidence reached the evaluator."})
        # Keyed by service and metric together. A requirement over SCADA must not be
        # answered by the AMI population that happened to carry the same metric name.
        measured = {(m["service"], m["metric"]): m for m in result.data["measurements"]}
        claims, evaluable = [], 0
        for requirement in config["requirements"]:
            measurement = measured.get((requirement["service"], requirement["metric"]))
            verdict, reason, evidence = self._judge(requirement, measurement, result)
            evaluable += verdict in ("met", "violated")
            claims.append({"requirement_id": requirement["requirement_id"], "verdict": verdict,
                           "evidence_refs": evidence, "reason": reason})
        limitations = ["Synthetic world; no field validation.",
                       f"{evaluable} of {len(claims)} requirements were evaluable."]
        if any(claim["verdict"] == "inconclusive" for claim in claims):
            limitations.append("An inconclusive requirement is not a passing one.")
        report = Record("AssuranceReport", {
            "study_id": scope["study_id"], "scenario_set_version": scope["scenario_set_version"],
            "scenario_set_hash": scope["scenario_set_hash"],
            "contributing_run_ids": [scope["run_id"]],
            "contributing_invocation_ids": sorted({m.data["stage_invocation_id"] for m in inputs}),
            "contributing_dataset_ids": sorted({m.data["output_dataset_id"] for m in inputs}),
            "evaluator_version": config.get("evaluator_version", VERSION), "claims": claims,
            "limitations": limitations,
            "created_at_utc": config.get("created_at_utc", "2026-09-22T00:00:00Z")})
        return ProviderResult((report,), {}, {"evaluator": VERSION, "claims": len(claims),
                                              "evaluable": evaluable})

    @staticmethod
    def _judge(requirement, measurement, result):
        """A verdict only where the evidence supports one, and the reason where it does not."""
        identity = f"measurement:{requirement['service']}:{requirement['metric']}"
        if measurement is None:
            return "inconclusive", {"code": "no_measurement",
                                    "detail": "The extraction carries no such measurement."}, []
        if measurement["quality"] != "measured":
            return "inconclusive", {"code": "unmeasured",
                                    "detail": "The measurement exists but holds no value."}, []
        population = measurement["denominator"]
        if requirement["unit"] == "ratio" and population <= 0:
            return "inconclusive", {"code": "empty_population",
                                    "detail": "No generated demand, so the ratio is not applicable."}, []
        missing = requirement.get("missingness_limit", 0)
        # The coverage check is the same service's outstanding demand, not any service's.
        outstanding = next((m for m in result.data["measurements"]
                            if m["metric"] == "outstanding"
                            and m["service"] == requirement["service"]), None)
        if outstanding and outstanding["quality"] == "measured" and outstanding["value"] > missing:
            return "inconclusive", {"code": "coverage_below_limit",
                                    "detail": "Outstanding demand exceeds the declared missingness limit."}, []
        met = _COMPARE[requirement["comparator"]](measurement["value"], requirement["threshold"])
        return ("met" if met else "violated",
                {"code": "evaluated",
                 "detail": f"{measurement['value']:.4f} {requirement['comparator']} "
                           f"{requirement['threshold']} over {population} generated."},
                [identity])


PROVIDERS = {"result": ("result.cohort", ResultProvider),
             "assurance": ("assurance.requirements", AssuranceProvider)}


def assessment_binding(registry, capability_ids, configuration, stage):
    """Register the Proposed provider for an assessment stage and return its binding."""
    require(stage in PROVIDERS, f"no assessment provider is defined for stage {stage}")
    if stage == "assurance":
        require(configuration.get("requirements"),
                "an evaluator must be given the requirements it scores against")
        for requirement in configuration["requirements"]:
            require(requirement["comparator"] in _COMPARE,
                    f"unknown comparator in {requirement['requirement_id']}")
    provider_id, factory = PROVIDERS[stage]
    spec = Record("ProviderSpec", {
        "stage_id": stage, "provider_id": provider_id, "provider_version": VERSION,
        "arm": "proposed", "input_types": list(INPUT_TYPES[stage]),
        "output_types": list(OUTPUT_TYPES[stage]), "state_schema_version": "1",
        "capability_ids": list(capability_ids), "direct_truth_access": False})
    if not registry.registered(stage, provider_id, VERSION):
        registry.register(spec, factory)
    return {k: v for k, v in spec.data.items() if k != "direct_truth_access"} | {
        "information_regime": "contract_only", "allow_privileged_inputs": False,
        "configuration": configuration, "configuration_hash": digest(configuration)}
