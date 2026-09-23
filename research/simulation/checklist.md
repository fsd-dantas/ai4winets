# Simulation checklist

**Status: normative methodology. Each track records its status against these items in its simulation
declaration.** [Framework](README.md)

Three gates, in the order work reaches them: a configuration entering a study's set, a study freezing, and a
claim leaving the repository. Item identifiers are stable; declarations refer to them.

A track marks each item **in place** (enforced by code or a test), **partial** (some of it enforced, the rest
checked by hand), **planned** (checked by hand until the named work lands) or **not applicable** (with the
reason). An item that is not enforced is still checked by hand at its gate, and the gap is recorded rather than
waived.

## Gate 1 — a configuration enters the set

| ID | Check |
| --- | --- |
| G1.1 | Every entity the configuration names is declared, and the configuration is validated against its schema when read |
| G1.2 | The configuration is a canonical, hashed artifact, and its hash binds into the provenance of every run |
| G1.3 | The resolved composition (world, topology, RF, network and traffic, conditions, decision policy, seeds) is materialised; nothing depends on an undocumented default |
| G1.4 | The abstraction registry declares every class relevant to the track's claims, with a rationale for each non-`included` class |
| G1.5 | The declared registry matches what the simulator or model reports it built |
| G1.6 | World mode, evaluation population and boundary semantics are declared ([spatial world](spatial-world-model.md)) |
| G1.7 | Every numeric parameter lives in the track's declared parameter block, marked nominal until calibrated |
| G1.8 | Every calibrated parameter cites its dataset, method, build and validity range |
| G1.9 | The condition the configuration claims to create is observed in a run, not assumed from its description |
| G1.10 | A condition variant changes only its intended condition, unless a coupled change is part of the hypothesis |
| G1.11 | Every mechanism the configuration exists to exercise is reachable in at least one run |
| G1.12 | Units, limiting cases and conservation checks pass ([assurance](simulation-assurance.md#verification)) |
| G1.13 | The configuration is synthetic, or its data source and licence are recorded, and it passes the sanitisation checklist in `CONTRIBUTING.md` |

## Gate 2 — a study freezes

| ID | Check |
| --- | --- |
| G2.1 | The study binds one configuration-set version and hash, with every member's revision |
| G2.2 | Treatments, method versions and information regimes are named in a comparison matrix |
| G2.3 | The simulator, model and software revisions are pinned and recorded in every result |
| G2.4 | Seeds and named random streams are recorded; paired treatments share exogenous inputs, or the model's determinism is declared and tested |
| G2.5 | Replication count, confidence level and target precision are declared, with pilot evidence behind them |
| G2.6 | Every primary metric names its population, window, aggregation and uncertainty method |
| G2.7 | Comparison families, multiplicity handling and stopping rules are preregistered |
| G2.8 | Baselines share the action constraints and comparable information of the methods they are compared with |
| G2.9 | Tuning and evaluation use disjoint configurations or seeds where generalisation is claimed |
| G2.10 | The assumptions that could reverse each intended conclusion are listed, with the range each is varied over |
| G2.11 | Failed, unsupported and timed-out runs have a declared handling rule |

## Gate 3 — a claim leaves the repository

| ID | Check |
| --- | --- |
| G3.1 | The claim names its study, configuration-set version, treatments and run identifiers |
| G3.2 | The claim states its capability level and does not describe planned behaviour as observed |
| G3.3 | The claim names the model it comes from, and does not generalise beyond that model's validity domain |
| G3.4 | The claim names the `out_of_scope` classes of every contributing configuration |
| G3.5 | No comparative claim rests on a single stochastic realisation; tails and uncertainty are reported, not only means |
| G3.6 | Regions where the conclusion weakens, reverses or becomes indistinguishable are reported alongside the nominal result |
| G3.7 | Privileged-information and deployable-information results are reported separately |
| G3.8 | Missing, failed and excluded runs remain visible |
| G3.9 | The result can be regenerated from the committed configuration, build or environment record and seeds |
