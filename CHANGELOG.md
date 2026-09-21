# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project follows
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added

- Executable ECoRA contract foundation in `software/ecora`: versioned schemas, immutable
  JSON records and dataset lineage, frozen-study admission, provider registry, audited
  boundary execution, capability/privilege enforcement, terminal outcomes and duplicate
  delivery/dispatch protection. Includes exported schemas, synthetic fixtures, installation
  metadata, CLI and property/invariant tests. Simulator and research providers remain planned.

- Selected ECoRA v1 research scope for synthetic wireless backhaul: workload obligations,
  label-free ordinary controller inputs, local agent and actuator boundaries, service/safety
  criteria, finite Oracle problems and preliminary parameter/resource budgets. The
  presentation and experimental questions are linked to the scope; runtime work remains planned.

- Repository charter in [`README.md`](README.md): purpose, research focus, the three exploratory research
  directions, the experimental philosophy and its four capability levels, reproducibility requirements, and
  the status and limitations that govern how any artifact here should be read.
- System contract stubs under [`system/`](system/): architecture, domain model, interfaces, control loop,
  assurance mode, and the telemetry and action contracts. Each declares `Status: planned` and states its
  intended scope; none carries a normative specification yet.
- Repository governance: [`LICENSE`](LICENSE), [`CITATION.cff`](CITATION.cff),
  [`CONTRIBUTING.md`](CONTRIBUTING.md) with the sanitisation checklist for open configurations and data, and
  [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
- `.gitignore` and `.gitattributes`, the latter pinning LF endings for files consumed by Linux tooling.
- Repository banner and social preview under `docs/assets/img/`, in light and dark variants with SVG sources,
  under the tagline *Assurance for critical wireless networks*. Rasters are rendered from the SVG sources with
  headless Chrome at the viewBox dimensions:
  `chrome --headless=new --disable-gpu --hide-scrollbars --screenshot=<out>.png --window-size=<w>,<h> file:///<in>.svg`
- Image policy in [`CONTRIBUTING.md`](CONTRIBUTING.md): explanatory figures in `docs/assets/img/`, evidence
  figures with the experiment that produced them.
- Statement of the open data and open configurations commitment in [`README.md`](README.md).
- First content under [`literature/`](literature/): citation conventions, `references.bib`, and a provenance
  note for the service assurance constraint recording that it is the standard statistical delay bound rather
  than a formulation original to this work. Entries carry a verification status, and the note lists the
  verification tasks still outstanding.

- **ECoRA — Expert Coordination, Resolution, and Assurance**: the architectural proposal under
  [`docs/ECoRA/`](docs/ECoRA/), covering the context map and bounded contexts, the domain ontology and its
  machine-readable vocabulary, the stage contracts, the decision methods, the nested-loop methodology with its
  study freeze contract, the experimental design and ablation matrix, and the recorded architectural
  decisions. Every capability it describes is declared **planned**.
- The ECoRA package presents the framework as a single instrumented pipeline: the two-loop separation,
  Coordination and Resolution as cross-cutting concerns, the Null/Proposed/Oracle ablation arms, and an
  explicit statement that no architectural novelty is claimed.

### Changed

- `StudyManifest` gains a required study-level `assembly` block that freezes what the
  assembled stage inputs contain: planning goals, operator catalog version, action costs,
  budgets and horizon, and the cohort identities, generation windows and deadlines. An
  assembled input departing from it is rejected at the boundary; only run-derived parts —
  predicates, and a cohort's measured counts — stay free. It is study-level rather than
  per treatment, so varying an assembly parameter starts a new study instead of becoming
  an undeclared factor beside the arms being compared. This adds a required field to a
  record type; no frozen study exists yet, so the contract stays at schema version 1.
- Stage inputs that the interface defines as **built from** upstream evidence — a
  `PlanningProblem` from a `DiagnosisRecord`, a `ResultInput` from receipts and a cohort
  specification — are assembled by a separate logged harness invocation rather than routed
  as the previous stage's raw output. That construction carries goal and cohort selection,
  which a study holds fixed across a stage's Null, Proposed and Oracle arms, so it cannot
  sit inside the provider being compared. A record the next stage cannot consume is now
  addressed to `sink` and retained as evidence. One test drives all seven stages.
- An invocation is marked delivered when a single consumer has received its whole output
  dataset. Delivery was previously pooled across consumers, which would report completion
  when no one consumer held all of it.
- `README.md` drops the *Candidate Research Directions* section; it prescribed a template
  under a `research-directions/` directory that does not exist. The three directions remain
  in *Research Focus*, which now states the criteria each is weighed against.
- Spelling normalised to `artifact` throughout.
- The quick start moved from `README.md` into [`docs/ECoRA/README.md`](docs/ECoRA/README.md), where the
  reading order and the eventual Python and ns-3 environments belong to the framework they describe.
  `README.md` points to that quick start; it now distinguishes the executable contract
  foundation from the planned simulator and research methods.
- `README.md` states what the repository is and guarantees, rather than instructing contributors. *Experimental
  philosophy* and *Reproducibility and scientific claims* merged into **Evidence and Reproducibility**; the
  metric list and the hold-conditions-fixed rule were removed in favour of the framework documents that make
  them binding, and the material duplicating [`CONTRIBUTING.md`](CONTRIBUTING.md) now points to it instead.
- `README.md` is scoped to the repository rather than to one framework. The ECoRA exposition moved to
  [`docs/ECoRA/README.md`](docs/ECoRA/README.md), which now carries the framework-element and arm tables and
  the statement that every method in it is a baseline. In its place `README.md` carries an **experiment
  index**: the studies this repository intends to run, the framework each is designed under, its status, and a
  link to its design. Every entry is declared planned; `experiments/` is empty.
