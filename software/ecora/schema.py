"""Source of the exportable Draft 2020-12 schema, independent of provider code."""

STAGES = ("telemetry", "diagnosis", "planning", "resolution", "action", "result", "assurance")
ARMS = ("null", "proposed", "oracle")
REGIMES = ("contract_only", "oracle_state")
STATUSES = ("ok", "empty", "no_op", "rejected", "error", "timeout")
OPERATORS = ("select_path", "set_ami_pacing", "defer_eligible_message", "publish_mark",
             "release_claim", "yield", "no_op")


def enum(*values):
    return {"enum": list(values)}


def array(item, minimum=0, unique=False):
    return {"type": "array", "items": item, "minItems": minimum, "uniqueItems": unique}


def obj(**properties):
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


def ref(name):
    return {"$ref": f"#/$defs/{name}"}


def nullable(item):
    return {"anyOf": [item, {"type": "null"}]}


TEXT = {"type": "string", "minLength": 1}
ID = {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:/-]*$"}
HASH = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
COUNT = {"type": "integer", "minimum": 0}
TIME = {"type": "number", "minimum": 0}
POSITIVE = {"type": "number", "exclusiveMinimum": 0}
PROBABILITY = {"type": "number", "minimum": 0, "maximum": 1}
BOOL = {"type": "boolean"}
JSON_OBJECT = {"type": "object"}  # Only explicit configuration/state/trace extension points.
IDS = array(ID, unique=True)
HASHES = array(HASH, unique=True)
UNIT = enum("s", "byte", "packet", "bit/s", "ratio", "count", "dBm", "id", "event")


