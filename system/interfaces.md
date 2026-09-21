# Stage interfaces, serialisation and replay

**Status: normative specification; contract foundation implemented, simulator orchestration and replay planned.**

[System index](README.md) · [ECoRA architecture](../docs/ECoRA/architecture.md) · [Stage arms](../docs/ECoRA/stage-arms.md)

These contracts are the ablation seams. A stage is a versioned input/output interface. Null, Proposed and Oracle are interchangeable providers of that interface, selected by a frozen treatment configuration. Removing a stage or bypassing its output type is invalid.

## Interface inventory

| Stage ID | Input type | Output type |
| --- | --- | --- |
| telemetry | AdapterObservationBatch, perception policy | TelemetryBatch with completeness and watermark |
| diagnosis | TelemetryBatch, knowledge and prior diagnostic state | DiagnosisRecord |
| planning | PlanningProblem built from DiagnosisRecord and declared evidence | PlanProposal |
| resolution | PlanProposal, competing claims and local resource view | ResolutionRecord plus admitted ActionCommands |
| action | Admitted ActionCommand and scoped actuator state | ActionReceipt |
| result | Receipts, subsequent observations and cohort specification | ResultRecord |
| assurance | Results, execution evidence and frozen requirements | AssuranceReport with version-scoped claims |

Scenario selection is a frozen study input, not an ablatable decision stage. Study-level aggregation is a fixed evaluation service. All seven stage providers have the three arms specified in [Stage arms](../docs/ECoRA/stage-arms.md); the initial factorial experiment varies only four stages.

A provider implements `invoke(input_messages, prior_state, context) -> output_messages, next_state, trace`. This is a language-neutral contract, not a call to pass live objects. Context contains serialised configuration, the decision watermark and named random-stream state. Simulator and artifact access occurs through explicit ports whose requests and responses are also recorded. No mutable global board, simulator pointer, closure or unlogged database query may supply hidden input.

Stateful blackboards and eco-agents additionally support serialisable snapshot/restore. Incremental marks, subscriptions, retries and expert activations have causal records. These internal records become inter-stage messages whenever they cross a declared boundary.

## Message envelope and durable log

Every inter-stage message, including control, error, timeout, empty and no-op messages, is serialisable and logged. This applies to in-process calls as well as files or network messages.

The planned canonical representation is UTF-8 JSON under versioned schemas; append-only streams use JSON Lines. Numbers are finite, missing values use explicit quality/status fields, units are explicit and object IDs are strings. Canonical encoding rules and the digest algorithm are versioned before implementation. Binary datasets or large arrays use immutable content-addressed references with format, schema and checksums, never process-local pointers.

| Field group | Required data |
| --- | --- |
| Study identity | study_id, scenario_set_version/hash, scenario_revision/hash, run_id |
| Stage identity | stage_id, stage_invocation_id, provider_id/version, arm, configuration_hash |
| Routing | message_id, message_type/schema_version, source_stage, destination_stage, sequence_number |
| Causality | correlation_id, parent_message_ids, input_dataset_ids, output_dataset_id |
| Time | simulation event time, available_at time, decision watermark, declared clock domain |
| Evidence access | information_regime, privileged_source_refs, access-policy version |
| Integrity | payload or immutable payload reference, content_hash, serialization_version |
| Replay | original_run/invocation refs when applicable, replay_mode, snapshot/random-state refs |
| Outcome | ok, empty, no_op, rejected, error or timeout, with typed reason |

Run-scoped invocations use simulation timestamps. Study-level aggregation/reporting records retain their constituent invocation IDs and creation clock rather than inventing a common simulation time.

An invocation lifecycle is `InputRecorded → Started → OutputRecorded → Delivered`, with logged rejection/error/timeout terminal alternatives. Persist inputs before invocation and outputs before downstream delivery. Record a dispatch intent before simulator mutation, then record/reconcile its receipt by idempotency key. A crash does not permit an unlogged command to be silently treated as applied.

Consumers validate schemas, hashes, causal parents, study membership and privileges before delivery. At-least-once transport is permitted; duplicate message IDs must not cause duplicate effects. Gaps, out-of-order messages and logging failures become explicit integrity failures. Stop or quarantine a run when its evidence chain cannot be reconstructed.

## Provenance and dataset ownership

The required lineage is **study → scenario → run → stage → dataset**, with the immutable scenario-set version binding the study and scenario revision. A stage means a concrete invocation of a configured provider, not just its name.

A StageInvocation owns one output DatasetArtifact manifest, which may describe zero output records plus a terminal reason. It references all consumed datasets and its prior-state snapshot. Subsequent stages consume those immutable artifacts, producing a lineage graph. Each dataset records schema, content hashes, record count, time coverage, producing invocation and source datasets. A study-scoped aggregate lists its contributing runs and stage datasets explicitly.

Canonical messages plus snapshots form the replay evidence. A text explanation alone is insufficient. Logs retain Null and Oracle invocations, rejected proposals and unknown outcomes exactly as Proposed invocations.

## Replay modes and limits

| Mode | What is replayed | Valid claim | Status |
| --- | --- | --- | --- |
| Boundary playback | Recorded output of stage N into N+1 | Downstream reproducibility on identical inputs | Implemented |
| Component substitution | Recorded inputs to N plus its state snapshot; replacement output feeds N+1 | Stage behaviour and downstream decisions for the recorded context | Planned |
| Closed-loop branch | Restore a compatible simulator/controller checkpoint or regenerate the causal prefix, then continue with substituted provider | Counterfactual service outcome under that continuation | Planned |
| Trace-only evaluation | Fixed recorded results into result/assurance provider | Evaluator behaviour on the same evidence | Implemented |

