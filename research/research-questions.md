# ECoRA research question and scope

**Status: proposed research framing, 2026-09-21. No experimental results.**

[ECoRA index](../docs/ECoRA/README.md) · [Experimental design](../docs/ECoRA/experiments.md)

## System presentation question

**Without failure labels available to the controller, how can knowledge-based diagnosis,
symbolic recovery planning and local conflict resolution be integrated into an auditable
control loop, with outcomes verifiable through evidence, over a simulated wireless
backhaul network?**

This is the system conception question. RQ0 below evaluates its service contribution.
Failure labels are excluded from Proposed and Null controller inputs; explicitly privileged
references and the independent evaluator retain their declared truth access. Verifiable
outcomes mean contract checks, replay and independent measurements, not a system-wide
formal verification claim. The [selected v1 scope](../docs/ECoRA/v1-scope.md) fixes the model.

## Primary question

**RQ0. Under which workload, resource and observability conditions do expert reasoning,
planning and local agent coordination improve the maintenance or recovery of declared
SCADA and AMI service requirements over fixed and trivial control baselines, and how
much of the remaining performance gap is attributable to decision methods versus
available information?**

The initial test bed is synthetic SCADA/AMI competition over wireless backhaul between
site and central aggregation gateways, preceded by a finite logical resource model.
The selected model uses an ns-3 LTE transport leg and an abstract alternative path.
Both services contend at a measured shared bottleneck. Field access networks are outside
scope, and the alternative surrogate does not demonstrate a second RAT.

ECoRA provides controlled stage substitutions, observation and action contracts, and
traceable outcome evidence to answer RQ0. It has not yet supplied an empirical answer.
Architectural novelty, universal controller superiority and guaranteed convergence are
not hypotheses of this study.

## Operational subquestions

| Part of RQ0 | Comparison and evidence | Existing question IDs |
| --- | --- | --- |
| Decision-method contribution | Matched expert, planner and coordination comparisons; paired Proposed versus Null stage substitutions; fixed-policy service reference | RQ-E, RQ-P, RQ-G, RQ-C, RQ-H |
| Conditions for useful control | Effects by frozen workload, resource, disturbance and observation conditions, including overload and no-intervention cases | RQ-C, RQ-F, RQ-T |
| Decision-method headroom | Contract-limited certified reference versus Proposed with matched information, objectives, actions and downstream methods | RQ-H |
| Information limits | Contract-limited versus privileged current-state references, supported by observation interventions or indistinguishable histories requiring different decisions | RQ-T |
| Credibility of service claims | Independent fixed evaluation of service, stability, recovery, execution validity and evidence coverage | RQ-A, RQ-F |

The existing [hypotheses and treatments](../docs/ECoRA/experiments.md#research-questions-and-hypotheses)
operationalise these subquestions. Within-arm method comparisons and stage ablations
retain separate manifests because they answer different attribution questions.

## Meaning of improvement

Service satisfaction means meeting the frozen per-class requirements: SCADA transaction
deadlines and delivery obligations, and AMI delivery, age and minimum-service obligations.
SCADA protection is not joint service success when AMI starves. Deferred readings remain
generated demand with delivery obligations.

Recovery means returning to service satisfaction for a declared sustained recovery window
following a disturbance. Stabilisation means bounded action, claim or allocation churn
over its own declared window. Stable starvation is service failure; recovery and
stabilisation must be measured separately.

Report per-run SCADA deadline misses, AMI delivery/age and starvation, recovery,
coordination overhead and execution validity. Numeric requirements, windows, budgets and
practically meaningful effect thresholds belong in the existing
[parameter register](../docs/ECoRA/experiments.md#parameter-register) and eventual frozen
ParameterSet. An aggregate score cannot conceal a failed class requirement or unsafe action.

Evidence for improvement must establish a prespecified practically meaningful paired
effect with uncertainty under declared service and safety criteria. No improvement,
service tradeoffs, nonrecovery, instability and insufficient evidence are admissible
answers. Nonsignificance is not equivalence; solver timeout is not physical infeasibility.

## Attribution and evidence boundary

Hold scenario versions, exogenous random streams, offered demand, requirements, action
authority and study scoring fixed across the relevant paired treatments. Runs, not
packets, are independent replications. Action-changing substitutions require their own
causally valid simulator continuation.

The planned 81-configuration screen varies telemetry, diagnosis, planning and resolution
on a tractable frozen set. The separately frozen nine-configuration confirmation measures
conditional effects around all-Proposed. Additional method and information comparisons
require separate budgets. These designs do not establish universal superiority.

Oracle-minus-Proposed is conditional reference headroom, not an automatic decomposition
of algorithmic and information limitations. Truth access is explicit and restricted to
current state in the initial Oracle regime. Symbolic optimality is not a packet-service
upper bound without a certified service model. See [stage arms](../docs/ECoRA/stage-arms.md).

Conclusions apply only to the executed model, frozen scenarios, observation contract,
action catalog and treatment versions. The initial study does not establish industrial
protocol compliance, field safety, a genuine second RAT from a path surrogate, energy
benefits, cyberattack resilience or general convergence. Novelty relative to prior work
requires a separate literature synthesis; this document makes no such claim.

## Selected scope decisions

| Decision | Selected outcome |
| --- | --- |
| Workloads | Central SCADA request/response transactions; independently generated site AMI readings with bounded first-release deferral and complete demand accounting |
| Network | Stationary LTE backhaul transport plus point-to-point alternative surrogate and a measured common egress bottleneck |
| Agents | Per-site/service agents, site-local visibility, versioned site path actuator and AMI-owned release queue |
| Success and safety | Per-site/class requirements; separate service, recovery and stability; mandatory authority, evidence, obligation and execution invariants |
| References | Bounded configuration search, exact proposal-subset resolution and a separate finite information-ambiguity problem |
| Feasibility | Contracts and finite replay first; overlapping methods/integration; explicit local compute, storage and study-run envelope |

The [v1 scope](../docs/ECoRA/v1-scope.md) and
[initial parameter block](../docs/ECoRA/experiments.md#initial-v1-values) complete these
design decisions. Implementation, pilot calibration and study freeze remain later work;
the simulator and research methods remain planned. The [contract foundation](../software/README.md)
now supplies executable schemas and audited provider boundaries, without an empirical answer to RQ0.