def definitions():
    d = {}
    d["Window"] = obj(start_s=TIME, end_s=TIME)
    d["Reason"] = obj(code=ID, detail=TEXT)
    d["Scope"] = obj(study_id=ID, scenario_set_version=ID, scenario_set_hash=HASH,
                     scenario_id=ID, scenario_revision=ID, scenario_hash=HASH, run_id=ID)
    d["Capability"] = obj(capability_id=ID, kind=enum("observe", "actuate", "truth"),
                          target=ID, service=enum("scada", "ami", "shared"),
                          name=ID, unit=nullable(UNIT), evidence_refs=IDS)
    d["Binding"] = obj(stage_id=enum(*STAGES), provider_id=ID, provider_version=ID,
                       arm=enum(*ARMS), input_types=array(ID, 1, True),
                       output_types=array(ID, 1, True), state_schema_version=ID,
                       information_regime=enum(*REGIMES), allow_privileged_inputs=BOOL,
                       capability_ids=IDS, configuration=JSON_OBJECT,
                       configuration_hash=HASH)
    d["ScenarioMember"] = obj(scenario_id=ID, revision=ID, content_hash=HASH, weight=POSITIVE)
    d["ScenarioSetManifest"] = obj(set_id=ID, version=ID,
                                   members=array(ref("ScenarioMember"), 1),
                                   benchmark_definition=TEXT, parent_hash=nullable(HASH))
    d["Requirement"] = obj(requirement_id=ID, target=ID, service=enum("scada", "ami"),
                           metric=ID, unit=UNIT, comparator=enum("le", "ge"),
                           threshold=TIME, window_s=POSITIVE, denominator=TEXT,
                           missingness_limit=PROBABILITY)
    d["Flow"] = obj(flow_id=ID, source=ID, destination=ID, service=enum("scada", "ami"),
                    generation=JSON_OBJECT, payload_bytes=COUNT, deadline_s=POSITIVE,
                    max_deferral_s=TIME)
    d["ScenarioSpec"] = obj(scenario_id=ID, revision=ID, synthetic={"const": True},
                            topology=JSON_OBJECT, flows=array(ref("Flow"), 1),
                            requirements=array(ref("Requirement"), 1), initial_state=JSON_OBJECT,
                            disturbances=array(JSON_OBJECT), parameter_set_hash=HASH,
                            required_capability_ids=IDS)
    d["CapabilityManifest"] = obj(adapter_id=ID, adapter_version=ID, model_version=ID,
                                  capabilities=array(ref("Capability")), limitations=array(TEXT),
                                  timing_mode=enum("fixed_simulated", "logical"))
    d["Treatment"] = obj(treatment_id=ID, bindings=array(ref("Binding"), len(STAGES)))
    d["StudyManifest"] = obj(study_id=ID, frozen={"const": True},
                             scenario_set_version=ID, scenario_set_hash=HASH,
                             treatments=array(ref("Treatment"), 1),
                             capability_manifest_hash=HASH, parameter_set_hash=HASH,
                             analysis_version=ID, scoring_version=ID, seed_manifest=JSON_OBJECT,
                             compute_budget_s=POSITIVE, storage_budget_bytes=COUNT,
                             access_policy_version={"const": "v1"})
    d["Observation"] = obj(observation_id=ID, subject=ID, service=enum("scada", "ami", "shared"),
                           metric=ID, unit=UNIT, value={}, quality=enum("observed", "derived", "missing"),
                           missing_reason=nullable(ref("Reason")), event_time_s=TIME,
                           available_at_s=TIME, window=ref("Window"), source=ID,
                           sampling_policy=ID, valid_min=nullable({"type": "number"}),
                           valid_max=nullable({"type": "number"}), assumptions=array(TEXT),
                           evidence_kind=enum("measured", "derived", "simulator_truth"),
                           capability_id=ID, source_observation_ids=IDS,
                           formula=nullable(TEXT), privileged_source_refs=IDS)
    batch = obj(observations=array(ref("Observation")), watermark_s=TIME,
                window=ref("Window"), sequence=COUNT, completeness=PROBABILITY,
                omitted_metrics=IDS)
    d["AdapterObservationBatch"] = batch
    d["TelemetryBatch"] = batch
    d["Hypothesis"] = obj(label=ID, support_ids=IDS, counterevidence_ids=IDS,
                          status=enum("supported", "contradicted", "unknown"))
    d["DiagnosisRecord"] = obj(hypotheses=array(ref("Hypothesis")), rule_trace=array(JSON_OBJECT),
                               unresolved_conflicts=IDS, confidence_semantics=enum("categorical"))
    d["PlanningProblem"] = obj(known_predicates=IDS, unknown_predicates=IDS, goals=IDS,
                               operator_catalog_version=ID, action_costs=JSON_OBJECT,
                               expansion_budget=COUNT, time_budget_s=POSITIVE,
                               memory_budget_bytes=COUNT, horizon_steps=COUNT)
    d["PlanStep"] = obj(operator=enum(*OPERATORS), target=ID, arguments=JSON_OBJECT,
                        preconditions=IDS, add_effects=IDS, delete_effects=IDS, cost=TIME)
    d["PlanProposal"] = obj(proposal_id=ID, agent_id=ID, site_id=ID,
                            service=enum("scada", "ami"), steps=array(ref("PlanStep")),
                            assumptions=IDS, estimated_cost=TIME, valid_until_s=TIME,
                            goal_status=enum("achieved_in_model", "unmet", "unknown"),
                            certificate_ref=nullable(ID))
    d["ResolutionDecision"] = obj(proposal_id=ID, disposition=enum("admit", "defer", "reject"),
                                  reason=ref("Reason"), conflicting_proposal_ids=IDS)
    d["ResolutionRecord"] = obj(resolution_id=ID, proposal_ids=IDS,
                                decisions=array(ref("ResolutionDecision")), claim_versions=JSON_OBJECT,
                                command_ids=IDS)
    d["ActionCommand"] = obj(command_id=ID, operator=enum(*OPERATORS), catalog_version={"const": "v1"},
                             target=ID, scope=enum("site", "ami_queue", "own_mark", "own_proposal"),
                             service=enum("scada", "ami", "shared"), issuer=ID,
                             arguments=JSON_OBJECT, argument_units=JSON_OBJECT,
                             read_set=IDS, write_set=IDS, resource_footprint=IDS,
                             expected_state_version=COUNT, precondition_evidence_ids=IDS,
                             resolution_id=ID, authority_capability_id=ID,
                             not_before_s=TIME, expires_at_s=TIME, idempotency_key=ID)
    d["ActionReceipt"] = obj(command_id=ID, idempotency_key=ID,
                             disposition=enum("applied", "no_op", "suppressed", "rejected", "failed", "unknown"),
                             applied_at_s=nullable(TIME), resulting_state=JSON_OBJECT,
                             application_observation_ids=IDS, reason=nullable(ref("Reason")))
    d["Cohort"] = obj(cohort_id=ID, generation_window=ref("Window"), generated=COUNT,
                      delivered_on_time=COUNT, delivered_late=COUNT, lost=COUNT, pending=COUNT,
                      duplicate_deliveries=COUNT, censored=BOOL, deadline_s=POSITIVE)
    d["Measurement"] = obj(metric=ID, unit=UNIT, value=nullable({"type": "number"}),
                           quality=enum("measured", "unknown"), numerator=COUNT, denominator=COUNT)
    d["ResultInput"] = obj(receipt_ids=IDS, observation_ids=IDS, cohorts=array(ref("Cohort")))
    d["ResultRecord"] = obj(before_window=ref("Window"), after_window=ref("Window"),
                            cohorts=array(ref("Cohort")), measurements=array(ref("Measurement")),
                            action_ids=IDS, uncertainty=TEXT)
    d["Claim"] = obj(requirement_id=ID, verdict=enum("met", "violated", "inconclusive", "not_applicable"),
                     evidence_refs=IDS, reason=ref("Reason"))
    d["AssuranceReport"] = obj(study_id=ID, scenario_set_version=ID, scenario_set_hash=HASH,
                               contributing_run_ids=IDS, contributing_invocation_ids=IDS,
                               contributing_dataset_ids=IDS, evaluator_version=ID,
                               claims=array(ref("Claim")), limitations=array(TEXT),
                               created_at_utc={"type": "string", "format": "date-time"})
    d["BoundaryOutcome"] = obj(status=enum(*STATUSES[1:]), reason=ref("Reason"))
    d["Replay"] = obj(mode=enum("none", "boundary_playback", "component_substitution", "closed_loop_branch", "trace_only"),
                      original_run_id=nullable(ID), original_invocation_id=nullable(ID))
    d["Message"] = obj(message_id=ID, scope=ref("Scope"), stage_invocation_id=ID,
                       source_stage=enum("harness", *STAGES), destination_stage=enum(*STAGES, "sink"),
                       provider_id=ID, provider_version=ID, arm=enum(*ARMS), configuration_hash=HASH,
                       sequence_number=COUNT, correlation_id=ID, parent_message_ids=IDS,
                       input_dataset_ids=IDS, output_dataset_id=ID, clock_domain={"const": "simulation"},
                       event_time_s=TIME, available_at_s=TIME, decision_watermark_s=TIME,
                       information_regime=enum(*REGIMES), privileged_source_refs=IDS,
                       access_policy_version={"const": "v1"}, serialization_version={"const": "ecora-json-v1"},
                       replay=ref("Replay"), status=enum(*STATUSES), reason=nullable(ref("Reason")),
                       payload=ref("Record"))
    d["DatasetArtifact"] = obj(dataset_id=ID, scope=ref("Scope"), stage_invocation_id=ID,
                               stage_id=enum("harness", *STAGES), provider_id=ID, provider_version=ID,
                               arm=enum(*ARMS), configuration_hash=HASH,
                               message_ids=IDS, message_hashes=array(HASH), record_count=COUNT,
                               source_dataset_ids=IDS, schema_versions=array(ID, unique=True),
                               time_coverage=nullable(ref("Window")), format={"const": "ecora-json-v1"},
                               information_regime=enum(*REGIMES), privileged_source_refs=IDS,
                               terminal_status=enum(*STATUSES), reason=nullable(ref("Reason")))
    d["StageInvocation"] = obj(invocation_id=ID, scope=ref("Scope"), stage_id=enum("harness", *STAGES),
                               provider_id=ID, provider_version=ID, arm=enum(*ARMS),
                               configuration_hash=HASH, input_dataset_ids=IDS, output_dataset_id=ID,
                               prior_state_hash=HASH, next_state_hash=HASH, random_state_hash=HASH,
                               trace_hash=HASH, context_hash=HASH, decision_watermark_s=TIME, state_schema_version=ID,
                               information_regime=enum(*REGIMES), privileged_source_refs=IDS,
                               status=enum(*STATUSES), reason=nullable(ref("Reason")))
    d["Snapshot"] = obj(state=JSON_OBJECT, privileged_source_refs=IDS,
                        state_schema_version=ID)
    d["ProviderContext"] = obj(configuration=JSON_OBJECT, decision_watermark_s=TIME,
                               random_state=JSON_OBJECT, information_regime=enum(*REGIMES),
                               privileged_source_refs=IDS)
    d["ProviderSpec"] = obj(stage_id=enum(*STAGES), provider_id=ID, provider_version=ID,
                            arm=enum(*ARMS), input_types=array(ID, 1, True), output_types=array(ID, 1, True),
                            state_schema_version=ID, capability_ids=IDS,
                            direct_truth_access=BOOL)
    record_names = tuple(name for name in d if name in RECORD_TYPES)
    d["Record"] = {"oneOf": [obj(record_type={"const": name}, schema_version={"const": "1"},
                                  data=ref(name), content_hash=HASH) for name in record_names]}
    return d


