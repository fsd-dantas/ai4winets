# ECoRA simulation declaration

**Status: registry declared in documentation for the ns-3 world as implemented at build 3.48. The
machine-readable per-scenario registry and its enforcement are planned (B66, B67).** [Index](README.md)

This is ECoRA's declaration against the repository's [simulation abstraction
framework](../../research/simulation/README.md): which mechanisms its worlds include, abstract, assume
negligible or leave out of scope, which claims those choices support, and where ECoRA stands on each item of the
[simulation checklist](../../research/simulation/checklist.md).

## Two worlds, two kinds of evidence

ECoRA runs every scenario in two worlds. The **finite reference model** is a small, deterministic resource model
built for exact references, replay and continuation; it is explicitly not a network result. The **ns-3 world**
is the network substrate, behind the [simulator adapter](../../system/simulator-adapter.md).

Agreement between the two is verification: both implement the same declared conditions, and a disagreement
exposes a defect in one of them. It is not validation: neither world is compared with a real network, and every
scenario is synthetic. The validity domain of any ECoRA result is the declared model, never a deployment.

## Abstraction registry of the ns-3 world

Read from `software/simulator/src/ecora-sim/lte-leg.h`, `ecora-sim.cc` and the attribute dump in
`data/simulator/ns3-model-manifest.json`. Where a value is an ns-3 default, it is marked so.

| Class | Status | Representation | Source |
| --- | --- | --- | --- |
| System boundary | `included` | Site gateways, one LTE leg, one abstract alternative leg, one shared egress, one central application | Scenario topology |
| Spatial world | `abstracted` | World mode `finite_closed`: one eNB and its UEs at declared positions; nothing exists outside the cell, and no external interference is represented | Scenario `radio` block |
| Mobility | `out_of_scope` | `ConstantPositionMobilityModel` for every node. Rules out handover and mobility claims | `lte-leg.h` |
| Large-scale path loss | `included` | `FriisSpectrumPropagationLossModel` | `lte-leg.h` |
| Link impairment | `abstracted` | Extra loss in dB per site through `MatrixPropagationLossModel`, 0 dB until a disturbance | ADR-29 |
| Shadowing and small-scale fading | `assumed_negligible` | No fading model (ns-3 default `FadingModel` is empty). Not yet justified for tail-latency claims | Manifest |
| Interference | `out_of_scope` | Single cell, so no inter-cell interference; degradation comes from load and loss instead. Rules out claims about interference-limited cells | `lte-leg.h` |
| Cell load | `abstracted` | `cell_load`: up to 35 competing UEs saturating the uplink at the site's position | ADR-30 |
| PHY and link adaptation | `included` | ns-3 LTE PHY with data and control error models enabled; CQI from PDSCH (defaults) | Manifest |
| MAC scheduling | `included` | `PfFfMacScheduler` | `lte-leg.h` |
| Radio control plane | `abstracted` | Ideal RRC (ns-3 default `UseIdealRrc`) | Manifest |
| Queues | `included` | RLC UM transmission buffer sized by the scenario; DropTail on point-to-point legs | `lte-leg.h`, `ecora-sim.cc` |
| Alternative leg | `abstracted` | Point-to-point with declared rate, delay, queue limit and rate error model; no second RAT is claimed (B02) | Scenario, [v1 scope](v1-scope.md) |
| Transport | `included` | UDP for every flow; reliability is the application's transaction, not the transport's | `ecora-sim.cc` |
| Traffic | `included` | SCADA request/response with a round-trip deadline; periodic AMI with permissible deferral | Scenario `flows` |
| Disturbances | `included` | Scheduled, declared per site and leg; no stochastic failure process | Scenario `disturbances` |
| Decision and control | `included` | Expert systems, blackboard, STRIPS/GPS/A* planning and eco-agents over granted signals; actions through the action contract, with receipts from actuator readback | [Decision methods](decision-methods.md), [action contract](../../system/action-contract.md) |
| Observability | `included` | Only granted signals; the LTE site queue is `derived`; the delivery summary `scada_response` is delayed by 10 ms; truth is privileged and logged | [Telemetry contract](../../system/telemetry-contract.md) |
| Control timing | `abstracted` | Decisions at declared epochs; explicit control-latency accounting is B25 | [Control loop](../../system/control-loop.md) |
| Compute and reasoning delay | `assumed_negligible` | Reasoning effort is counted (passes, plan steps, expansions) but not charged as simulated time | B32 |
| Energy | `out_of_scope` | No energy claim is made | — |
| Security and adversaries | `out_of_scope` | No attack or adversarial-observation claim is made | — |
| Cyber-physical coupling | `out_of_scope` | SCADA and AMI are workloads; no power-system state is modelled | — |
| Randomness | `included` | ns-3 seed fixed, run number per request; named independent streams in the finite world (B15) | `ecora-sim.cc` |

