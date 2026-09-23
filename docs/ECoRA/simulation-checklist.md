# Simulation checklist

**Status: partly implemented. Each item states whether it is enforced today, partly in place or planned, and
where its evidence lives.** [Index](README.md)

Three gates, in the order work reaches them: a scenario entering the set, a study freezing, and a claim leaving
the repository. An item that is not yet enforced is still checked by hand at its gate, and the gap is recorded
rather than waived. The reasoning behind the items is in [Simulation fidelity](simulation-fidelity.md).

Status: **in place** — enforced by code or a test · **partial** — some of it enforced, the rest by hand ·
**planned** — by hand until the named backlog item lands.

## Gate 1 — a scenario enters the set

| # | Check | Status | Evidence |
| --- | --- | --- | --- |
| 1.1 | Every site, leg and path named is declared; the scenario builds in the finite model | in place | `ecora.scenario`, `tests/test_scenario.py` |
| 1.2 | The scenario is canonical JSON, and its hash binds into run provenance | in place | [Scenarios](../../scenarios/README.md) |
| 1.3 | The same scenario builds both worlds, and each reports holding what it declares | in place | `tests/test_simulator_adapter.py` |
| 1.4 | The note states the condition, and the condition is observed in both worlds, not assumed | partial | Pilots such as `bottleneck-pilot`; reviewed by hand (S5 was found to be overload this way) |
| 1.5 | Every numeric parameter is in the parameter register, marked nominal until calibrated | partial | [Parameter register](experiments.md#parameter-register) |
| 1.6 | A calibrated parameter cites its dataset, measurement method and build | in place for the LTE rate table | `data/simulator/lte-rate-calibration.json`, ADR-29, ADR-30 |
| 1.7 | The scenario changes only its intended condition, unless a coupled change is part of the hypothesis | partial | Reviewed by hand against S0 |
| 1.8 | The scenario declares its abstraction registry, with a rationale for every non-`included` class | planned | B66 |
| 1.9 | The declared registry matches what the simulator reports it built | planned | B67 |
| 1.10 | Every declared mechanism the scenario exists to exercise is reachable in a run | partial | Reachability tests such as the arbitration window in `tests/test_study.py`; a passing suite alone does not show a mechanism can run |
| 1.11 | The scenario is synthetic and passes the sanitisation checklist | partial | [CONTRIBUTING](../../CONTRIBUTING.md#open-configurations-and-data--sanitisation-checklist) |

## Gate 2 — a study freezes

| # | Check | Status | Evidence |
| --- | --- | --- | --- |
| 2.1 | The study binds one scenario-set version and hash, with every member's revision | in place | [Study freeze contract](methodology.md#study-freeze-contract) |
| 2.2 | Treatments, provider versions and information regimes are named in the comparison matrix | in place | `studies/*.json`, `tests/test_study.py` |
| 2.3 | The simulator build is pinned by checksum, and every response carries its build id | in place | `software/simulator/ns3-build.json`, ADR-28 |
| 2.4 | Seeds and named random streams are recorded; paired treatments share exogenous inputs | partial | B15; the ns-3 run number per request. Pairing policy is B40 |
| 2.5 | Replication count, confidence level and target precision are declared, with pilot variance behind them | planned | B40, B41 |
| 2.6 | Every primary metric names its population, window and aggregation | partial | [Metrics and denominators](experiments.md#metrics-and-denominators), B36 |
| 2.7 | Comparison families, multiplicity handling and branch epochs are preregistered | planned | B40 |
| 2.8 | The assumptions that could reverse a conclusion are listed, with the range each will be varied over | planned | B68, B48 |
| 2.9 | Failed, unsupported and timed-out cells have a declared handling rule | planned | B43 |

## Gate 3 — a claim leaves the repository

| # | Check | Status | Evidence |
| --- | --- | --- | --- |
| 3.1 | The claim names its study, scenario-set version, treatments and run ids | in place | [Claims and comparisons](methodology.md#claims-and-comparisons) |
| 3.2 | The claim states its capability level and does not describe planned behaviour as observed | partial | [CONTRIBUTING](../../CONTRIBUTING.md#claims-and-capability-status); by hand |
| 3.3 | The claim names the world it comes from; a finite-model result is not stated as a network result | partial | By hand |
| 3.4 | The claim names the `out_of_scope` classes of every contributing scenario | planned | B66 |
| 3.5 | No comparative claim rests on a single seed; tails and uncertainty are reported, not only means | planned | B40, B49 |
| 3.6 | Regions where the conclusion weakens or reverses are reported alongside the nominal result | planned | B48, B68 |
| 3.7 | Oracle-conditioned and deployable-information results are reported separately | in place | B37, B38 |
| 3.8 | Missing, failed and excluded runs remain visible | partial | B37; full accounting is B43 |
| 3.9 | The result can be regenerated from committed configuration, build manifest and seeds | partial | Replay (B16, B17); clean-environment reproduction is B53 |
