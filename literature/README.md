# Literature

**References.** This directory holds engagement with other people's work: literature reviews, critical
analyses and evidence synthesis, always fully cited. The maintainer's own findings, derivations and study
notes belong in the project wiki, not here.

## Contents

| Item | Purpose |
| --- | --- |
| [`references.bib`](references.bib) | BibTeX entries for every work cited in this repository |
| [`assurance-formulation.md`](assurance-formulation.md) | Provenance of the service assurance constraint used in `README.md` |

## Conventions

- **Every claim attributed to a source names that source.** A reference in prose without a matching entry in
  `references.bib` is incomplete.
- **Distinguish what a source states from what this repository infers from it.** A synthesis note says which
  is which; where the two are merged, the note is not yet finished.
- **Record the verification status of each entry.** A citation assembled from a secondary source — a survey, a
  vendor paper, a textbook summarising a standard — is marked as such until the primary text is consulted.
  This matters most for standards, whose clause numbering and threshold values change between editions.
- **Note the edition or version for standards**, since requirements are not stable across releases.
- A critical analysis of one work is stored as `<author>-<year>/` with the analysis alongside any extracted
  data; a synthesis across several works is stored by topic.