## Claims and the fidelity they need

| Claim | Must be credible | Current gap |
| --- | --- | --- |
| A controller keeps SCADA within its deadline under a condition | Queues, scheduler, PHY error and retransmission, traffic, control latency, tail metrics | Fading omitted; control latency not yet charged (B25) |
| Throttling AMI relieves contention | Egress and RLC queueing, per-class accounting, offered versus delivered load | Single-site topology (B64) |
| Path selection recovers a degraded or silent leg | Leg degradation mechanism, probe evidence and its lag, actuation delay | Actuation delay not yet charged (B25); interference out of scope |
| A method outperforms a baseline | All of the above, plus paired replications, uncertainty and the frozen study | Replication counts and intervals are B40 obligations |
| A gap is attributable to information, not method | Observation permissions, privileged-reference separation (B38) | None beyond the above |

## Assumptions that could reverse a conclusion

Candidates for the sensitivity study in B48, each named because an ECoRA conclusion plausibly depends on it:

- **No fading.** Deterministic channels make deadline misses all-or-nothing; fading would spread them into tails
  and could widen or narrow arbitration windows.
- **Single cell, no interference.** Load and loss are one route to a slow-but-alive leg; an interference-limited
  cell may degrade with a different time profile.
- **RLC buffer size.** It bounds queueing delay on LTE and therefore which deadlines can be met.
- **AMI demand and period.** Degradation appeared only with demand near the cell-edge share (ADR-30).
- **Probe schedule.** Period, timeout and validity set how quickly diagnosis can see a change.
- **Egress capacity** around the contended band measured in B21.

## Checklist status

Against the [simulation checklist](../../research/simulation/checklist.md).

| ID | Status | Evidence or plan |
| --- | --- | --- |
| G1.1 | in place | `ecora.scenario` refuses undeclared sites, legs and paths; `tests/test_scenario.py` |
| G1.2 | in place | Canonical JSON, hash bound into run provenance ([scenarios](../../scenarios/README.md)) |
| G1.3 | partial | Scenario and study are each hashed and bound into provenance; storing one resolved composition per result is to be confirmed with B66 |
| G1.4 | partial | The registry above; per-scenario machine-readable registry is B66 |
| G1.5 | planned | B67: the simulator already reports its loss chain, scheduler and RLC mode; the check against the declaration is not built |
| G1.6 | partial | `finite_closed` declared above, not yet in scenario files (B66) |
| G1.7 | partial | [Parameter register](experiments.md#parameter-register) |
| G1.8 | in place for the LTE rate table | `data/simulator/lte-rate-calibration.json`, ADR-29, ADR-30 |
| G1.9 | partial | Pilots such as `bottleneck-pilot` (S5 was found to be overload this way); reviewed by hand |
| G1.10 | partial | Reviewed by hand against S0 |
| G1.11 | partial | Reachability tests such as the arbitration window in `tests/test_study.py` |
| G1.12 | partial | Units and timestamps enforced (B11); per-class queue accounting in both worlds (B21); limiting cases by hand |
| G1.13 | partial | Every scenario is synthetic; sanitisation checklist applied by hand |
| G2.1 | in place | [Study freeze contract](methodology.md#study-freeze-contract) |
| G2.2 | in place | `studies/*.json`, `tests/test_study.py` |
| G2.3 | in place | `software/simulator/ns3-build.json`, build id on every response, ADR-28 |
| G2.4 | partial | B15 streams; ns-3 run number per request; pairing policy is B40 |
| G2.5 | planned | B40, B41 |
| G2.6 | partial | [Metrics and denominators](experiments.md#metrics-and-denominators), B36 |
| G2.7 | planned | B40 |
| G2.8 | in place | Every arm binds the same telemetry and action contracts ([stage arms](stage-arms.md)) |
| G2.9 | partial | Holdout protection is stated in [methodology](methodology.md#outer-loop-responsibilities); enforcement is B40 |
| G2.10 | planned | B68, then B48 |
| G2.11 | planned | B43 |
| G3.1 | in place | [Claims and comparisons](methodology.md#claims-and-comparisons) |
| G3.2 | partial | Capability levels in `CONTRIBUTING.md`; checked by hand |
| G3.3 | partial | Finite-model results are labelled as such by hand |
| G3.4 | planned | B66 |
| G3.5 | planned | B40, B49 |
| G3.6 | planned | B48, B68 |
| G3.7 | in place | B37, B38 |
| G3.8 | partial | B37; full accounting is B43 |
| G3.9 | partial | Replay and continuation (B16, B17); clean-environment reproduction is B53 |
