# DPOP channel assignment: simulation declaration

**Status: registry declared in documentation for the solver as implemented (DFS, UTIL and VALUE).**
[Study design](README.md)

This is the study's declaration against the repository's [simulation abstraction
framework](../../research/simulation/README.md). The study simulates a distributed algorithm, not a radio
network: agents exchange messages over a logical transport to solve a constraint problem derived from a map. Most
radio and network classes are therefore out of scope, and each is declared so that the claims they rule out are
explicit.

## What the model is

A planar map is read as a surrogate interference graph: one region, one AP, one agent; regions sharing a
boundary segment must take different channels; optional synthetic channel-busyness scores act as unary costs.
DPOP solves the resulting DCOP exactly. The [study design](README.md#one-problem-read-two-ways) states what the
surrogate keeps and what it drops.

## Abstraction registry

| Class | Status | Representation | Source |
| --- | --- | --- | --- |
| System boundary | `included` | Regions, their APs and agents, the constraint graph, the message protocol | [System model](README.md#system-model) |
| Spatial world | `abstracted` | World mode `trace_bounded`: the map defines the world. Synthetic grids, and sourced municipal boundaries for the Curitiba maps; nothing outside the map exists | [Instances](README.md#demonstration-and-validation-instances), `data/geography/` |
| Geometry | `abstracted` | Adjacency from shared boundary segments of positive length; corner contact creates no edge | [System model](README.md#system-model) |
| RF, antenna and propagation | `out_of_scope` | No received power, path loss or fading. Rules out coverage, SINR and link-quality claims | — |
| Interference | `abstracted` | A binary conflict between neighbouring regions, forbidden when both take one channel. Omits SINR dependence, partial overlap and nonplanar conflict structure | [One problem, read two ways](README.md#one-problem-read-two-ways) |
| Channel preference | `abstracted` | Synthetic integer scores 0 to 100 per AP and channel, not measured busyness | [Declared values](README.md#declared-values-nominal-uncalibrated) |
| PHY and MAC | `out_of_scope` | No transmission is modelled. Rules out throughput, airtime and loss claims | — |
| Coordination transport | `abstracted` | Reliable, lossless, ordered logical transport on a separate control path; message counts are not airtime | [System model](README.md#system-model) |
| Traffic and applications | `out_of_scope` | No user traffic | — |
| Mobility | `abstracted` | A mobile cell as a declared sequence of static snapshots, each re-solved; nothing moves during a solve | [Mobile cells](README.md#mobile-cells-re-planning-over-snapshots) |
| Decision and control | `included` | DPOP: distributed DFS pseudo-tree, UTIL propagation, VALUE reconstruction; hard constraints as explicit forbidden values | [Architecture](architecture.md) |
| Observability | `included` | Each agent sees only its own variable, owned factors and received messages; no agent reads global state | [Architecture](architecture.md) |
| Compute | `abstracted` | Table entries and messages per phase; timing and process memory are not measured, since agents share one process | [Metrics](README.md#metrics) |
| Energy, security, cyber-physical coupling | `out_of_scope` | No claim depends on them | — |
| Randomness | `included` | The solver is deterministic under its declared tie rule and orders; seeds only generate instances and independent preference scores | [Declared values](README.md#declared-values-nominal-uncalibrated) |

## Claims and the fidelity they need

The study's claims are about the algorithm on the declared instances, so the fidelity they need is in the
problem model, the protocol and the independent evaluation, not in radio behaviour.

| Claim | Must be credible | Current gap |
| --- | --- | --- |
| C1 Every admitted map is coloured with zero conflicts | Map validation, constraint model, independent evaluator | The independent evaluator is CA-11 |
| C2 The cost equals the exact optimum; infeasible instances are reported | Exact enumeration on small instances; K5 | None for the tested instance families |
| C3 Independent choice can violate the constraints coordination satisfies | The same instances and costs for both | The baseline is CA-14 |
| C4 Table size follows the separator | Separator and table accounting per phase | Frozen measurement is CA-37 |
| C5 A stability cost reduces reassignment when a mobile cell moves | The snapshot sequence and its re-solve rule | Mobile-cell sequences are CA-34 to CA-36 |

The study already states what it does not claim: throughput, loss, SINR, airtime or service gains, behaviour
under changing costs or lost messages, nonplanar interference and real radio data.

## Checklist status

Against the [simulation checklist](../../research/simulation/checklist.md). Items about stochastic replication
and preregistered comparisons apply only to the deferred comparative study, which declares its own protocol.

| ID | Status | Evidence or plan |
| --- | --- | --- |
| G1.1 | in place | Map and instance validation reject duplicate IDs, invalid geometry, disconnected and nonplanar graphs; `tests/test_dcop_domain.py`, `tests/test_dcop_geography.py` |
| G1.2 | partial | Source data are hashed for the Curitiba maps; run records are not yet bound to an instance hash |
| G1.3 | partial | Instances are fully declared in code and data; a stored resolved record per run comes with the `solve` CLI (CA-12) |
| G1.4 | in place | This registry |
| G1.5 | not applicable | No external simulator; the registry describes the solver directly |
| G1.6 | in place | `trace_bounded`, declared above |
| G1.7 | in place | [Declared values](README.md#declared-values-nominal-uncalibrated), marked nominal |
| G1.8 | not applicable | No calibrated parameter |
| G1.9 | partial | Integration checks show each instance's outcome, including the 29-region budget stop |
| G1.10 | not applicable | Instances are not condition variants of a baseline |
| G1.11 | partial | Infeasibility is reached (K5) and generated instances now include infeasible cases |
| G1.12 | partial | Every factor counted once; root cost matches enumeration under every root; order independence of the full solve is CA-15 |
| G1.13 | in place | Synthetic instances; municipal boundaries with recorded source, attribution and access terms |
| G2.1 to G2.11 | not applicable to the core study | The core runs are deterministic, one run per map, mode and root; the deferred comparative study must meet these items |
| G3.1 | partial | Claims name their instance and root; run identifiers arrive with CA-12 |
| G3.2 | in place | Capability levels stated throughout the study documents |
| G3.3 | in place | Claims are scoped to declared instances; the not-claimed list is explicit |
| G3.4 | in place | This registry |
| G3.5 | not applicable | No comparative performance claim; C3 is illustrative |
| G3.6 | partial | The budget limit on the 29-region map is reported; the resource description is CA-37 |
| G3.7 | not applicable | No privileged-information comparison |
| G3.8 | partial | Budget stops are reported, never as infeasibility |
| G3.9 | partial | Deterministic from committed code and data; clean-checkout runbook is CA-38 |
