# Simulation fidelity and abstraction registry

**Status: planned methodology. The registry below describes the ns-3 world as implemented at build 3.48; the
declaration inside each scenario and its enforcement are planned (B66).** [Index](README.md)

A simulation result holds only within the conditions its model represents. This document states how ECoRA
decides how much fidelity a claim needs, how each modelling choice is declared, and which choices the current
worlds make. The [checklist](simulation-checklist.md) turns it into gates a scenario, a study and a claim must
pass.

The aim is not maximal fidelity at every layer. It is **fitness for purpose**: a model must keep every mechanism
that could change the conclusion of the question it serves.

## Governing rule

The minimum acceptable fidelity is the lowest fidelity at which a justified perturbation of the omitted detail
cannot plausibly reverse the conclusion.

Two consequences follow. An abstraction is judged against a claim, not in general: Friis propagation with no
fading can be adequate for "throttling AMI restores SCADA at a contended egress" and inadequate for "SCADA meets
its deadline at a cell edge". And an omission that could reverse a conclusion must either be modelled or be
varied in a sensitivity study before the claim is made.

## Declaring a choice

Every mechanism class relevant to a claim takes exactly one status:

| Status | Meaning | Required with it |
| --- | --- | --- |
| `included` | Represented explicitly and parameterised | The parameters and their source |
| `abstracted` | Represented by an aggregate, table, surrogate or reduced model | The representation and its validity range |
| `assumed_negligible` | Deliberately omitted because it cannot move the claim | A rationale, and evidence when the claim depends on it |
| `out_of_scope` | Outside the research boundary | A rationale, and the claim it rules out |

`out_of_scope` is not a softer `assumed_negligible`. It names what the result cannot be used for.

## Two worlds, two kinds of evidence

ECoRA runs every scenario in two worlds. The **finite reference model** is a small, deterministic resource model
built for exact references, replay and continuation; it is explicitly not a network result. The **ns-3 world**
is the network substrate, behind the [simulator adapter](../../system/simulator-adapter.md).

Agreement between the two is **verification**: both implement the same declared conditions, and a disagreement
exposes a defect in one of them. It is not **validation**: neither world is compared with a real network, and
every scenario is synthetic. The validity domain of any ECoRA result is therefore the declared model, never a
deployment.

