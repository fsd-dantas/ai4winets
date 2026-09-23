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

> This is the standard statistical delay bound and is not a formulation original to this work. It restates the normative definition of reliability — the proportion of packets delivered within the time constraint required by the service (3GPP TS 22.261) — as a probability with an explicit violation budget, in the delay-violation-probability form used for wireless link modelling (Wu and Negi, 2003). Preferring tail and violation-oriented measures over averages follows the same argument (Bennis, Debbah and Poor, 2018). The deadline $D_i^{\max}$ is domain-specific and is not supplied by the formula: for substation communications it derives from the IEC 61850-5 transfer-time classes. Full entries and provenance are in [`literature/`](literature/).

The repository currently explores three interconnected directions:

| Direction | Guiding question | Current repository connection |
|---|---|---|
| **Assurance-constrained multi-RAT intelligence** | How can heterogeneous wireless paths and radio access technologies be selected, coordinated, duplicated, or recovered to maintain critical-service guarantees? | Dual-homed and multi-RAT network scenarios, failover logic, traffic prioritization, and simulation experiments |
| **Digital-twin-assisted self-healing** | How can a calibrated network representation use telemetry to predict service degradation, evaluate remedial actions, and safely support closed-loop recovery? | NS-3 scenarios, telemetry exports, causal replay, versioned results, ontology, and diagnosis contracts |
| **Cyber-resilient deterministic communications** | How can a critical wireless network preserve availability, timing, and integrity during cyber-physical failures and adversarial activity? | Fault diagnosis, provenance-aware telemetry, recovery workflows, service differentiation, and planned threat modelling |

These are held open as alternatives and possible combinations; narrowing follows evidence rather than
preference. Each is weighed the same way: the clarity and novelty of the gap it addresses, its relevance to
critical wireless and cyber-physical systems, its feasibility against the available simulation, telemetry and
laboratory assets and a tractable action space, the theoretical, systems and experimental contribution it
would make, and the risk of over-scoping it within a doctoral timeframe.

## Repository Map

```text
.
├── research/                  # Research framing, questions, methodology, and roadmap
├── literature/                # Literature reviews, critical analyses, evidence synthesis
├── experiments/               # Studies, their arms, and run artifacts; indexed below
├── scenarios/                 # Declared scenario definitions, versioned and frozen per study
├── system/                    # Executable contracts, once adopted from a framework proposal
├── software/                  # Software packages, modules, integration code, and setup material
├── docs/                      # Documentation, including framework proposals
│   ├── ECoRA/                 # ECoRA framework package: architecture, contracts, methodology
│   └── assets/img/            # Repository-level figures, banner, and social preview
├── data/                      # Schemas, synthetic inputs, and provenance material when applicable
├── CITATION.cff               # Citation metadata
├── CHANGELOG.md               # Versioned change history
├── CONTRIBUTING.md            # Contribution conventions
├── CODE_OF_CONDUCT.md         # Participation expectations
└── LICENSE                    # Repository licence
```

### Core Documentation

- [Research question and scope](research/research-questions.md) — the question under study, the comparisons that address it, and the boundary of what its evidence can claim.
- [Literature](literature/) — references, citation conventions, and provenance notes for every borrowed   formulation. This directory holds engagement with other people's work, always cited.
- [System contracts](system/) — normative interfaces, telemetry and action contracts; executable validation
  and audited provider boundaries are in the [contract package](software/README.md).
- [Framework proposals](docs/) — the architectures the studies are built on. The first is [ECoRA](docs/ECoRA/), a planned framework for measuring how observation, reasoning, planning and coordination contribute to network control under declared service requirements. It is one framework this repository uses, not the repository's subject; its full package stays in its own folder.

**The ECoRA contract foundation is executable.** The framework's [quick start](docs/ECoRA/README.md#quick-start)
links installation, tests and a synthetic provider-substitution demo. Simulation and research
decision methods remain planned; contract tests are not network-performance evidence.

Documents below are not yet written. They are listed so the intended structure is visible; each becomes a link when it lands.

- Research problem statement — problem framing and scope. *(planned)*
- Research roadmap — planned work, known gaps, and conformance tasks. *(planned)*
- Capability matrix — declared versus executable sensing, reasoning, and actuation capabilities. *(planned)*
- Getting started — entry points for readers and contributors. *(planned)*

## Evidence and Reproducibility

Every experiment here is an evidence-bearing artifact, and the repository is explicit about what each one's evidence can carry. Four levels describe any capability it mentions:

- **Implemented** — behaviour exercised by executable code.
- **Simulated** — behaviour represented in a model and evaluated under stated assumptions.
- **Planned** — a documented direction that is not yet implemented or validated.
- **Unsupported** — a concept the current simulator, telemetry model, or controller cannot represent.

No result is generalised beyond its observed model, scenario set, telemetry coverage, action space, software version, and reproducibility evidence. Unavailable telemetry is never presented as observed evidence, and a planned capability is never described in language implying it was measured.

An experiment that reports a result publishes what a reader needs to regenerate it: source and dependency versions, scenario definitions and configuration files, input-data origin, licence and transformations, random seeds and replication count, execution commands, hardware and operating-system constraints, raw or versioned result artifacts, metric definitions and analysis scripts, and the limitations that bound the claim.

