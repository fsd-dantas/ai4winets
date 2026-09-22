"""The Proposed telemetry provider: normalisation, quality and local projection.

Specified by docs/ECoRA/stage-arms.md as contract-constrained trace normalisation, quality
and local projection, and scoped by docs/ECoRA/v1-scope.md to what one site's agents may
see: their own workload, queue and delivery summaries, that site's path selector, and
same-site marks. Nothing from another site reaches a local projection, whatever the
adapter offered.

Three rules govern it, and each exists to stop a specific way of lying with evidence:

- It never invents a value. An expected signal that is absent, or present but older than
  the declared freshness bound, leaves the batch as an explicit missing observation with
  its reason. Unknown is a value; silence is not.
- It cannot report the absence of what it was never permitted to observe, because a
  synthesised missing observation still carries a capability the binding holds and is
  checked against it at the boundary.
- Declared completeness is the fraction of expected signals actually relayed, so a batch
  cannot claim full coverage while withholding one.

In v1 the adapter already emits contract-valid observations, so normalisation is a checked
pass-through rather than a transformation. That is stated here rather than implied: when a
rawer adapter arrives, this is the seam that has to do the work.
"""

from functools import partial

from .contracts import Record, digest, require
from .registry import ProviderResult
from .schema import INPUT_TYPES, OUTPUT_TYPES

VERSION = "proposed-v1"


class ProjectionProvider:
    """Projects an adapter batch onto one site's declared local view."""

    def invoke(self, inputs, prior_state, context):
        watermark = context.data["decision_watermark_s"]
        config = context.data["configuration"]
        expected = config["expected"]
        max_age = config.get("max_observation_age_s")
        subject = config["neighbourhood"]["subject"]
        services = set(config["neighbourhood"]["services"])

        offered = []
        for message in inputs:
            payload = Record.from_dict(message.data["payload"])
            if payload.kind == "AdapterObservationBatch":
                offered.extend(payload.data["observations"])

        # A neighbourhood is the site and what belongs to it, such as its own legs. It is
        # still one site: a subject under another site's prefix does not become local.
        local = [o for o in offered
                 if (o["subject"] == subject or o["subject"].startswith(f"{subject}/"))
                 and o["service"] in services]
        remote = len(offered) - len(local)
        by_signal = {(o["subject"], o["service"], o["metric"], o["unit"]): o for o in local}

        relayed, omitted, stale = [], [], 0
        for signal in expected:
            key = (signal["subject"], signal["service"], signal["metric"], signal["unit"])
            found = by_signal.get(key)
            if found is not None and found["quality"] == "missing":
                # Offered but it did not come back, as with a probe that timed out. The
                # adapter's own reason is kept rather than replaced by a generic one.
                omitted.append(signal["metric"])
                relayed.append(found)
                continue
            reason = None
            if found is None:
                reason = {"code": "absent", "detail": "The adapter offered no such signal."}
            elif max_age is not None and found["available_at_s"] < watermark - max_age:
                reason = {"code": "stale", "detail": "Older than the declared freshness bound."}
                stale += 1
            if reason is None:
                relayed.append(found)
                continue
            omitted.append(signal["metric"])
            relayed.append(self._absent(signal, watermark, reason))

        batch = Record("TelemetryBatch", {
            "observations": relayed, "watermark_s": watermark,
            "window": {"start_s": watermark, "end_s": watermark},
            "sequence": config.get("sequence", 0),
            "completeness": (len(expected) - len(omitted)) / len(expected) if expected else 0,
            "omitted_metrics": sorted(set(omitted))})
        state = {"batches": prior_state.data["state"].get("batches", 0) + 1,
                 "last_watermark_s": watermark}
        trace = {"offered": len(offered), "out_of_neighbourhood": remote,
                 "relayed": len(relayed) - len(omitted), "absent_or_stale": len(omitted),
                 "stale": stale}
        return ProviderResult((batch,), state, trace)

    @staticmethod
    def _absent(signal, watermark, reason):
        """An expected signal that could not be relayed, recorded as unknown."""
        return {"observation_id": f"observation:{signal['subject']}:{signal['metric']}:unknown:{watermark}",
                "subject": signal["subject"], "service": signal["service"],
                "metric": signal["metric"], "unit": signal["unit"], "value": None,
                "quality": "missing", "missing_reason": reason, "event_time_s": watermark,
                "available_at_s": watermark, "window": {"start_s": watermark, "end_s": watermark},
                "source": "telemetry.projection", "sampling_policy": "expected_signal",
                "valid_min": None, "valid_max": None,
                "assumptions": ["Expected by the declared projection; not supplied or not fresh."],
                "evidence_kind": "measured", "capability_id": signal["capability_id"],
                "source_observation_ids": [], "formula": None, "privileged_source_refs": []}


def projection_binding(registry, capability_ids, configuration):
    """Register the Proposed telemetry provider and return its frozen binding."""
    require(configuration.get("expected"), "a projection must declare the signals it expects")
    for signal in configuration["expected"]:
        require(signal["capability_id"] in capability_ids,
                f"projection expects a signal it is not permitted to observe: {signal['metric']}")
    spec = Record("ProviderSpec", {
        "stage_id": "telemetry", "provider_id": "telemetry.projection",
        "provider_version": VERSION, "arm": "proposed",
        "input_types": list(INPUT_TYPES["telemetry"]), "output_types": list(OUTPUT_TYPES["telemetry"]),
        "state_schema_version": "1", "capability_ids": list(capability_ids),
        "direct_truth_access": False})
    if not registry.registered("telemetry", spec.data["provider_id"], VERSION):
        registry.register(spec, ProjectionProvider)
    return {k: v for k, v in spec.data.items() if k != "direct_truth_access"} | {
        "information_regime": "contract_only", "allow_privileged_inputs": False,
        "configuration": configuration, "configuration_hash": digest(configuration)}
