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

The repository currently explores three interconnected directions:

| Direction | Guiding question | Current repository connection |
|---|---|---|
| **Assurance-constrained multi-RAT intelligence** | How can heterogeneous wireless paths and radio access technologies be selected, coordinated, duplicated, or recovered to maintain critical-service guarantees? | Dual-homed and multi-RAT network scenarios, failover logic, traffic prioritization, and simulation experiments |
| **Digital-twin-assisted self-healing** | How can a calibrated network representation use telemetry to predict service degradation, evaluate remedial actions, and safely support closed-loop recovery? | NS-3 scenarios, telemetry exports, causal replay, versioned results, ontology, and diagnosis contracts |
| **Cyber-resilient deterministic communications** | How can a critical wireless network preserve availability, timing, and integrity during cyber-physical failures and adversarial activity? | Fault diagnosis, provenance-aware telemetry, recovery workflows, service differentiation, and planned threat modelling |

These directions share a common experimental substrate. They are intentionally maintained as alternatives and possible combinations until literature evidence, prototype results, feasibility constraints, and supervisory guidance justify thematic narrowing.

## Repository map

```text
.
├── research/                  # Research framing, methodology, ontology, questions, and roadmap
├── literature/                # Literature reviews, critical analyses, evidence synthesis
├── experiments/               # Reproducible experiments and shared simulation environments
├── scenarios/                 # Declared scenario definitions shared across experiments
├── system/                    # Architecture, domain model, and telemetry, action and control-loop contracts
├── software/                  # Software packages, modules, integration code, and setup material
├── docs/                      # Architecture, domain model, capability matrix, and experiment catalogue
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

Documents marked *planned* are not yet written. They are listed so that the intended structure is visible; the
entry becomes a link when the document lands.

- Research problem statement — current problem framing and scope. *(planned)*
- Research methodology — methodological principles and evidence strategy. *(planned)*
- Research questions — questions addressed by current artefacts. *(planned)*
- Research roadmap — planned work, known gaps, and conformance tasks. *(planned)*
- Research ontology — formal vocabulary for concepts shared across experiments. *(planned)*
- [System contracts](system/) — architecture, domain model, interfaces, control loop, assurance mode, and the
  telemetry and action contracts. Each is a stub declaring its intended scope.
- Capability matrix — declared versus executable sensing, reasoning, and actuation capabilities. *(planned)*
- Experiment catalogue — index of experimental artefacts and their intended evidence. *(planned)*
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

## Current experiments

| ID  | Experiment                 | Role in the portfolio                                                                                               | Status |
| --- | -------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------ |
| 001 | Symbolic restoration chain | Studies interpretable symbolic diagnosis, planning, and restoration reasoning                                       |        |
| 002 | Multi-expert blackboard    | Studies coordination of diagnosis knowledge sources and evidence integration                                        |        |
| 003 | Eco-resolution             | Studies multi-agent resource-resolution behaviour and traffic prioritization                                        |        |
| 004 | Multi-RAT simulation       | Provides the shared dual-homed wireless simulation environment, fault scenarios, telemetry, and recovery evaluation |        |

The existing symbolic, blackboard, and reactive-agent components are **baselines and research artefacts**. They are not presumed to be the final architecture for any prospective thesis direction. Future controllers—including optimization-based, learning-based, digital-twin-assisted, and security-aware mechanisms—should be evaluated against common scenarios and comparable assurance metrics whenever possible.

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

Start with [`system/`](system/) for the contracts that define what the research system observes, what it may
do, and how a service assurance requirement is declared.

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