Three things are deliberately not restated here. Metric definitions and the rule that a comparison holds its conditions fixed belong to the framework a study is designed under — for ECoRA, the [study freeze contract](docs/ECoRA/methodology.md) and its [metrics and denominators](docs/ECoRA/experiments.md#metrics-and-denominators), where they bind rather than advise. The working conventions are in [CONTRIBUTING.md](CONTRIBUTING.md).

## Experiment Index

**The entries below are planned studies, not reported experimental results.** Each design links to its documentation; reproducible execution artifacts will live in a study directory under `experiments/` when available.

| Study | What it measures | Framework | Status | Design |
| --- | --- | --- | --- | --- |
| Factorial screen | Main effects and interactions of telemetry, diagnosis, planning and resolution on a small frozen scenario set | ECoRA | planned | [Declared factorial and confirmatory design](docs/ECoRA/experiments.md#declared-factorial-and-confirmatory-design) |
| Full-set confirmation | Conditional paired effects around the all-Proposed configuration, on a separately frozen full set | ECoRA | planned | [Declared factorial and confirmatory design](docs/ECoRA/experiments.md#declared-factorial-and-confirmatory-design) |
| Information-headroom comparison | What a contract-limited controller can reach against a privileged current-state reference | ECoRA | planned | [Stage arms and oracles](docs/ECoRA/stage-arms.md) |
| Planner microbenchmark | Search effort and plan validity on interacting symbolic goals | ECoRA | planned | [Scenario catalog, S8](docs/ECoRA/experiments.md#scenario-catalog) |
| Distributed channel assignment as map coloring | Whether agents, one per region, reach a verified conflict-free four-coloring through DPOP messages alone; minimum-cost channel plans; how separators set table size; channel reassignment when a mobile cell moves | Standalone DCOP / DPOP | planned | [Design](docs/dcop-channel-assignment/README.md) · [Architecture](docs/dcop-channel-assignment/architecture.md) · [Development backlog](docs/dcop-channel-assignment/development-backlog.md) |

When an experiment lands, its directory carries the objective and hypothesis, the scenario set version it was frozen against, the software versions and seeds, the execution command, the raw artifacts, the analysis, and the limitations that bound its claim. A study with no reproducible execution record remains marked as planned in this index.

Frameworks are listed here only as the source of a study's design. A framework proposal on its own is not experimental evidence, and no entry above should be read as a result.

## Learning Artifacts and External Work

This repository may contain technical artifacts initially produced in structured learning settings when they have been revised into reusable scholarly material. Such artifacts are included to document intellectual development, strengthen reproducibility, and support research-direction assessment.

They are not presented as institutional submissions, graded work, institutional positions, or formally approved research outputs.

Such an artifact is placed by what it contributes: an evidence-synthesis critique in `literature/`, a reproducible implementation or simulation in `experiments/`, a framing or feasibility study in `research/`. Notes, derivations and study material recording the maintainer's **own** reasoning go to the project wiki rather than here — the wiki carries the reasoning, the repository carries the artifacts it produced. Nothing is published before the sanitisation checklist in [CONTRIBUTING.md](CONTRIBUTING.md) has been applied to it.

Each artifact records its own provenance, revision status, assumptions, reproducibility information, limitations and research relevance, using this template:

```md
# Scholarly Learning Artifact: <Title>

## Purpose
This artifact records an independent technical study of <topic> and its
relevance to the exploratory research directions in this repository.

## Research relevance
- Assurance-constrained multi-RAT intelligence:
- Digital-twin-assisted self-healing:
- Cyber-resilient deterministic communications:

## Artifact type
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

## Open Data and Configurations

The inputs behind a published result are published with it, not only the result. Two things are meant by this, and they fail differently:

- **Open data** — the datasets a claim rests on: telemetry exports, simulation outputs, measurement traces, with their origin, generation method, licence and transformations documented. Data without configurations gives a reader numbers they cannot regenerate.
- **Open configurations** — the machine-readable setup that produced those data: scenario definitions, topology declarations, fault-injection specifications, parameter blocks, random seeds, build settings and version pins. Configurations without data give a reader a recipe with no reference output to check against.

Reproducibility needs both, plus the execution command and the metric definitions. This commitment binds at commit time rather than at publication time: once configurations are declared open, every configuration file entering the repository is already a publication decision. The checklist in [CONTRIBUTING.md](CONTRIBUTING.md) is what keeps that commitment reliable.

The provenance chain that links the two halves is `study → scenario → run → dataset`, and it is the structure against which FAIR compliance and artifact evaluation are assessed.

## Contributions

This is a single-author research portfolio, and outside correction is welcome: a claim that is not traceable to code, data or cited evidence, a result that does not reproduce, a reading of the literature that is wrong. [CONTRIBUTING.md](CONTRIBUTING.md) states the conventions, what a contribution is expected to improve, and the sanitisation checklist that governs any configuration or data entering the repository.

## Status and Limitations

This is an active exploratory repository. It contains implemented software, documented models, simulation results, literature material, and planned directions at different levels of maturity.

In particular:

- A simulation result is not equivalent to field validation.
- A controller that succeeds in a limited scenario is not automatically robust under broader operating conditions.
- Unavailable telemetry must not be represented as observed evidence.
- A planned experiment, model, controller, or theme is not a validated contribution.
- The present repository supports research exploration; it does not yet establish an end-to-end validated critical-infrastructure solution.

Any artifact here is read through its declared capability level, its stated limitations, its reproducibility status, and the research roadmap.

## Citation

If you use this repository, please cite the versioned software record described in [CITATION.cff](CITATION.cff).

```text
DANTAS, Fernando Sabino. Applied AI for Wireless Communication:
research knowledge base and research framework for applying artificial
intelligence to wireless communication systems. GitHub repository, 2026.
Available at: https://github.com/fsd-dantas/ai4winets.
```

## Licence

This repository is distributed under the terms of the [MIT License](LICENSE), except where a specific artifact, dataset, dependency, or externally sourced material declares different terms. Material entering the repository is compatible with the applicable licence and attribution obligations.

---

**Research posture:** explore broadly, document precisely, reproduce rigorously, and narrow the research question only when evidence supports the decision.