| Activity | Question | Where ECoRA has it |
| --- | --- | --- |
| Verification | Was the model built as specified? | Contract and property tests; cross-world agreement at transitions (B22a) |
| Calibration | Were uncertain parameters fitted to evidence? | The LTE loss-and-load rate table, measured in ns-3 (ADR-29, ADR-30) |
| Validation | Is the model adequate for the target system? | Not claimed. No real-network comparison exists or is planned for v1 |
| Sensitivity | Which assumptions drive the conclusion? | Planned for B48; see [candidate reversals](#assumptions-that-could-reverse-a-conclusion) |

## Registry of the ns-3 world

Read from `software/simulator/src/ecora-sim/lte-leg.h`, `ecora-sim.cc` and the attribute dump in
`data/simulator/ns3-model-manifest.json`. Where a value is an ns-3 default, it is marked so; the manifest
records the defaults of the pinned build.

| Class | Status | Representation | Source |
| --- | --- | --- | --- |
| System boundary | `included` | Site gateways, one LTE leg, one abstract alternative leg, one shared egress, one central application | Scenario topology |
| Spatial world | `abstracted` | Finite and closed: one eNB and its UEs at declared positions; nothing exists outside the cell | Scenario `radio` block |
| Mobility | `out_of_scope` | `ConstantPositionMobilityModel` for every node. Rules out handover and mobility claims | `lte-leg.h` |
| Large-scale path loss | `included` | `FriisSpectrumPropagationLossModel` | `lte-leg.h` |
| Link impairment | `abstracted` | Extra loss in dB per site through `MatrixPropagationLossModel`, 0 dB until a disturbance | ADR-29 |
| Shadowing and small-scale fading | `assumed_negligible` | No fading model (ns-3 default `FadingModel` is empty). Not yet justified for tail-latency claims | Manifest |
| Interference | `out_of_scope` | Single cell, so no inter-cell interference; degradation comes from load and loss instead. Rules out claims about interference-limited cells | `lte-leg.h` |
| Cell load | `abstracted` | `cell_load`: up to 35 competing UEs saturating the uplink at the site's position | ADR-30 |
| PHY and link adaptation | `included` | ns-3 LTE PHY with data and control error models enabled (defaults); CQI from PDSCH (default) | Manifest |
| MAC scheduling | `included` | `PfFfMacScheduler` | `lte-leg.h` |
| Radio control plane | `abstracted` | Ideal RRC (ns-3 default `UseIdealRrc`) | Manifest |
| Queues | `included` | RLC UM transmission buffer sized by the scenario; DropTail on point-to-point legs | `lte-leg.h`, `ecora-sim.cc` |
| Alternative leg | `abstracted` | Point-to-point with declared rate, delay, queue limit and rate error model; no second RAT is claimed (B02) | Scenario, v1 scope |
| Transport | `included` | UDP for every flow; reliability is the application's transaction, not the transport's | `ecora-sim.cc` |
| Traffic | `included` | SCADA request/response with a round-trip deadline; periodic AMI with permissible deferral | Scenario `flows` |
| Disturbances | `included` | Scheduled, declared per site and leg; no stochastic failure process | Scenario `disturbances` |
| Observability | `included` | Only granted signals; the LTE site queue is `derived`; truth is privileged and logged | [Telemetry contract](../../system/telemetry-contract.md) |
| Control timing | `abstracted` | Decisions at declared epochs; explicit control-latency accounting is B25 | [Control loop](../../system/control-loop.md) |
| Compute and inference delay | `assumed_negligible` | Reasoning effort is instrumented (B32) but not charged as simulated time | B32 |
| Energy | `out_of_scope` | No energy claim is made | — |
| Security and adversaries | `out_of_scope` | No attack or adversarial-observation claim is made | — |
| Randomness | `included` | ns-3 seed fixed, run number per request; named independent streams in the finite world (B15) | `ecora-sim.cc` |

## Claims and the fidelity they need

The claims ECoRA intends to make, and what must be credible before each is stated:

| Claim | Must be credible | Current gap |
| --- | --- | --- |
| A controller keeps SCADA within its deadline under a condition | Queues, scheduler, PHY error and retransmission behaviour, traffic, control latency, tail metrics | Fading omitted; control latency not yet charged (B25) |
| Throttling AMI relieves contention | Egress and RLC queueing, per-class accounting, offered versus delivered load | None beyond the single-site topology (B64) |
| Path selection recovers a degraded or silent leg | Leg degradation mechanism, probe evidence and its lag, actuation delay | Actuation not yet implemented (B23); interference out of scope |
| A method outperforms a baseline | All of the above, plus paired replications, uncertainty and the frozen study | Replication counts and intervals are B40 obligations |
| A gap is attributable to information, not method | Observation permissions, privileged-reference separation (B38) | None beyond the above |

## Assumptions that could reverse a conclusion

Candidates for the sensitivity study in B48, each named because an ECoRA conclusion plausibly depends on it:

- **No fading.** Deterministic channels make deadline misses all-or-nothing; fading would spread them into
  tails and could make arbitration windows wider or narrower.
- **Single cell, no interference.** Degradation by load and loss is one route to a slow-but-alive leg; an
  interference-limited cell may degrade with a different time profile.
- **RLC buffer size.** The buffer bounds queueing delay on LTE and therefore which deadlines can be met.
- **AMI demand and period.** Degradation appeared only with demand near the cell-edge share (ADR-30).
- **Probe schedule.** Probe period, timeout and validity set how quickly diagnosis can see a change.
- **Egress capacity** around the contended band measured in B21.

The study reports the regions where a conclusion weakens, reverses or becomes indistinguishable, not only the
nominal point.

## Not adopted, and why

Considered and excluded from v1, so their absence is a decision rather than an oversight:

| Element | Reason |
| --- | --- |
| Guarded, wrap-around and open-stochastic world modes | One cell and a handful of sites; no edge-effect claim is made. Revisit with multi-site or multi-cell work (B64) |
| MDP/POMDP and learning-policy templates | ECoRA's methods are expert systems, planning and eco-agents; nothing is trained |
| Energy, security and cyber-physical co-simulation | No claim depends on them; each is `out_of_scope` above |
| MIMO, beamforming and antenna patterns | The LTE leg uses the ns-3 defaults and no claim depends on antenna behaviour |
| A worlds/conditions/policies split of `scenarios/` | A scenario is the world and a study is what the system knows; both are hashed as frozen artifacts |

## Acceptance properties

Planned, and enforced once B66 lands:

- A scenario without an abstraction declaration is refused when it is read.
- Every `abstracted`, `assumed_negligible` and `out_of_scope` entry carries a rationale.
- A report names the `out_of_scope` entries of every scenario that contributed to a claim.
- A declaration that contradicts what the simulator reports it built is refused, as build ids already are.
