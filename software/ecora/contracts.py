"""Validated immutable records, canonical JSON, hashes and cross-field invariants."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math

from jsonschema import Draft202012Validator, FormatChecker

from .schema import RECORD_TYPES, STAGES, schema_document

# The simulator's valid range for cell load, the same bound it enforces itself: a site's
# share was measured to fall smoothly to 35 competing UEs and to vanish at 40, where the
# cell stops admitting UEs. Beyond it the model is not the cell a scenario means.
MAX_COMPETING_UES = 35

# The actuator each operator writes, as it is named in a command's read and write sets and
# in the observed state versions. One table, so no builder can name an actuator differently.
ACTUATOR_FIELDS = {"select_path": "selected_path", "set_ami_pacing": "pacing_profile"}


def observed_version(proposal, target, operator):
    """The version the proposal's controller observed the actuator at, or None.

    None means no version was observed, and then no command may be written: a write that
    cannot name the state it was decided against cannot be checked for staleness, and the
    action contract says to abstain rather than assume.
    """
    versions = proposal.get("state_versions") or {}
    return versions.get(f"{target}/{ACTUATOR_FIELDS[operator]}")


class ContractError(ValueError):
    """An input cannot cross a declared boundary without losing contract integrity."""


def require(condition, message):
    if not condition:
        raise ContractError(message)


def _json_types(value):
    if type(value) is dict:
        require(all(type(k) is str for k in value), "JSON object keys must be strings")
        for child in value.values():
            _json_types(child)
    elif type(value) is list:
        for child in value:
            _json_types(child)
    elif type(value) is float:
        require(math.isfinite(value), "non-finite JSON number")
    elif type(value) not in (str, int, bool, type(None)):
        raise ContractError(f"not a JSON value: {type(value).__name__}")


def canonical(value):
    """ecora-json-v1: sorted keys, compact UTF-8, finite numbers; not RFC 8785."""
    _json_types(value)
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise ContractError(str(exc)) from exc


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def decode(raw):
    try:
        result = json.loads(raw, object_pairs_hook=_pairs,
                            parse_constant=lambda value: (_ for _ in ()).throw(
                                ContractError(f"non-finite number: {value}")))
        _json_types(result)
        return result
    except (ValueError, UnicodeError, TypeError) as exc:
        raise ContractError(str(exc)) from exc


@lru_cache(maxsize=None)
def validator(kind):
    require(kind in RECORD_TYPES, f"unsupported record type: {kind}")
    schema = schema_document()
    schema["$ref"] = f"#/$defs/{kind}"
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _window(window):
    require(window["start_s"] <= window["end_s"], "window ends before it starts")


def _unique(items, field):
    keys = [item[field] for item in items]
    require(len(keys) == len(set(keys)), f"duplicate {field}")


def _terminal(data, field="status"):
    if data[field] != "ok":
        require(data["reason"] is not None, "non-ok outcome requires a typed reason")


def _observation(o, watermark):
    require(o["event_time_s"] <= o["available_at_s"] <= watermark,
            "observation violates event/availability watermark ordering")
    _window(o["window"])
    require(o["window"]["end_s"] <= o["event_time_s"], "observation window extends into its future")
    missing = o["quality"] == "missing"
    require((o["value"] is None) == missing, "missing observation must use null, observed must have a value")
    require((o["missing_reason"] is not None) == missing, "missing observation requires its reason")
    if o["evidence_kind"] == "simulator_truth":
        require(bool(o["privileged_source_refs"]), "simulator truth requires privileged source references")
    if o["quality"] == "derived":
        require(o["evidence_kind"] == "derived" and o["formula"] and o["source_observation_ids"],
                "derived evidence needs formula and sources")
    units = {"queue_occupancy": {"byte", "packet"}, "offered_load": {"bit/s"},
             "goodput": {"bit/s"}, "packet_generated": {"event"}, "packet_delivered": {"event"},
             "scada_response": {"s"}, "packet_drop": {"event"}, "path_state": {"id"}, "pacing_profile": {"id"},
             "path_probe": {"s"}, "actuator_version": {"count"}, "claim_state": {"event"}, "control_message": {"byte"},
             "link_measurement": {"dBm"}}
    require(o["metric"] in units, "signal not in versioned telemetry catalog")
    require(o["unit"] in units[o["metric"]], "metric/unit mismatch")
    if o["valid_min"] is not None and o["valid_max"] is not None:
        require(o["valid_min"] <= o["valid_max"], "invalid observation range")
    if missing:
        return
    value = o["value"]
    if o["unit"] in {"s", "byte", "packet", "bit/s", "ratio", "count", "dBm"}:
        require(type(value) in (int, float), "numeric metric requires a numeric value")
        if o["unit"] != "dBm":
            require(value >= 0, "negative observation")
        if o["unit"] in {"byte", "packet", "count"}:
            require(type(value) is int, "counts must be integers")
        if o["unit"] == "ratio":
            require(value <= 1, "ratio exceeds one")
        if o["valid_min"] is not None:
            require(value >= o["valid_min"], "observation below its declared range")
        if o["valid_max"] is not None:
            require(value <= o["valid_max"], "observation above its declared range")
    elif o["unit"] == "id":
        require(type(value) is str and bool(value), "identifier metric requires a string")
    else:
        require(type(value) is dict and bool(value.get("event_id")), "event requires an event_id object")


def _command(d):
    require(d["not_before_s"] < d["expires_at_s"], "command has no valid dispatch interval")
    operator = d["operator"]
    allowed = {
        "select_path": ("site", {"path"}, {"selected_path"}),
        "set_ami_pacing": ("ami_queue", {"profile"}, {"pacing_profile"}),
        "defer_eligible_message": ("ami_queue", {"message_id", "release_at_s", "latest_release_s"}, {"release_at_s"}),
        "publish_mark": ("own_mark", {"intent", "expires_at_s"}, {"mark"}),
        "release_claim": ("own_mark", {"claim_id"}, {"mark"}),
        "yield": ("own_proposal", {"proposal_id"}, {"proposal"}),
        "no_op": ("own_proposal", set(), set()),
    }
    scope, arguments, writes = allowed[operator]
    require(d["scope"] == scope, "operator scope mismatch")
    require(set(d["arguments"]) == arguments, "operator arguments do not match the v1 catalog")
    require(set(d["write_set"]) == {f'{d["target"]}/{key}' for key in writes},
            "write set exceeds the operator's owned mutable fields")
    if scope == "ami_queue":
        require(d["service"] == "ami", "SCADA deferral/pacing is forbidden")
    if operator == "select_path":
        require(d["service"] == "shared", "path switching must cover both service classes")
        require(d["arguments"]["path"] in ("lte", "alternative"), "unknown path")
    if operator == "set_ami_pacing":
        require(d["arguments"]["profile"] in ("normal", "restricted", "minimum"), "unknown pacing profile")
    expected_units = {key: "s" for key in arguments if key.endswith("_s")}
    require(d["argument_units"] == expected_units, "action argument units mismatch")
    for key in expected_units:
        value = d["arguments"][key]
        require(type(value) in (int, float) and value >= 0, "invalid action time")
    if operator == "defer_eligible_message":
        require(d["not_before_s"] <= d["arguments"]["release_at_s"] <= d["arguments"]["latest_release_s"],
                "deferral exceeds delivery obligation")
    if operator != "no_op":
        require(bool(d["precondition_evidence_ids"]), "mutation requires precondition evidence")


def validate(kind, data):
    canonical(data)
    errors = sorted(validator(kind).iter_errors(data), key=lambda error: str(error.path))
    if errors:
        raise ContractError(f"{kind} {list(errors[0].path)}: {errors[0].message}")
    if kind == "ScenarioSetManifest":
        _unique(data["members"], "scenario_id")
    elif kind == "ScenarioSpec":
        _unique(data["flows"], "flow_id")
        _unique(data["requirements"], "requirement_id")
        _unique(data["topology"]["legs"], "leg_id")
        legs = {leg["leg_id"]: leg for leg in data["topology"]["legs"]}
        sites = set(data["topology"]["sites"])
        require(data["topology"]["initial_path"] in legs, "the initial path must name a declared leg")
        for flow in data["flows"]:
            require(flow["max_deferral_s"] < flow["deadline_s"], "deferral must precede deadline")
            # A transaction starts centrally and is answered by a site; a periodic flow
            # starts at a site. Either way one end is a declared site.
            site_end = flow["destination"] if flow["pattern"] == "request_response" else flow["source"]
            require(site_end in sites, f"flow {flow['flow_id']} names an undeclared site")
            if flow["service"] == "scada":
                require(flow["max_deferral_s"] == 0, "SCADA cannot be deferred")
        for leg in legs.values():
            if leg["kind"] == "lte":
                require(set(leg["radio"]["site_positions_m"]) == sites,
                        f"LTE leg {leg['leg_id']} must position every declared site")
                levels = {}
                for entry in leg["logical"]["rate_table"]:
                    levels.setdefault(entry["competing_ues"], []).append(entry["extra_loss_db"])
                require(0 in levels, "the rate table covers the unloaded cell")
                for level, losses in levels.items():
                    # Each load level is its own loss table, starting where the leg is unimpaired.
                    require(losses == sorted(set(losses)) and losses[0] == 0,
                            f"at {level} competing UEs, losses start at 0 and increase, once each")
        for disturbance in data["disturbances"]:
            require(disturbance["site"] in sites, "a disturbance names an undeclared site")
            require(disturbance["leg"] in legs, "a disturbance names an undeclared leg")
            kind = legs[disturbance["leg"]]["kind"]
            # An LTE leg has no rate to change, and a point-to-point leg has no radio or cell.
            require((disturbance["kind"], kind) in {("rate", "point_to_point"), ("radio_loss", "lte"),
                                                    ("cell_load", "lte")},
                    f"a {disturbance['kind']} disturbance cannot apply to a {kind} leg")
            if disturbance["kind"] == "cell_load":
                require(disturbance["competing_ues"] <= MAX_COMPETING_UES,
                        f"cell load beyond the model's valid range of {MAX_COMPETING_UES} competing UEs")
    elif kind == "CapabilityManifest":
        _unique(data["capabilities"], "capability_id")
        for cap in data["capabilities"]:
            require(bool(cap["evidence_refs"]), "enabled capability needs evidence")
    elif kind == "StudyManifest":
        _unique(data["treatments"], "treatment_id")
        assembly = data["assembly"]
        _unique(assembly["result"]["cohorts"], "cohort_id")
        for cohort in assembly["result"]["cohorts"]:
            _window(cohort["generation_window"])
        require(all(type(c) in (int, float) and c >= 0 for c in assembly["planning"]["action_costs"].values()),
                "frozen action costs must be nonnegative numbers")
        for treatment in data["treatments"]:
            require({b["stage_id"] for b in treatment["bindings"]} == set(STAGES)
                    and len(treatment["bindings"]) == len(STAGES), "exactly one binding per stage required")
            for binding in treatment["bindings"]:
                require(binding["configuration_hash"] == digest(binding["configuration"]), "configuration hash mismatch")
                if binding["information_regime"] == "oracle_state":
                    require(binding["arm"] == "oracle", "only Oracle may request direct truth")
    elif kind in ("AdapterObservationBatch", "TelemetryBatch"):
        _window(data["window"])
        require(data["window"]["end_s"] <= data["watermark_s"], "batch window exceeds watermark")
        _unique(data["observations"], "observation_id")
        for observation in data["observations"]:
            _observation(observation, data["watermark_s"])
        if data["omitted_metrics"] or any(o["quality"] == "missing" for o in data["observations"]):
            require(data["completeness"] < 1, "incomplete telemetry cannot declare complete coverage")
    elif kind == "PlanningProblem":
        require(not set(data["known_predicates"]) & set(data["unknown_predicates"]), "known/unknown predicates overlap")
        require(all(type(c) in (int, float) and c >= 0 for c in data["action_costs"].values()),
                "action costs must be nonnegative numbers")
    elif kind == "PlanProposal":
        require(data["estimated_cost"] == sum(step["cost"] for step in data["steps"]), "plan cost mismatch")
    elif kind == "ResolutionRecord":
        _unique(data["decisions"], "proposal_id")
        require({x["proposal_id"] for x in data["decisions"]} == set(data["proposal_ids"]),
                "resolution must account for every supplied proposal")
    elif kind == "ActionCommand":
        _command(data)
    elif kind == "ActionReceipt":
        applied = data["disposition"] == "applied"
        require((data["applied_at_s"] is not None) == applied, "only applied receipts have application times")
        require(not applied or bool(data["application_observation_ids"]), "application needs observed evidence")
        require(applied or data["reason"] is not None, "non-applied receipt needs reason")
    elif kind in ("ResultInput", "ResultRecord"):
        for cohort in data["cohorts"]:
            _window(cohort["generation_window"])
            accounted = sum(cohort[k] for k in ("delivered_on_time", "delivered_late", "lost", "pending"))
            require(accounted == cohort["generated"], "cohort loses or double-counts generated demand")
        if kind == "ResultRecord":
            _window(data["before_window"])
            _window(data["after_window"])
            for m in data["measurements"]:
                require((m["value"] is None) == (m["quality"] == "unknown"), "unknown measurement requires null")
                if m["unit"] == "ratio" and m["quality"] == "measured":
                    require(m["denominator"] > 0 and 0 <= m["numerator"] <= m["denominator"], "invalid ratio population")
                    require(0 <= m["value"] <= 1, "invalid measured ratio")
    elif kind == "AssuranceReport":
        for claim in data["claims"]:
            if claim["verdict"] in ("met", "violated"):
                require(bool(claim["evidence_refs"]), "conclusive claim requires evidence")
    elif kind == "Message":
        _terminal(data)
        require(data["event_time_s"] <= data["available_at_s"], "message available before event")
        require(data["decision_watermark_s"] <= data["event_time_s"], "output predates decision watermark")
        payload = Record.from_dict(data["payload"])
        require(payload.kind not in {"Message", "DatasetArtifact", "StageInvocation", "StudyManifest", "ScenarioSpec"},
                "administrative records cannot be provider payloads")
        if payload.kind == "BoundaryOutcome":
            require(data["status"] == payload.data["status"], "terminal status mismatch")
        refs = set(data["privileged_source_refs"])
        if payload.kind in ("TelemetryBatch", "AdapterObservationBatch"):
            require(all(set(o["privileged_source_refs"]) <= refs for o in payload.data["observations"]), "lost observation privilege")
        require((data["information_regime"] == "oracle_state") == bool(refs), "privilege regime/lineage mismatch")
    elif kind == "DatasetArtifact":
        _terminal(data, "terminal_status")
        require(data["record_count"] == len(data["message_ids"]) == len(data["message_hashes"]), "dataset count mismatch")
        if data["time_coverage"] is not None:
            _window(data["time_coverage"])
        require((data["information_regime"] == "oracle_state") == bool(data["privileged_source_refs"]), "dataset privilege mismatch")
    elif kind == "StageInvocation":
        _terminal(data)
        require((data["information_regime"] == "oracle_state") == bool(data["privileged_source_refs"]), "invocation privilege mismatch")
    elif kind == "ProviderSpec":
        require(not data["direct_truth_access"] or data["arm"] == "oracle", "only Oracle may declare truth access")


@dataclass(frozen=True, init=False)
class Record:
    """Immutable canonical bytes. Accessors return detached copies, not mutable internals."""

    _raw: bytes

    def __init__(self, kind, data):
        validate(kind, data)
        core = {"record_type": kind, "schema_version": "1", "data": data}
        object.__setattr__(self, "_raw", canonical({**core, "content_hash": digest(core)}))

    @classmethod
    def from_dict(cls, document):
        require(type(document) is dict and set(document) == {"record_type", "schema_version", "data", "content_hash"},
                "invalid record envelope")
        require(document["schema_version"] == "1", "unsupported schema version")
        result = cls(document["record_type"], document["data"])
        require(result.content_hash == document["content_hash"], "record content hash mismatch")
        return result

    @classmethod
    def from_json(cls, raw):
        return cls.from_dict(decode(raw))

    def to_json(self):
        return self._raw

    def to_dict(self):
        return decode(self._raw)

    @property
    def kind(self):
        return self.to_dict()["record_type"]

    @property
    def data(self):
        return self.to_dict()["data"]

    @property
    def content_hash(self):
        return self.to_dict()["content_hash"]