A replay re-enters recorded payloads under the replaying run's scope, carrying the run and
invocation they were recorded in, so replayed evidence is attributable and is never joined
to the original run's lineage. Provider state restores from a recorded snapshot through
the same seam, and privilege travels with what is replayed. The two unimplemented modes
are refused rather than approximated: a mode that would license a counterfactual claim
must not be served by machinery that cannot support one.

To ablate N, replay its recorded inputs through the chosen arm, serialise its output and feed that output through the unchanged N+1 interface. Keep a boundary-playback control using the original output. Empty decisions still carry status and trace through every boundary.

After a replacement changes an action, recorded future telemetry from the original run is not its counterfactual outcome. Service-effect claims require a new closed-loop branch/run with matched exogenous inputs. If ns-3 checkpointing is unavailable, regenerate the prefix under the recorded configuration/seeds and verify prefix hashes before branching. Otherwise restrict the result to component replay; do not claim equivalent continuation.

State snapshots include pending events, blackboard revisions, local marks, random-stream states and ordering policy where relevant. If exact reconstruction is unsupported, report that limitation. Wall-clock timing requires a separate measurement; replaying a recorded computation time does not measure the new provider's latency.

## Provider registry and configuration

The registry maps `stage_id + provider_id + provider_version` to input/output schemas, arm, information permissions, supported state format and capability requirements. Null is a real provider, never an absent configuration entry. Missing bindings, unresolved versions, schema mismatch or unavailable Oracle support fail study admission.

Illustrative configuration shape, not an executable run configuration:

```json
{
  "binding": {
    "stage_id": "diagnosis",
    "arm": "null",
    "provider_id": "diagnosis.first_candidate",
    "provider_version": "design-v1",
    "input_schema": "TelemetryBatch/v1",
    "output_schema": "DiagnosisRecord/v1",
    "information_regime": "contract_only"
  },
  "logging": {
    "all_boundaries": true,
    "serialization": "json",
    "state_snapshots": true
  }
}
```

Changing an arm changes a registry binding in the declared treatment matrix, not the orchestration code or the network model. Oracle access is capability-scoped and its use taints the invocation and descendants. A provider cannot shed that label by emitting an otherwise ordinary DiagnosisRecord.

## Contract readiness before pipeline code

The interfaces, [telemetry contract](telemetry-contract.md) and [action contract](action-contract.md) must have agreed schemas, example traces and acceptance criteria before pipeline implementation. Required checks include round-trip serialisation, determinism on replayable inputs, logging completeness, no-op propagation, state restoration, privilege isolation, schema-compatible provider substitution and the separation of replay from closed-loop counterfactual claims.

The [contract package](../software/README.md) now implements versioned schemas, frozen
admission, immutable records/datasets, the provider registry, boundary logging, capability
checks and privilege propagation. Its synthetic substitution demo and tests exercise that
foundation. Provider state restoration and boundary
playback are implemented, alongside a deterministic finite reference world, Null providers
for every stage and run orchestration with independent named random streams. Component
substitution and verified closed-loop continuation remain M2 work; runtime decision
providers remain later work.

## Executable representation

The structural schema is [ecora-v1.schema.json](../data/schemas/ecora-v1.schema.json);
cross-field and admission checks also require the Python validator. Each immutable record
contains `record_type`, `schema_version`, `data` and `content_hash`. A `Message` record's
data contains the envelope above and a nested validated payload record. Hashes use SHA-256
over the canonical record excluding its own hash; the versioned `ecora-json-v1` encoding
is specified in the [package guide](../software/README.md#serialization-and-provenance).
Dataset IDs are invocation-owned identities; manifest content hashes remain separate to
avoid circular hashes between a message and its owning dataset.

Explicit `BoundaryOutcome` records represent empty/no-op/rejected/error/timeout output
when no domain output exists. `AdapterObservationBatch` and `ResultInput` make the ingress
and cohort/receipt input seams executable. All stage schemas exist, and the bundled
fixture providers exercise every stage, but they are contract fixtures carrying no
diagnostic, planning or measurement content. The registry requires every stage binding at
admission.

Two stage inputs are **built from** upstream evidence rather than being the previous
stage's output: a `PlanningProblem` is built from a `DiagnosisRecord`, and a `ResultInput`
from receipts, subsequent observations and a cohort specification. That construction
carries goal selection and cohort choice, which a study holds fixed across a stage's Null,
Proposed and Oracle arms; placing it inside the provider would vary it with the arm under
comparison. It is therefore a separate logged harness invocation that consumes the
upstream dataset for lineage and emits the assembled input. A record the next stage cannot
consume — `DiagnosisRecord`, `ResolutionRecord`, `ActionReceipt` — is addressed to `sink`
and retained as evidence rather than delivered into a seam that would reject it.

The StudyManifest owns what is assembled, in one `assembly` block per study rather than
per treatment. It freezes the planning goals, operator catalog version, action costs,
budgets and horizon, and the cohort identities, generation windows and deadlines. An
assembled input that departs from it is rejected at the boundary. Only the run-derived
parts stay free: known and unknown predicates for planning, and the measured counts for a
cohort. Varying an assembly parameter is therefore a new study, not a new treatment.

Run-scoped messages use simulation seconds; standalone study-level AssuranceReport records
use UTC creation timestamps and contributing run/dataset identities. The current boundary
wrapper is run-scoped and does not implement the later independent study aggregator.

One cooperative writer owns each journal. Complete duplicate delivery is suppressed;
uncertain delivery/dispatch claims require reconciliation instead of automatic retries.
The current implementation does not supply a transactional external actuator, TruthPort,
plugin process sandbox, timer-based provider interruption or automatic crash recovery.
