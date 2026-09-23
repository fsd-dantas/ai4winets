# Simulation abstraction framework

**Status: normative research methodology for every simulation in this repository. Conformance is declared per
study track; a track that does not yet meet an item says so in its declaration.**

This framework defines which model classes a simulation study must consider, how each modelling choice is
declared, and how those choices connect research claims, configurations, simulator realisations and evidence.
It applies to every track in this repository that produces evidence by simulation, whatever its subject:
network control, distributed algorithms, radio planning or anything added later.

The objective is not maximal fidelity at every layer. It is **fitness for purpose**: each abstraction keeps the
mechanisms capable of changing the conclusion for the stated research question.

## Documents

| Document | Scope |
| --- | --- |
| This page | Governing rule, abstraction statuses, required classes, claim-to-fidelity mapping, declaration and conformance |
| [Spatial world model](spatial-world-model.md) | World extent, boundaries, populations, guard regions, edge effects and KPI eligibility |
| [Wireless RF and channel model](wireless-rf-channel-model.md) | Link budget, propagation, antennas, fading, noise, interference and PHY abstraction |
| [Network and service model](network-service-model.md) | PHY/MAC, topology, queues, transport, traffic, event correlation, mobility and KPIs |
| [Control and resilience model](control-and-resilience-model.md) | Decision formalism, observability, actions, learning, safety, compute, energy, security and cyber-physical coupling |
| [Simulation assurance](simulation-assurance.md) | Verification, validation, calibration, uncertainty, sensitivity, statistics and reproducibility |
| [Checklist](checklist.md) | The gates a configuration, a study and a claim pass, with item identifiers declarations refer to |
| [Abstraction catalog](abstraction-catalog.md) | A quick reference of model families for authors and reviewers |

## Governing rule

A simulation result is valid only within the conditions its model represents. Every study therefore makes
explicit:

- the research hypothesis and the decision or use case it serves;
- the system boundary and the mechanisms left out;
- the abstraction chosen at each relevant layer;
- the inputs, standards, theory or measurements behind each parameter;
- the metrics, populations and time windows over which conclusions are drawn;
- the verification, validation, uncertainty, sensitivity and reproducibility evidence.

**The minimum acceptable fidelity is the lowest fidelity at which a justified perturbation of the omitted detail
cannot plausibly reverse the conclusion.** An abstraction is judged against a claim, not in general: the same
model can be adequate for one conclusion and inadequate for another in the same study.

## Traceability chain

Every reported result is traceable through:

```text
Research question / hypothesis
  -> system boundary and abstraction choices
  -> configuration (world, conditions, treatments)
  -> simulator or model realisation
  -> seed plan and execution environment
  -> raw observations and KPI derivation
  -> statistical analysis and conclusion
```

A link that cannot be followed is a gap to be reported, not an omission to be inferred around.

## Abstraction statuses

Each abstraction class relevant to a claim takes exactly one status:

| Status | Meaning | Required with it |
| --- | --- | --- |
| `included` | Represented explicitly and parameterised | Parameters and their source |
| `abstracted` | Represented by an aggregate, statistical, tabulated, surrogate or reduced-order model | The representation and its validity range |
| `assumed_negligible` | Deliberately omitted because it cannot move the claim | A written justification, with evidence when the claim depends on it |
| `out_of_scope` | Outside the research boundary | A rationale, and the claims it rules out |

`out_of_scope` is not a softer `assumed_negligible`: it names what the result cannot be used for. These
statuses describe modelling choices; they are distinct from the repository's capability levels (implemented,
simulated, planned, unsupported), which describe whether a capability exists at all.

## Required abstraction classes

A study declares each class below. A class irrelevant to every claim is declared `out_of_scope` with a one-line
rationale; it is not silently dropped.

| Class | Core question |
| --- | --- |
| System purpose and boundary | What claim is tested, and what is inside the modelled system? |
| Spatial world and population | Is the world finite, guarded, periodic, trace-bounded or open? See [spatial world](spatial-world-model.md) |
| Geometry and environment | Where are nodes, obstacles, terrain, clutter and reflectors? |
| RF, antenna and channel | How are received signal, loss, fading, interference and receiver limits represented? See [RF and channel](wireless-rf-channel-model.md) |
| PHY and MAC | How do waveform, error rate, scheduling, retransmission and access control determine delivery? |
| Network and transport | How do routing, queues, backhaul, protocols and congestion determine end-to-end service? See [network and service](network-service-model.md) |
| Traffic and applications | What flows, priorities, deadlines, bursts and correlated events occur? |
| Mobility and temporal dynamics | How do positions, channel states, loads and failures evolve? |
| Decision and control | What are the state, observation, action, delay, objective, constraints and information limits? See [control and resilience](control-and-resilience-model.md) |
| Compute and orchestration | What processing, inference, placement and control-plane delays occur? |
| Energy and sustainability | Which radio, compute, sleep, battery and harvesting dynamics matter? |
| Security and resilience | Which attacks, correlated failures, degradation and recovery processes matter? |
| Cyber-physical coupling | How do communication, control and physical processes influence each other? |
| Experiment credibility | How are verification, validation, uncertainty, statistics and reproducibility handled? See [assurance](simulation-assurance.md) |

