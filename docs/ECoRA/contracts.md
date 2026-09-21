# Contracts and causal execution

**Status: executable contract schemas and boundary checks implemented; domain providers and simulator planned.** [Index](README.md)

This document is the end-to-end contract map. The normative stage boundaries are [Interfaces](../../system/interfaces.md), [Telemetry](../../system/telemetry-contract.md) and [Action](../../system/action-contract.md). Their serialisation, logging, authority and substitution rules apply to every arm. Catalogs below summarise those contracts; future changes must update the normative owner first.

## Common envelope

Every inter-stage record is serialisable and durably logged using the [canonical envelope](../../system/interfaces.md#message-envelope-and-durable-log). It carries message/schema identity, study and frozen set identity, stage invocation, provider/version/arm, information regime, causal parents, dataset references and hashes. Run-scoped records also name the scenario revision, run, event/availability times and decision watermark. Study-level reports name contributing invocations/datasets rather than inventing one run ID or simulation timestamp. Record IDs are message IDs in this envelope, not a competing identifier scheme. Numeric settings reference the parameter register.

The provenance chain is **study → scenario → run → stage → dataset**. A stage invocation logs its input references, serialised state and every output, including empty, no-op, rejected, timeout and error outcomes. A replacement provider consumes the same schema and returns the same schema. Configuration selects Null, Proposed or Oracle; orchestration does not fork by arm.

| Record | Required payload |
| --- | --- |
| StudyManifest | Frozen scenario-set version/hash, stage/arm provider bindings, information permissions, factorial/confirmation matrix, compute/storage budget, analysis/scoring versions, seed policies, capability and parameter references |
| ScenarioSetManifest | Immutable version, member scenario revisions/hashes, selection/aggregation weights, benchmark definitions and optional parent-set reference |
| ScenarioSpec | Topology, flow definitions, service requirements, initial state, disturbance schedule, parameter-set reference, needed capabilities |
| CapabilityManifest | Adapter/model versions, supported observations and actions, abstraction boundaries, timing mode, exercised evidence references |
| StageInvocation | Stage/provider/arm, input and output datasets, state/random-stream snapshots, timing, information regime and terminal status |
| DatasetArtifact | Immutable schema/format, record count, coverage, content hashes, producing invocation and source datasets |
| TelemetryBatch | Window, sequence, source records, completeness, drop/missing indicators and stream watermark |
| DiagnosisRecord | Hypotheses, support and counterevidence, rule trace, unresolved conflicts, confidence semantics |
| PlanningProblem | State projection, unknowns, goals, operator catalog, cost function and budget |
| PlanProposal | Ordered steps or dependency graph, expected effects, assumptions, estimated cost, validity horizon |
| ResolutionRecord | Proposal IDs, admit/defer/reject outcome, conflicts, claim versions, authority scope and reason |
| ActionCommand | Operator, target, arguments, expected state version, not-before time, expiry, idempotency key |
| ActionReceipt | Command ID, adapter disposition, actual application time, observed actuator state, failure/unknown reason |
| ResultRecord | Before/after windows, eligible population, measurements, action associations and uncertainty |
| AssuranceReport | Study and scenario-set version/hash, scoped requirement claims, evidence coverage, method/run manifests and limitations for research review |

A report may say a requirement was met without claiming that the controller caused the improvement. Causal benefit comes from the paired experimental comparison.

## Scenario and capabilities

Scenario validation resolves every required capability before a run starts. A capability includes its scope: route change per site is not route change per flow. Each flow declares source, destination, service class, payload model, timing process, deadline semantics and offered-load process.

Run admission verifies the study is frozen, the scenario revision belongs to its ScenarioSetManifest, all content hashes match and the treatment is declared in its matrix. A mismatch rejects admission. Runtime authority covers only allowed run-state mutations; neither the controller nor the runner can amend the scenario set, workload definition, requirements or scoring policy. Research revision creates a successor set and a new study under [Methodology](methodology.md).

The [selected v1 network](v1-scope.md#wireless-backhaul-model) is site-to-central wireless
backhaul using an LTE transport leg and an abstract alternative path. Field access is
outside scope. Its manifest must record the selected helper classes and resolved runtime
attributes, including the nominal carrier settings; these do not support a deployment claim.

An AMI workload needs its own generated messages, identifiers, queues or observable flow mapping, delivery trace and service requirements. Until that exists, AMI experiments remain planned.

## Telemetry catalog

All entries below are planned ECoRA observations. Availability is checked per adapter and run.

| Signal | Unit and semantics | Source requirement |
| --- | --- | --- |
| packet_generated | Event; unique flow/packet ID and creation time | Application instrumentation |
| packet_delivered | Event; matching ID and delivery time | Receiver instrumentation |
| scada_response | Event; request ID and completion time | Request/response application |
| queue_occupancy | Bytes or packets, explicitly declared | Queue trace |
| offered_load | Bits/s over a named interval | Generated payload accounting |
| goodput | Unique delivered application bits/s | Receiver trace, excluding duplicates |
| packet_drop | Event and reason where available | Queue/device/application trace |
| path_state | Applied route/path and version | Actuator state observation |
| path_probe | Probe/leg identity, send/acknowledgement times or timeout | Gateway probe application, with availability gating |
| claim_state | Claim ID, owner, resource and expiry | Local coordination substrate |
| control_message | Event, size and endpoints | Coordination transport |
| link_measurement | Named radio metric and unit | Actual model trace; unavailable on an abstract path unless explicitly modelled |

Queue occupancy is not inferred from end-to-end delay as if directly measured. A configured packet error rate is a model parameter, not an observed error ratio. Host computation time is not network latency.

Windows specify interval convention and packet population. Service evaluation normally uses generation cohorts, followed long enough to classify their outcomes. Packets still unresolved at run end are censored or classified by the declared deadline policy; they are never silently removed from denominators. Warm-up, disturbance, recovery and drain intervals are explicit.

## Observation-to-state projection

Projection is a pure, versioned function of an admissible evidence window and declared thresholds. It produces known predicates, unknown predicates and a provenance map. Threshold-derived facts are logged as derived. A missing signal can yield insufficient evidence, not a fabricated healthy state.

Null and Proposed providers see only their contracted observations at the decision watermark. The initial Oracle arm may access separately logged current simulator truth through a privileged interface, never future measurements. Late observations retain their actual availability time. A corrected report may use them retrospectively, but the historical decision trace is not rewritten. Optional future-aware references require a separate study and cannot be confused with the current-state Oracle.

## Action catalog

These are proposed operator families. Each is disabled until the selected adapter implements and verifies it.

| Operator | Preconditions | Predicted configuration effect | Limitation or compensation |
| --- | --- | --- | --- |
| select_path(scope, path) | Target exists, alternate reachable by declared evidence, actuator supports scope, valid claim | Change selected path | Does not guarantee packet delivery; compensate by another selection |
| set_ami_pacing(flow, profile) | AMI classification, supported pacing, profile within workload contract | Change eligible application release schedule | Cannot erase backlog or alter evaluation demand to manufacture success |
| defer_eligible_message(flow, message) | Message is deferrable and still within its declared limit | Schedule a later transmission attempt | Records resulting delay; mandatory traffic cannot be silently discarded |
| publish_mark(resource, payload) | Local visibility and valid schema | Create expiring environmental record | A mark alone grants no reservation |
| release_claim(claim) | Issuer owns claim, version matches | End intended resource use | Already applied network effects remain |
| yield(resource) | Agent can defer its proposed use | Withdraw or delay local proposal | Existing service obligations still count |
| no_op(scope) | Scope and reason explicit | No mutation | Still produces a decision record and evaluable result |

Rate scheduling or radio scheduler manipulation is not implicitly available through these names. A later catalog may add it after simulator support is established. Disturbance injection belongs to the experimental harness and is never available to the controller as a repair action.

Every operator specifies a read set, write set, resource footprint, action cost, expiry, reversibility class and observation confirming application. Its write set must exclude the study manifest, scenario-set definitions and evaluation policy. Dispatch checks authority, safety invariants and the timing horizon in addition to physical preconditions. Concurrent proposals conflict when their effects or resource requirements cannot coexist, not merely because they arrive at the same timestamp.

## Resolution and concurrency

Central mode uses an explicit arbitration policy. Eco mode uses local detection, marks and distributed protocol choices. In both, the actuator enforces physical consistency, such as rejecting stale versions. The actuator does not select a global service-optimal winner.

For simultaneous events, ns-3's deterministic execution order must be recorded. Fixed agent-ID order is an implementation convenience with potential bias, so activation order is a sensitivity factor. Lease renewal, expiry, stale reads and delayed messages have explicit semantics.

An unenforced mark is advisory. A reservation requires a grant protocol and actuator support. If a global reservation service is introduced, label that treatment as centrally arbitrated rather than presenting it as fully decentralised.

## Assurance contract

A requirement consists of subject/class, metric definition, threshold reference, evaluation window, denominator, acceptable missingness, and violation budget. Every claim carries `study_id`, `scenario_set_version`, `scenario_set_hash`, contributing scenario/run references and evaluator version, even when exported separately from its report. Cross-set comparison records must identify each set explicitly; they cannot masquerade as a single-set claim. Verdicts are:

- **Met:** adequate evidence satisfies the configured predicate.
- **Violated:** adequate evidence demonstrates a breach.
- **Inconclusive:** evidence or observation duration is insufficient.
- **Not applicable:** the declared condition for applicability is absent.

The report includes separate service and coordination outcomes. Service can fail while coordination is stable, or pass during continuing churn. A useful report contains:

1. Study and frozen scenario-set version/hash, member scenarios, model, treatment, seed and evaluator manifest.
2. Offered and delivered workload by class, including deferred/dropped demand.
3. Requirement verdicts with packet counts, windows and coverage.
4. Diagnosis and plan traces; admitted, rejected, failed and unknown actions.
   Each trace identifies the stage invocation, arm, datasets and any privileged evidence lineage.
5. Stabilisation, starvation, fairness and recovery measurements.
6. Paired comparison results and uncertainty, when a comparison exists.
7. Model limitations and unsupported claims.
8. Evidence gaps and open questions for separate research review; no automatic scenario revision or active-study mutation.

Assurance is observational during a study. It cannot adjust thresholds, scenario membership or scoring between runs to change a verdict. Scenario-set revision proposals belong to the research methodology and are separate artifacts, not runtime commands. An evaluator correction requires a versioned reanalysis with explicit impact on prior claims.
