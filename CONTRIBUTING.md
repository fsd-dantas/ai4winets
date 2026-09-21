# Contributing

Issues and pull requests are welcome. Before proposing a large change, open an issue describing the problem
and the research question the change serves.

A contribution to this repository should improve one of: research evidence, reproducibility, documentation
quality, experimental validity, or software reliability. A change that adds a controller, a metric or a
scenario without naming the question it answers and the comparison it enables will be asked to do so first.

## Conventions

- **English.** Documentation, identifiers, commit messages and test names are written in English.
- **No accented characters in source files.** This avoids terminal encoding problems; Markdown documentation
  uses full accentuation where a quoted term needs it.
- **Tests assert properties** — admissibility, plan validity, invariants, bounds — rather than only expected
  outputs.
- **Declared thresholds.** Every numeric parameter a rule, policy or controller depends on lives in one
  declared block and is marked as nominal and uncalibrated until a calibration procedure is documented.
- **Figures** are written in English, with light and dark variants. See *Images and figures* below.

## Claims and capability status

Every claim in this repository must be traceable to code, data, or cited evidence. State the status of a
described capability using the repository's four levels:

| Level | Meaning |
| --- | --- |
| **Implemented** | Behaviour exercised by executable code in this repository. |
| **Simulated** | Behaviour represented in a model and evaluated under stated assumptions. |
| **Planned** | A documented direction that is not yet implemented or validated. |
| **Unsupported** | A concept the current simulator, telemetry model or controller cannot represent. |

Do not describe a planned capability in language that implies it has been observed. Do not present unavailable
telemetry as observed evidence. Do not generalise a result beyond its model, scenario set, telemetry coverage,
action space, software version and reproducibility evidence.

## Experiment layout

Each experiment lives in `experiments/NNN-name/` with a `README.md` that states:

1. Objective, research question and hypothesis.
2. System model, scenario, assumptions, and fault or threat conditions.
3. Software versions, configuration, inputs and execution procedure.
4. Metrics, results, limitations and reproducibility status.
5. The scope of the claim the observed evidence supports.

Folders such as `configuration/`, `scripts/` and `results/`, and a `report.md`, exist only when they have
content.

For comparative work, hold the network topology, traffic classes, fault or attack scenarios, measurement
intervals and evaluation metrics constant unless a documented research question requires otherwise. Prefer tail
and violation-oriented measures over means alone: deadline-miss ratio, tail latency and jitter, per-class
delivery, availability, mean time to detect, mean time to recover, recovery side effects, and — where
applicable — unsafe-action rate.

## Reproducibility

For every implemented experiment, preserve or document the source code and dependency versions, scenario
definitions and configuration files, input-data origin and licence, random seeds and number of replications,
execution commands, hardware and operating-system constraints, result artifacts, metric definitions and
analysis scripts, and known limitations.

A successful installation is not validation of an experiment. Reproduce the documented command, compare the
stated outputs, and read the limitations before relying on a result.

## Where material belongs

- `research/` — research framing, methodology, questions, ontology and roadmap.
- `literature/` — **references**: literature reviews, critical analyses and evidence synthesis drawn from
  other people's work, with full citation.
- The project **wiki** — **own findings**: theory notes, derivations and study material produced by the
  maintainer. The wiki carries the reasoning; the repository carries the artifacts.
- `experiments/` — reproducible experiments whose main contribution is experimental evidence.
- `software/` — packages, modules, integration code and setup material.
- `scenarios/` — declared scenario definitions shared across experiments.
- `system/` — architecture, domain model, and the telemetry, action and control-loop contracts.
- `docs/` — architecture views, capability matrix, experiment catalogue and getting-started material.
- `data/` — schemas, synthetic inputs and provenance material.

Before publishing material that began in a structured learning setting, remove institutional identifiers,
grades, assessment rubrics, restricted content, private data and copyrighted instructional material, and record
provenance, revision status, assumptions, reproducibility information, limitations and research relevance in
the artifact's README.

## Images and figures

Images live in two places, and which one applies depends on what the image *is*, not on what it looks like.

- **`docs/assets/img/`** — repository-level and explanatory figures: the banner, the social preview,
  architecture diagrams, domain and ontology diagrams, state machines, conceptual illustrations. These explain
  the repository and are referenced from `README.md` and from documents under `docs/` and `system/`.
- **`experiments/NNN-name/results/figures/`** — **evidence figures**: any plot, chart or visualisation produced
  by a run. An evidence figure travels with the configuration, seed and raw data that produced it. Moving it
  into a global image folder severs that provenance link, so it stays with its experiment.

The test is simple: if regenerating the image requires re-running an experiment, it is evidence and belongs
with the experiment. If it can be redrawn from understanding alone, it is explanatory and belongs in
`docs/assets/img/`.

Format and naming:

- **SVG is the source of truth** for diagrams. Commit a raster alongside it only where a consumer needs one —
  the README banner and the GitHub social preview, which do not render SVG reliably.
- Light and dark variants are suffixed `-light` and `-dark`, and README references pair them with a
  `<picture>` element so the banner follows the reader's theme.
- Figure generators are local tooling and are not tracked: `docs/assets/src/` is gitignored. The figures they
  produce are versioned.
- Apply the sanitisation checklist below to images as well. A topology diagram or a plot axis label can carry
  a real site name as easily as a configuration file can.

## Open configurations and data — sanitisation checklist

Configurations and data behind published results are themselves published. Nothing that identifies a real
network may therefore enter this repository. Every scenario here is **synthetic**. Before any commit
containing configuration, telemetry or topology, check:

- [ ] no real subscriber key (`Ki`, `OPc`), IMSI or IMEI;
- [ ] no real operator PLMN (MCC/MNC);
- [ ] no real IP addressing, hostname, serial number or equipment identifier;
- [ ] no real coordinate, substation name, site name or field topology;
- [ ] no customer, employer or project name, and no material carrying one;
- [ ] identifiers are synthetic and declared as such in the artifact that uses them.

A file that fails any line of this checklist does not enter the repository, even in a branch.

## Commits

Messages in English, imperative mood, with a paragraph explaining why when the reason is not obvious from the
diff.

## Releases

1. Bump the version in `CITATION.cff` (and in the package metadata once a package exists), and move the
   `[Unreleased]` notes to the new version in `CHANGELOG.md`.
2. Create and push the tag: `git tag vX.Y.Z && git push origin vX.Y.Z`.
