<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/fsd-dantas/ai4winets/main/docs/assets/img/banner-dark.jpg">
    <img src="https://raw.githubusercontent.com/fsd-dantas/ai4winets/main/docs/assets/img/banner-light.jpg" alt="Applied AI for Wireless Communication — assurance for critical wireless networks. An isometric lattice with energised traces wiring a search tree, a network router, a transmission tower, a gauge, a feedback controller and a network mesh to one AI processor." width="100%">
  </picture>
</p>

# Applied AI for Wireless Communication

> A reproducible research portfolio for studying assurance, autonomy, and cyber-physical resilience in critical wireless networks.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Research status](https://img.shields.io/badge/research%20status-exploratory-informational.svg)](#status-and-limitations)

## Purpose

This repository is an evolving **research knowledge base**, **reproducible experimentation environment**, and **scholarly portfolio** for artificial intelligence applied to wireless communication systems.

Its current emphasis is the study of critical wireless networks: systems in which communication performance, availability, security, and recovery behavior affect safety, continuity of service, or cyber-physical operation. Representative contexts include smart-grid communications, industrial operational technology, private cellular systems, resilient backhaul, and other mission- or time-critical infrastructures.

The repository documents research evolution rather than a finalized dissertation proposal. The research directions recorded here are exploratory: they do not constitute an institutional commitment, an approved thesis topic, or a claim that any implemented architecture is the final research solution.

## Research Focus

The portfolio investigates how wireless systems can preserve critical services during operational faults, environmental degradation, congestion, infrastructure outages, and adversarial events. The central concern is **service assurance** rather than average network performance alone.

For a critical service $i$, useful assurance properties include:

$$\Pr\left(D_i \leq D_i^{\max}\right) \geq 1 - \epsilon_i,$$

where $D_i$ is end-to-end delay, $D_i^{\max}$ is the service deadline, and $\epsilon_i$ is the allowable probability of deadline violation. Complementary properties include availability, jitter, packet delivery, time to detect, time to recover, energy cost, security integrity, and the probability of unsafe control action.

This is the standard statistical delay bound and is not a formulation original to this work. It restates the
normative definition of reliability — the proportion of packets delivered within the time constraint required
by the service (3GPP TS 22.261) — as a probability with an explicit violation budget, in the
delay-violation-probability form used for wireless link modelling (Wu and Negi, 2003). Preferring tail and
violation-oriented measures over averages follows the same argument (Bennis, Debbah and Poor, 2018). The
deadline $D_i^{\max}$ is domain-specific and is not supplied by the formula: for substation communications it
derives from the IEC 61850-5 transfer-time classes. Full entries and provenance are in
[`literature/`](literature/).

The repository currently explores three interconnected directions:

| Direction | Guiding question | Current repository connection |
|---|---|---|
| **Assurance-constrained multi-RAT intelligence** | How can heterogeneous wireless paths and radio access technologies be selected, coordinated, duplicated, or recovered to maintain critical-service guarantees? | Dual-homed and multi-RAT network scenarios, failover logic, traffic prioritization, and simulation experiments |
| **Digital-twin-assisted self-healing** | How can a calibrated network representation use telemetry to predict service degradation, evaluate remedial actions, and safely support closed-loop recovery? | NS-3 scenarios, telemetry exports, causal replay, versioned results, ontology, and diagnosis contracts |
| **Cyber-resilient deterministic communications** | How can a critical wireless network preserve availability, timing, and integrity during cyber-physical failures and adversarial activity? | Fault diagnosis, provenance-aware telemetry, recovery workflows, service differentiation, and planned threat modelling |

These directions share a common experimental substrate — the ECoRA framework described below. They are
intentionally maintained as alternatives and possible combinations until literature evidence, prototype
results, feasibility constraints, and supervisory guidance justify thematic narrowing.

## Repository map

```text
.
├── research/                  # Research framing, methodology, ontology, questions, and roadmap
├── literature/                # Literature reviews, critical analyses, evidence synthesis
├── experiments/               # ECoRA studies, ablation arms, and their run artefacts
├── scenarios/                 # Declared scenario definitions, versioned and frozen per study
├── system/                    # Executable contracts, once adopted from the ECoRA proposal
├── software/                  # Software packages, modules, integration code, and setup material
├── docs/                      # Documentation, including the ECoRA architectural proposal
│   ├── ECoRA/                 # Architecture, ontology, contracts, methodology, experiments and ablation
│   └── assets/img/            # Repository-level figures, banner, and social preview
├── data/                      # Schemas, synthetic inputs, and provenance material when applicable
├── CITATION.cff               # Citation metadata
├── CHANGELOG.md               # Versioned change history
├── CONTRIBUTING.md            # Contribution conventions
├── CODE_OF_CONDUCT.md         # Participation expectations
└── LICENSE                    # Repository licence
```

Packaging (`pyproject.toml`) and task automation (`Makefile`) arrive with the first software module, so that
the package name follows the code rather than preceding it. Most documents listed below are planned rather than
written; each entry states which.

### Core documentation

The ECoRA package is the current centre of gravity. Every document in it describes a **planned** architecture:
it introduces no runtime implementation and no experimental result.

- [**ECoRA index**](docs/ECoRA/) — start here. Scope, evidence boundary and acceptance criteria.
- [Architecture](docs/ECoRA/architecture.md) — bounded contexts, context map, aggregates, ports and adapters,
  and the relationship to established reference models.
- [Domain and ontology](docs/ECoRA/ontology.md) and [vocabulary](docs/ECoRA/ontology.ttl) — ubiquitous
  language and epistemic distinctions, with a machine-readable RDF/OWL design artefact.
- [Contracts](docs/ECoRA/contracts.md) — scenario, telemetry, diagnosis, planning, resolution, execution and
  assurance interfaces.
- [Decision methods](docs/ECoRA/decision-methods.md) — rule experts, STRIPS, GPS, A\* and eco-problem solving.
- [Methodology](docs/ECoRA/methodology.md) — the two loops, the study freeze contract, and the rules for
  cross-version comparison.
- [Experiments and ablation](docs/ECoRA/experiments.md) — scenario family, hypotheses, ablation matrix,
  metrics and validity criteria.
- [Evidence and decisions](docs/ECoRA/evidence-and-decisions.md) — capability boundaries, architectural
  decisions and implementation sequence.

Documents below are not yet written. They are listed so the intended structure is visible; each becomes a link
when it lands.

- [System contracts](system/) — stubs, pending adoption of the ECoRA contracts into executable form.
- Research problem statement — problem framing and scope. *(planned)*
- Research questions — questions addressed by current artefacts. *(planned)*
- Research roadmap — planned work, known gaps, and conformance tasks. *(planned)*
- Capability matrix — declared versus executable sensing, reasoning, and actuation capabilities. *(planned)*
- Getting started — entry points for readers and contributors. *(planned)*

## Experimental philosophy

Experiments in this repository are treated as **evidence-bearing research artefacts**. An experiment should make clear:

1. Its objective, research question, and hypothesis.
2. The system model, scenario, assumptions, and threat/fault conditions.
3. Software versions, configuration, inputs, and execution procedure.
4. Metrics, results, limitations, and reproducibility status.
5. The scope of the claim supported by the observed evidence.

The repository distinguishes explicitly among:

- **Implemented capability** — behaviour exercised by executable code.
- **Simulated capability** — behaviour represented in a model and evaluated under stated assumptions.
- **Planned capability** — a documented direction that is not yet implemented or validated.
- **Unsupported capability** — a concept that the current simulator, telemetry model, or controller cannot presently represent.

No result should be generalized beyond its observed model, scenario set, telemetry coverage, action space, software version, and reproducibility evidence.

## ECoRA — the unified framework

**Status: planned. No runtime implementation and no measured result exists yet.**

**ECoRA — Expert Coordination, Resolution, and Assurance** is the closed-loop framework this repository
studies. Symbolic diagnosis, automated planning, expert coordination, self-organising resolution and simulated
measurement are *methods* and *treatments* within one instrumented pipeline, not separate systems. Unifying
them is what makes them comparable: every method is exercised against the same scenarios, the same action
space and the same assurance metrics.

ECoRA separates two loops that run on different clocks and under different authority:

- **Inner operational loop, within a run:** telemetry → diagnosis → plan → resolution → action → result →
  subsequent telemetry. Bounded by observation availability, deadlines, safety invariants and actuator authority.
- **Outer experimental loop, across studies:** assurance reports → research review → candidate scenario set →
  freeze a new study. This is research methodology, **not** an automated runtime feedback path. The runtime
  contains no report-to-scenario mutation command.

Keeping these apart is what makes measurement possible: a study freezes one scenario-set version before
comparative measurement, so a controller change can never be confounded with a benchmark change.

### What the framework contains

| Element | Role in ECoRA |
| --- | --- |
| Decision methods | Rule-based diagnosis with certainty factors, STRIPS and GPS planning, A\* search |
| Coordination | How multiple knowledge sources contribute to a shared solution state |
| Resolution | How competing proposals are reduced to a decision, by central arbitration or local self-organisation |
| Assurance | Evaluation of service requirements against evidence, scoped to a frozen study |
| The plant | ns-3 behind an anti-corruption layer, supplying telemetry and applying actions |

Coordination and Resolution are **concerns applied across the loop**, not single stages — candidates compete at
diagnosis, at planning and at execution. Treating them as cross-cutting is what turns *expert* and *eco* modes
from two incomparable architectures into two settings of one ablatable factor.

### Stages are interfaces, so ablation is a configuration

Every stage binds a provider through configuration rather than code, in three arms:

| Arm | What it is | What it measures |
| --- | --- | --- |
| **Null** | A degenerate policy — first match, first feasible action, no planning | Whether the stage contributes at all |
| **Proposed** | The method under study | How much it contributes |
| **Oracle** | Ground truth from the simulator, with its privileges explicitly labelled | How much headroom remains |

The Oracle arm carries the load that matters most here. If an oracle diagnoser barely beats the proposed one,
the bottleneck is not the method — it is the telemetry. That converts a weak result into a measured statement
about **observability sufficiency**, which is exactly the claim the telemetry contract exists to support.
Because every stage invocation logs its typed inputs and outputs, a stage can also be replayed in isolation.

No architectural novelty is claimed: the loop instantiates MAPE-K and related closed-loop reference models, and
the decision methods are classical formulations. See
[Relationship to established reference models](docs/ECoRA/architecture.md#relationship-to-established-reference-models).
The substance is the instantiation discipline — explicit contracts, a frozen benchmark, and ablation evidence
for every declared factor.

Every method in the framework is a **baseline**, not a presumed solution. Future controllers,
including optimisation-based, learning-based, digital-twin-assisted and security-aware mechanisms, are
evaluated as additional treatments against the same frozen scenario set and the same assurance metrics.

The full architectural proposal is in **[`docs/ECoRA/`](docs/ECoRA/)**.

## Candidate research directions

The `research-directions/` area is the primary location for study without premature commitment.

Each candidate direction should contain:

```text
research-directions/<theme>/
├── overview.md                # Motivation, scope, and terminology
├── research-gap.md            # Evidence-supported gap statement
├── candidate-questions.md     # Provisional research questions and hypotheses
├── study-plan.md              # Literature, skills, prototypes, and milestones
├── evidence-log.md            # Traceable findings that update the assessment
└── viability-assessment.md    # Fit, novelty, feasibility, risk, and decision rationale
```

The comparative framework should assess each direction against the same criteria:

- Scientific novelty and gap clarity.
- Relevance to critical wireless and cyber-physical systems.
- Compatibility with available simulation, emulation, and testbed assets.
- Data, telemetry, and observability requirements.
- Action-space and control feasibility.
- Reproducibility and evaluation tractability.
- Expected theoretical, systems, and experimental contributions.
- Risk of over-scoping within a doctoral timeframe.
- Alignment with future laboratory infrastructure and collaborators.

## Learning artefacts and external work

This repository may contain technical artefacts initially produced in structured learning settings when they have been revised into reusable scholarly material. Such artefacts are included to document intellectual development, strengthen reproducibility, and support research-direction assessment.

They are not presented as institutional submissions, graded work, institutional positions, or formally approved research outputs.

Use the following principles:

- Store a literature critique in `literature/` when it is an evidence-synthesis artefact. `literature/` holds
  **references** — engagement with other people's work, always fully cited.
- Publish technical notes, derivations, and study material in the project **wiki** when they primarily record
  the maintainer's **own findings and reasoning**. The wiki carries the reasoning; the repository carries the
  artefacts it produced.
- Store a reproducible implementation or simulation in `experiments/` when its main contribution is experimental evidence.
- Store a theme-comparison or feasibility study in `research-directions/` when it informs research selection.
- Remove institutional identifiers, grades, assessment rubrics, restricted content, private data, and copyrighted instructional material before publication.
- Record provenance, revision status, assumptions, reproducibility information, limitations, and research relevance in the artefact README.

A minimal metadata template is available below:

```md
# Scholarly Learning Artefact: <Title>

## Purpose
This artefact records an independent technical study of <topic> and its
relevance to the exploratory research directions in this repository.

## Research relevance
- Assurance-constrained multi-RAT intelligence:
- Digital-twin-assisted self-healing:
- Cyber-resilient deterministic communications:

## Artefact type
Literature analysis | replication | implementation | simulation exercise |
comparative study | technical note

## Scope and provenance
This material was developed or initiated in a structured learning context and
has been revised for independent scholarly documentation and reproducibility.
It does not represent an institutional position, formal thesis proposal, or
validated research result.

## Reproducibility
- Software and version:
- Data and licence:
- Execution procedure:
- Expected output:
- Limitations:

## Key learning outcomes
- 
- 
- 
```

## Reproducibility and scientific claims

Reproducibility is a first-class requirement. For every implemented experiment, preserve or document:

- Source code and dependency versions.
- Scenario definitions and configuration files.
- Input-data origin, generation method, licence, and transformations.
- Random seeds and the number of replications.
- Execution commands and hardware/operating-system constraints.
- Raw or appropriately versioned result artefacts.
- Metric definitions and analysis scripts.
- Known limitations and unmodelled phenomena.

For comparative studies, use the same network topology, traffic classes, fault or attack scenarios, measurement intervals, and evaluation metrics unless a documented research question requires otherwise.

For critical-service evaluation, prefer tail and violation-oriented measures over means alone:

- Deadline-miss ratio.
- Tail latency and jitter.
- Packet delivery or loss under each service class.
- Service availability.
- Mean time to detect and mean time to recover.
- Recovery effectiveness and unintended side effects.
- Energy or computational overhead.
- Control stability and policy oscillation.
- Security detection quality and unsafe-action rate, when applicable.

## Open data and configurations

The inputs behind a published result are published with it, not only the result. Two things are meant by this,
and they fail differently:

- **Open data** — the datasets a claim rests on: telemetry exports, simulation outputs, measurement traces,
  with their origin, generation method, licence and transformations documented. Data without configurations
  gives a reader numbers they cannot regenerate.
- **Open configurations** — the machine-readable setup that produced those data: scenario definitions,
  topology declarations, fault-injection specifications, parameter blocks, random seeds, build settings and
  version pins. Configurations without data give a reader a recipe with no reference output to check against.

Reproducibility needs both, plus the execution command and the metric definitions. This commitment binds at
commit time rather than at publication time: once configurations are declared open, every configuration file
entering the repository is already a publication decision. The checklist in [CONTRIBUTING.md](CONTRIBUTING.md)
is what keeps that commitment honest.

The provenance chain that links the two halves is `study → scenario → run → dataset`, and it is the structure
against which FAIR compliance and artifact evaluation are assessed.

## Quick start

This repository currently carries its research framing, system contracts and governance. **No executable
software has landed yet**, so there is nothing to install. Clone it and read:

```bash
git clone https://github.com/fsd-dantas/ai4winets.git
cd ai4winets
```

Start with [`docs/ECoRA/`](docs/ECoRA/) for the architectural proposal: what the research system observes,
what it may do, how competing proposals are resolved, and how a service assurance claim is scoped to a frozen
study. The stubs under [`system/`](system/) are placeholders awaiting adoption of those contracts into
executable form.

When software arrives, two environments will apply: the Python package on any supported Python environment,
and the ns-3 multi-RAT experiment on Linux, with Ubuntu or WSL2 as the documented setup path. Each experiment
directory will carry the README stating its exact execution and validation procedure.

Do not interpret a successful installation as validation of an experiment. Reproduce the documented command, compare the stated outputs, and review the experiment’s limitations before relying on its results.

## Contribution principles

Contributions should improve either research evidence, reproducibility, documentation quality, experimental validity, or software reliability. Before opening a change, consult [CONTRIBUTING.md](CONTRIBUTING.md) and the relevant experiment documentation.

Useful contributions include:

- Correcting a claim that is not traceable to code, data, or cited evidence.
- Adding a reproducible baseline under a clearly scoped research question.
- Extending telemetry only when its provenance and limitations are documented.
- Adding fault, attack, or recovery scenarios with explicit assumptions.
- Improving test coverage, configuration validation, and result provenance.
- Contributing literature evidence through a traceable synthesis rather than isolated citations.

Avoid introducing a new controller, metric, or scenario without identifying the research question it addresses and the comparison it enables.

## Status and limitations

This is an active exploratory repository. It contains implemented software, documented models, simulation results, literature material, and planned directions at different levels of maturity.

In particular:

- A simulation result is not equivalent to field validation.
- A controller that succeeds in a limited scenario is not automatically robust under broader operating conditions.
- Unavailable telemetry must not be represented as observed evidence.
- A planned experiment, model, controller, or theme is not a validated contribution.
- The present repository supports research exploration; it does not yet establish an end-to-end validated critical-infrastructure solution.

Readers should use the capability matrix, per-experiment limitations, reproducibility-status declarations, and research roadmap when interpreting any artefact.

## Citation

If you use this repository, please cite the versioned software record described in [CITATION.cff](CITATION.cff).

```text
DANTAS, Fernando Sabino. Applied AI for Wireless Communication:
research knowledge base and research framework for applying artificial
intelligence to wireless communication systems. GitHub repository, 2026.
Available at: https://github.com/fsd-dantas/ai4winets.
```

## Licence

This repository is distributed under the terms of the [MIT License](LICENSE), except where a specific artefact, dataset, dependency, or externally sourced material declares different terms. Ensure that any new contribution is compatible with the applicable licence and attribution obligations.

---

**Research posture:** explore broadly, document precisely, reproduce rigorously, and narrow the research question only when evidence supports the decision.
