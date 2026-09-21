# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project follows
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added

- Selected ECoRA v1 research scope for synthetic wireless backhaul: workload obligations,
  label-free ordinary controller inputs, local agent and actuator boundaries, service/safety
  criteria, finite Oracle problems and preliminary parameter/resource budgets. The
  presentation and experimental questions are linked to the scope; runtime work remains planned.

- Repository charter in [`README.md`](README.md): purpose, research focus, the three exploratory research
  directions, the experimental philosophy and its four capability levels, reproducibility requirements, and
  the status and limitations that govern how any artefact here should be read.
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

- The quick start moved from `README.md` into [`docs/ECoRA/README.md`](docs/ECoRA/README.md), where the
  reading order and the eventual Python and ns-3 environments belong to the framework they describe.
  `README.md` keeps one line stating that no executable software has landed, pointing to it.
- `README.md` states what the repository is and guarantees, rather than instructing contributors. *Experimental
  philosophy* and *Reproducibility and scientific claims* merged into **Evidence and Reproducibility**; the
  metric list and the hold-conditions-fixed rule were removed in favour of the framework documents that make
  them binding, and the material duplicating [`CONTRIBUTING.md`](CONTRIBUTING.md) now points to it instead.
- `README.md` is scoped to the repository rather than to one framework. The ECoRA exposition moved to
  [`docs/ECoRA/README.md`](docs/ECoRA/README.md), which now carries the framework-element and arm tables and
  the statement that every method in it is a baseline. In its place `README.md` carries an **experiment
  index**: the studies this repository intends to run, the framework each is designed under, its status, and a
  link to its design. Every entry is declared planned; `experiments/` is empty.
