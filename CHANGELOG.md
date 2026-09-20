# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project follows
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added

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
- Repository banner and social preview under `docs/assets/img/`, carried over from the predecessor repository
  in light and dark variants with SVG sources. The tagline now reads *Assurance for critical wireless
  networks* in place of the predecessor's *A knowledge base for wireless AI research*, and the social preview
  carries this repository's URL. Rasters are rendered from the SVG sources with headless Chrome at the
  viewBox dimensions:
  `chrome --headless=new --disable-gpu --hide-scrollbars --screenshot=<out>.png --window-size=<w>,<h> file:///<in>.svg`
- Image policy in [`CONTRIBUTING.md`](CONTRIBUTING.md): explanatory figures in `docs/assets/img/`, evidence
  figures with the experiment that produced them.
- Statement of the open data and open configurations commitment in [`README.md`](README.md).

### Notes

This repository succeeds `applied-ai-for-wireless-communication`, which framed a single question on auditable
diagnosis, planning and routing for multi-RAT smart-grid networks. The present repository widens the frame to
service assurance in critical wireless networks and keeps three candidate directions open. Material carried
over from the predecessor is re-declared under the capability levels in [`CONTRIBUTING.md`](CONTRIBUTING.md)
rather than inherited as validated.
