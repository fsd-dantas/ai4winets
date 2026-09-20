# Action authority and stage substitution

**Status: planned normative specification; actions remain disabled until adapter support is verified.**

[Interfaces](interfaces.md) · [Stage arms](../docs/ECoRA/stage-arms.md)

An action absent from the catalog is outside the controller's authority. Null, Proposed and Oracle use the same authority boundary. Oracle knowledge or optimality does not grant extra actuators, waive safety, or turn a predicted effect into observed success.

## Command and receipt schema

ActionCommand names the operator/catalog version, target and scope, arguments/units, read/write sets, resource footprint, expected state version, precondition evidence, admitting ResolutionRecord, authority capability, not-before/expiry times and idempotency key. Its envelope and full payload are serialised and logged before dispatch.

ActionReceipt names the command, disposition, actual application time when applicable, resulting actuator state, observation proving application, and rejection/failure/unknown reason. It inherits study/run/stage/dataset provenance and Oracle lineage. A no-op or suppressed command is not an applied command. A receipt confirms application, not service improvement.

## Candidate action catalog

| Operator | Preconditions and scope | Predicted effect | Reversibility and limit |
| --- | --- | --- | --- |
| select_path | Supported site/flow scope, existing target, current evidence for reachability and valid claim | Change selected path | Another path selection can compensate; cannot undo lost packets |
| set_ami_pacing | Identified AMI flow, supported profile within declared workload bounds | Change eligible release schedule | Restore profile; original demand and backlog stay in evaluation |
| defer_eligible_message | Deferrable message within its limit | Schedule later attempt | Delay already incurred cannot be undone |
| publish_mark | Valid local scope, payload schema and expiry | Create environmental record | Expiry/release; advisory unless separately granted |
| release_claim | Matching issuer and version | End resource-use intent | Does not reverse prior network effects |
| yield | Agent may defer this use without violating action authority | Withdraw/delay local proposal | Service obligations remain |
| no_op | Explicit target scope and reason | No mutation | Terminal logged decision, still evaluated |

Every enabled operator must declare cost, latency model, safety predicates, reversibility class, resource conflicts and verification trace. Parameter values are owned by the frozen study's ParameterSet. Fault injection belongs to the scenario harness; it is not a repair action. A route change is not a radio handover without an explicit model.

## Admission and execution arms

Resolution determines which proposal may be dispatched; action execution determines what actually happens. They are separate interfaces and ablation seams.

| Stage | Null | Proposed | Oracle |
| --- | --- | --- | --- |
| Resolution | First feasible proposal under a fixed ordering, defer the rest; explicit no-op if none | Central policy, blackboard-derived policy or local eco protocol | Exact feasible allocation over the supplied proposal set for a declared objective/horizon |
| Action | Suppress mutation and emit a no-op/suppressed receipt referencing the admitted command | Apply through the adapter and reconcile actual state | Exact simulator-level application of the admitted effect, subject to the same catalog, authority and safety |

An Oracle resolver cannot invent proposals outside its input set. A missing action option is upstream headroom. An Oracle executor is available only if the simulator exposes a verified direct-actuation hook. Otherwise the Oracle cell is unsupported and cannot be replaced silently by Proposed.

Matched-latency execution comparisons preserve the declared delay. An ideal zero-delay/failure-free executor is a separate explicitly idealised treatment and cannot be pooled with those comparisons. Perfect execution never guarantees a service requirement under overload.

## Safety and timing invariants

Immediately before dispatch, verify capability, target, state/claim version, preconditions, authority, not-before time, expiry and safety predicates. Every arm retains this check. If uncertainty prevents a required check, reject or abstain rather than assume success.

No operator may write the StudyManifest, ScenarioSetManifest, requirement thresholds, workload obligations or scoring policy. The only permitted runtime mutations are the catalog's scoped effects. Simulator disturbance access remains separate.

All present actions are synthetic simulation actions within the frozen manifest. No real-network control or human-authorised production operation is supported. A future action requiring human authorisation must carry a named approval capability and evidence before dispatch; this does not add an approval step to ordinary simulated runs.

## Failure, replay and compensation

Persist dispatch intent before mutation and reconcile by idempotency key after interruptions. Never retry an unknown command blindly. Rejected, expired, unsupported, no-op and timeout cases all produce typed records and remain in the dataset.

An action-changing replay requires a fresh simulator continuation before its service effect can be evaluated. Recorded outcomes from the original command are not attributed to the substituted command. Compensation is a new admitted/logged action with current preconditions.

Future acceptance checks must verify schema round trips, invariant preservation across all arms, no-op receipts, idempotency, stale-command rejection, truthful application timestamps, privilege labels and agreement between receipts and simulator state.
