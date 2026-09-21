# ECoRA v1 scope decisions

**Status: scope selected, 2026-09-21; implementation and validation remain planned.**

[Index](README.md) · [Research questions](../../research/research-questions.md) ·
[Parameter register](experiments.md#parameter-register)

This document fixes what the first version must simulate, observe, control and claim.
It specialises the normative [telemetry](../../system/telemetry-contract.md) and
[action](../../system/action-contract.md) contracts. All numeric settings are owned by
the parameter register; they are synthetic engineering choices, not industry requirements
or calibrated measurements. Changing a scope decision requires a recorded revision;
pilots may revise nominal values before study freeze, with rationale and provenance.

## Presentation and experimental questions

The system presentation question is: **Without failure labels available to the controller,
how can knowledge-based diagnosis, symbolic recovery planning and local conflict resolution
be integrated into an auditable control loop, with outcomes verifiable through evidence,
over a simulated wireless backhaul network?**

The empirical question remains RQ0: under which conditions does that integration improve
SCADA/AMI service, and what decision-method and information limits remain? Verification
here means executable contract checks, replay and independent outcome measurement; it
does not assert formal verification of the entire network or controller.

## Workloads and delivery obligations

The central application generates periodic SCADA requests to each site. Each unique
request produces one response after the declared processing delay when received. Completion
is the first matching response received centrally; the deadline starts at request generation
and includes both directions and site processing. Requests continue independently of earlier
completion. There are no application retries, cancellation or controller deferral of SCADA.
Underlying LTE retransmissions remain model behaviour. Duplicate requests produce no extra
response and duplicate responses add no success. A late response is delivered but missed
its transaction deadline. Missing requests/responses remain in the generated denominator.

Each site's AMI generator creates periodic uniquely identified readings and additional
burst readings on the scenario schedule. Generation never depends on pacing, chosen path
or controller decisions. Each reading must arrive centrally within its age limit. No
coalescing, overwrite, cancellation or application retransmission is allowed. The controller
may delay its first release only within the deferral limit. An oldest-first obligation
timer releases it when that limit is reached even if pacing would wait longer; this timer
is identical in every treatment and is not an intelligent repair. Its releases are logged.
Overflow or transmission loss remains an unmet obligation; expired readings can arrive
late and remain visible in the outcome ledger.

Pacing uses the declared nonzero profiles, a token bucket with a single-reading burst
allowance and FIFO order. It governs gateway AMI release, not generation or the radio
scheduler. The separate AMI minimum-service guard requests prompt release when local
pending demand has seen no observed delivery for the guard interval. The guard is a
Proposed policy feature that can be ablated; the hard deferral limit cannot be ablated.
Neither mechanism guarantees delivery during overload or path failure.

Score cohorts generated in the measurement interval, using half-open time windows.
Warm-up demand runs normally but belongs to a separate cohort. Stop new generation at
measurement end and drain for at least the largest obligation deadline. Delivery exactly
at a deadline succeeds. Run-end interruption before a deadline is right-censoring, not
success or an invented loss. After a deadline elapses, absence of delivery is a violation
when event evidence is complete. Log outstanding, dropped, late and duplicate identities.

## Wireless-backhaul model

The study boundary is **site aggregation gateway to central aggregation gateway**, with
synthetic field endpoints and the central application beyond those boundaries. Field
access networks are outside scope. LTE supplies one backhaul transport leg: site gateways
use UE-side adapters and aggregate their service traffic toward an eNB/EPC and the central
gateway. This application of an LTE link does not model wireless eNB-to-EPC S1 backhaul.
The EPC's internal links remain wired model support, not the alternative radio path.

Select ns-3 release 3.45, `LteHelper`, `PointToPointEpcHelper`, a stationary single-cell
topology, `PfFfMacScheduler`, `FriisSpectrumPropagationLossModel`, no fading, no mobility,
no handover and no carrier aggregation. Both service classes share the default non-GBR
bearer per UE; no class-specific LTE scheduler tuning is a controller action. Export all
resolved attributes, including RLC/HARQ settings inherited from the pinned release, in
the build/run manifest. Selection follows the documented helper and configuration APIs,
not an assertion that this repository already exercises them.
See [ns-3 LTE user documentation](https://www.nsnam.org/docs/release/3.45/models/html/lte-user.html).

Select `PointToPointHelper` with a finite DropTail queue, configured rate, propagation
delay and packet-unit `RateErrorModel` for the alternative leg. It is a transport surrogate
for a second wireless backhaul option, with no represented PHY, MAC, RF interference or
second RAT. The [ns-3 tutorial](https://www.nsnam.org/docs/tutorial/singlehtml/) describes
point-to-point rate/delay configuration and receive error models. A later genuine second
RAT requires a successor model and study; it is excluded from v1 acceptance.

Each site has both legs. Gateway forwarding adapters preserve service/message identities
inside a declared UDP envelope and choose the leg for each newly released datagram. The
central adapter uses the site's same selected leg for outgoing SCADA requests. A versioned
site switch changes both gateway selectors as one synthetic actuator transaction. Packets
already released keep their old leg; there is no duplication, migration or guaranteed
lossless switch. This is an idealised forwarding actuator, not demonstrated routing-protocol
convergence or radio handover. Envelope bytes and processing delay are counted.

Both legs terminate upstream of a shared, rate-limited central egress link to the application.
Both classes' site-to-central traffic must traverse its same finite FIFO queue. Measure its
arrivals, service, drops and occupancy independently. The LTE scheduler and per-site path
queues add possible bottlenecks. Switching can bypass a leg impairment but cannot increase
the common egress capacity. Capacity labels require an uncontrolled pilot and deadline-aware
service evidence; offered bitrate alone cannot certify feasibility.

The harness may reduce the alternative leg's service rate, inject packet loss on its receiver,
and restore the original settings. It also schedules workload bursts and telemetry/mark
delay or loss. Those controls and their current/future schedules never enter ordinary
controller inputs. v1 recovery claims concern these represented disturbances, not diagnosed
physical root causes or adversarial attacks.

## Agent scope, observations and control

Use one agent per site and service class. A local neighbourhood contains the agents at
that site only. Each agent sees its own generation, queue/release, delivery summaries and
service history, plus that site's path selector/version, round-trip probes and unexpired
peer marks. Remote delivery summaries have explicit availability delay; no agent reads a
remote queue or another site's state. The global evaluator has no action authority.

No Proposed or Null provider receives injected-failure labels, configured loss rates,
hidden service capacity, simulator event queues or future schedules. The initial diagnostic
vocabulary is a set of operational predicates: local queue pressure, overdue SCADA,
AMI age risk, no recent path-probe acknowledgement, conflicting local intentions and
insufficient evidence. Hypotheses retain support and contradictions; a missed probe is
not proof of a failed radio. Oracle labels describe only corresponding current model
predicates. The harness disturbance ledger is available for retrospective evaluation.

Queue pressure means occupied bytes reach the registered fraction of configured capacity;
AMI age risk means the oldest undelivered reading reaches the warning age. SCADA is overdue
when a generated transaction has no matching completion at its deadline. Missing inputs
produce unknown predicates. Path viability uses fresh successful probe acknowledgements;
configured link parameters are not substituted for observations.

| Actuator/resource | Ownership and selected v1 behaviour |
| --- | --- |
| Site path selector | Single versioned gateway actuator; both local agents may propose a change, but only one compatible write can be admitted per version |
| AMI release queue | Its AMI agent may set pacing or defer an eligible reading; no authority over SCADA generation or release |
| Intent marks | Issuer owns update/release; visible only within its site; expiry enforced on reads |
| Yield/no-op | Affects only the issuer's pending proposal; obligations remain |

Initial eco resolution uses expiring advisory intent marks, agent-specific random backoff
and a local deterministic tie-break on `(waiting_since, agent_id)` with longest-waiting
first. An agent yields its conflicting proposal when an earlier visible claim wins.
After the contention interval, it may attempt dispatch if no winning live mark is visible.
The actuator uses compare-and-swap on version and rejects stale writes; it never chooses a
global utility winner. Delayed marks can cause races, whose rejections remain evidence.
No resource lease or global reservation is implied. Fixed activation order and alternative
backoff/handshake mechanisms remain separately budgeted sensitivity comparisons.

Select ideal local shared-memory marks for the primary reference treatment; count reads,
writes and serialised bytes, but do not call them network overhead. A separate delayed/lossy
logical-message treatment evaluates communication sensitivity, not RF transport realism.
Provider choice and substrate are frozen per study, never selected from observed outcomes.

At each decision boundary, deliver available events, seal telemetry at its watermark,
compute diagnosis and proposals, resolve local conflicts, then dispatch after the declared
control latency. Apply expiry and current-state checks at dispatch. Log deterministic event
tie ordering. Use simulated fixed latency for matched comparisons and report host reasoning
time separately; measured host time does not silently become simulated delay.

Only the next mutation of a validated plan is eligible for admission at a time; subsequent
steps are revalidated against fresh state. Contention and retry waiting add their simulated
duration before dispatch latency. A retry after proposal expiry requires a fresh proposal,
evidence and version, not an extension of an expired command.

## Service objectives and safety

For each site, evaluate SCADA deadline-miss ratio and completion delivery, AMI within-age
delivery ratio, and AMI minimum goodput while demand is continuously pending. Report age
quantiles separately; received-only age statistics cannot hide undelivered readings.
AMI starvation is the longest continuously pending interval with no unique delivery,
including withheld demand. Apply the floor only to complete windows with continuously
pending demand; no demand is not applicable. Require all applicable per-site/class
predicates for joint satisfaction; do not pool sites to hide failure.

Coordination stability is a full stability window with action changes and claim churn
within their registered limits and no stale-write retry loop. Claim churn counts changed
owner/resource/intent, not same-intent refreshes; refresh overhead is still reported.
Stability has no service predicate. Recovery is the first full sustained recovery window
whose mature cohorts satisfy service requirements after disturbance onset. Report the
window start and evidence-availability time, and also time from restoration. Nonrecovery
is retained with censoring at the last evaluable window.

Every arm preserves authority, message obligations, locality, nonnegative rates, finite
queue accounting, idempotency, current actuator version, expiry and preconditions. Unknown
reachability prevents path mutation. Missing evidence cannot become healthy. A rejected
unsafe proposal is distinct from an applied invariant violation; either is logged, and any
applied invariant violation invalidates a successful-control claim. Requirement satisfaction
is an objective, not a safety promise under overload. No action changes the scenario,
requirements, scoring, demand generation or disturbance state.

## Finite references and method priorities

Start with a logical reference model using the same site/agent ownership and action catalog.
Represent transport as deterministic byte-service FIFO queues with explicit propagation,
the same application obligations and registered logical leg rates. This is a finite
workload per run with discrete events, not an LTE emulator. Its diagnostic truth predicates
derive from those queues and obligations. The symbolic configuration graph is bounded
even though packet-event histories are longer.
Its symbolic configuration enumerates per-site selected path and AMI pacing profile, with
exogenous reachability and observation masks fixed during a bounded planning episode.
Configuration goals concern reachable selected paths and permitted pacing, never predicted
packet delivery. Enumerate reachable states and legal edges; record the optimal-cost table
and graph digest as the planning certificate. Unknown preconditions prohibit an edge.

| Stage | Selected reference problem and permission |
| --- | --- |
| Telemetry | Exact current values of the finite truth projection with privileged lineage |
| Diagnosis | Direct evaluation of the declared current operational predicates; unmodelled physical causes are unsupported |
| Planning | Exhaustive shortest-path solution on the bounded symbolic graph under the shared operator costs and step horizon; goal reachability and cost only |
| Resolution | Enumerate subsets of supplied proposals; retain conflict-free, safe subsets; maximise admitted SCADA proposals, then waiting AMI proposals, then minimise mutation cost; deterministic ID tie-break |
| Action | Direct verified application of the same admitted mutation, authority and simulated latency; may coincide with Proposed when hooks are identical |
| Result | Independent complete-event cohort reconstruction with identities and times |
| Assurance | Independent requirement evaluation with the same frozen scoring and explicit evidence coverage |

The planning and resolution references establish symbolic/proposal optima, not global
service upper bounds. No provider sees the future random sample path. Solver budget
exhaustion returns unknown with its partial bound, never certified optimality.

For information headroom, use a supplemental finite one-decision problem: two hidden
current reachability states with opposite feasible leg choices, identical masked observed
histories, a declared equal prior and binary successful-transfer reward. Enumerate the
common safe actions and exact expected reward for each observation equivalence class;
compare with a current-state reference under the same action authority. If an observation
mask removes evidence required for safe switching, abstention remains mandatory in the
contract-limited arm. This establishes a bound only for that finite decision problem,
not an ns-3 packet-service upper bound. Extra observations split the equivalence class;
retain both states and all outcomes rather than selecting the favourable one.

Select single-engine categorical rule diagnosis, STRIPS forward uniform-cost configuration
planning and the local mark/backoff resolver as the initial Proposed composition, with
per-site input projection. Compare one-rule blackboard experts using identical rules;
compare GPS and A* on the same symbolic problems; compare eco coordination with empty-mark
local resolution. All required methods remain in v1, but do not become hidden factorial levels.

The fixed-policy service reference holds each site's path at its scenario initial setting,
releases SCADA immediately, and holds AMI at the restricted pacing profile, with the same
hard deferral timer and observation/probe overhead. Trivial stage policies retain their
separate definitions in [stage arms](stage-arms.md); a no-intervention B0 is explicitly
composed with no-op planning, not confused with the factorial first-feasible Null planner.

Implement contracts, finite model and replay first. ns-3 integration and decision methods
can then overlap. Oracle infrastructure and independent scoring can start early, but final
Oracle/arm acceptance depends on the implemented methods and adapters. Run the factorial
screen only after all those dependencies pass; then confirmation and reproducibility.

## Preliminary execution budget and closure

The parameter register fixes a small logical screening set (contention, simultaneous
proposals and observation ambiguity), a full backhaul set covering S0 through S7, and S8
as a separate planner microbenchmark. Screen and confirmation are different substrates:
logical interactions are hypotheses for ns-3 confirmation, not transferable effect sizes.
All ns-3 cells still require their declared scoped current-state references to pass support
checks before study admission. Supplemental methods and information tests have an explicit
reserve. Pilot cost, variance and storage precede final membership/replication freeze.

Use one local workstation, capped concurrent workers and bounded solver memory/time. Retain
all required boundary/event evidence; reaching a budget stops at a run boundary or marks an
interrupted run, never silently samples away required logs or shrinks a frozen matrix.
No cloud spending is assumed. If the pilot exceeds the envelope, revise the candidate
study before freeze; an already frozen study retains failed/unfinished-cell accounting.

Scope closure requires this document, registered initial values, contract specialisations,
and a decision record consistent with each other. It does not require completed pilots,
working providers, calibrated thresholds or a frozen comparative study. Those are explicit
later acceptance obligations, not unresolved choices about the first version's purpose.