## Claim-to-fidelity mapping

Before a claim of a given kind is made, the listed abstractions must be credible for it: `included`, or
`abstracted` with a stated validity range covering the claim, or `assumed_negligible` with evidence.

| Primary claim | Minimum abstractions that must be credible |
| --- | --- |
| Coverage, link budget, outage, SINR | Geometry, antenna patterns, propagation, shadowing and fading, interference, receiver noise and sensitivity |
| Capacity, goodput, error rate, spectral efficiency | RF and channel, PHY-to-error mapping, MCS, HARQ/ARQ, scheduler, queueing, traffic load |
| Tail latency or deadline-bound service | PHY/MAC retransmission, queues, traffic burstiness, transport, processing and control delay, deadline metrics |
| Handover, multi-RAT resilience, association | Mobility, measurements, radio and link states, control-plane delay, admission and resource constraints, failure processes |
| Backhaul, slicing, edge computing, orchestration | Topology, link capacity, queueing, routing and control plane, compute placement, inference and orchestration latency |
| Utility or industrial communications | Application classes, priorities, correlated physical events, resilience, power and communication dependencies, recovery |
| Decision-method benefit (rule-based, planning, optimisation or learned) | Decision formalism, partial observation, action feasibility, telemetry and actuation delay, baselines with information parity, separation of tuning and evaluation, generalisation |
| Distributed-algorithm correctness or cost | Problem instance model, communication model (loss, order, delay), independent evaluation, exact references where tractable |
| Deployment or digital-twin claim | Map, trace or site data, calibration, measurement comparison, uncertainty bounds, explicit validity domain |

## Configuration composition

A resolved experiment is the composition of:

$$
\text{Experiment} = \text{World} + \text{Topology/Environment} + \text{RF} + \text{Network/Traffic}
+ \text{Conditions/Faults} + \text{Decision policy} + \text{Seed plan}.
$$

How a track splits these across files is its own choice. What is fixed is that the resolved composition is
materialised, hashed and stored with every result, so a result never depends on an undocumented default.

## Declaration

Each study track keeps one **simulation declaration** in its own documentation, and each resolved experiment
records, in machine-readable form, at least:

```json
{
  "experiment_metadata": {
    "research_claim": "string",
    "primary_hypothesis": "string",
    "system_boundary": "string",
    "target_deployment_or_population": "string",
    "primary_metrics": ["string"],
    "abstraction_registry": "path-or-inline-object",
    "validation_plan": "path-or-inline-object",
    "seed_plan": "path-or-inline-object",
    "software_revision": "commit-or-version",
    "simulator_revision": "commit-or-version"
  }
}
```

An abstraction registry entry takes this shape:

```json
{
  "abstraction_registry": {
    "spatial_world": {"status": "included", "reference": "research/simulation/spatial-world-model.md"},
    "terrain_buildings": {
      "status": "abstracted",
      "representation": "scenario-specific path-loss and shadowing model",
      "rationale": "The study evaluates control behaviour rather than site-specific ray paths."
    },
    "adjacent_channel_interference": {
      "status": "assumed_negligible",
      "rationale": "Single co-channel carrier; justified for the declared bandwidth plan."
    },
    "physical_process_dynamics": {
      "status": "out_of_scope",
      "rationale": "The experiment studies communication recovery after an exogenous event."
    }
  }
}
```

The field names are the framework's; a track may map them into its own schema, provided the mapping is stated.
Values in examples throughout this framework are illustrative, not declared parameters.

## Current declarations

| Track | Declaration | Conformance |
| --- | --- | --- |
| ECoRA | [Simulation declaration](../../docs/ECoRA/simulation-declaration.md) | Registry declared in documentation; machine-readable per-scenario registry planned |
| DPOP channel assignment | [Simulation declaration](../../docs/dcop-channel-assignment/simulation-declaration.md) | Registry declared in documentation |

## Conformance

A study is conformant only if it declares every class relevant to its primary claims, gives a rationale for
every `abstracted`, `assumed_negligible` or `out_of_scope` class that could materially influence those claims,
and states its status against each [checklist](checklist.md) item. Non-conformance is permitted while it is
declared; an undeclared gap is a defect.