RECORD_TYPES = (
    "ScenarioSetManifest", "ScenarioSpec", "StudyManifest", "CapabilityManifest",
    "AdapterObservationBatch", "TelemetryBatch", "DiagnosisRecord", "PlanningProblem", "PlanProposal",
    "ResolutionRecord", "ActionCommand", "ActionReceipt", "ResultInput", "ResultRecord", "AssuranceReport",
    "BoundaryOutcome", "Message", "DatasetArtifact", "StageInvocation", "Snapshot",
    "ProviderContext", "ProviderSpec",
)

INPUT_TYPES = {
    "telemetry": ("AdapterObservationBatch",), "diagnosis": ("TelemetryBatch",),
    "planning": ("PlanningProblem",), "resolution": ("PlanProposal",),
    "action": ("ActionCommand",), "result": ("ResultInput",), "assurance": ("ResultRecord",),
}
OUTPUT_TYPES = {
    "telemetry": ("TelemetryBatch",), "diagnosis": ("DiagnosisRecord",),
    "planning": ("PlanProposal",), "resolution": ("ResolutionRecord", "ActionCommand"),
    "action": ("ActionReceipt",), "result": ("ResultRecord",), "assurance": ("AssuranceReport",),
}


def schema_document():
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "urn:ecora:contracts:1", "$ref": "#/$defs/Record", "$defs": definitions()}
