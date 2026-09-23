# Simulation assurance

**Status: normative methodology.** [Framework](README.md)

Verification, validation, calibration, uncertainty and reproducibility requirements for every simulation study
in this repository. A result is not credible because the model runs or produces plausible plots.

## Definitions

| Activity | Question |
| --- | --- |
| Verification | Was the model implemented correctly with respect to its specification? |
| Validation | Is the model adequate for the intended use and target system? |
| Calibration | Were uncertain parameters fitted to appropriate evidence? |
| Uncertainty quantification | How do uncertain inputs and random effects affect conclusions? |
| Sensitivity analysis | Which assumptions materially drive outputs? |
| Replication | Can an independent run using the same method reproduce the result? |
| Reproducibility | Can another researcher recreate the computational result from the shared artifact? |

Agreement between two implementations of the same declared model is verification, not validation: it shows
both implement the specification, not that the specification matches a target system.

## Verification

At minimum:

- unit tests for custom schedulers, traffic generators, objective or reward functions, adapters, failure
  injectors, metric collectors and configuration parsers;
- conservation checks where applicable: offered = delivered + dropped + queued or remaining;
- unit checks: Hz/MHz, W/dBm, m/km, s/ms/slots, bytes/bits, coordinate reference;
- limiting-case checks: no load, no interference, no fading, static nodes, ideal CSI, infinite buffer, disabled
  failures, deterministic seeds;
- schema validation of scenario and world-model artifacts;
- regression tests for known reference configurations;
- exact references (enumeration, closed form, certified optimum) wherever the problem is small enough;
- **reachability**: a declared mechanism a scenario exists to exercise is shown to act in at least one run. A
  passing test suite does not establish that a mechanism can run.

Tests assert properties (admissibility, invariants, bounds, conservation), not only expected outputs.

## Validation

Validation evidence is proportional to the strength of the claim:

| Claim type | Expected validation evidence |
| --- | --- |
| Analytical link or queue result | Hand calculation or theoretical comparison |
| Protocol or algorithm behaviour | Specification, reference implementation, exact reference or known benchmark |
| RF or channel behaviour | Standard model, measurement data, radio map, or controlled SDR or testbed comparison |
| End-to-end network behaviour | Trace, laboratory, emulation, independently implemented simulator, or testbed |
| Decision-method or deployment claim | Cross-scenario robustness, realistic observability and delay, baselines, and emulation or experiment where possible |
| Digital-twin or site-specific claim | Site inventory or map, measurement calibration and out-of-sample validation |

Validation states its validity domain: a match under one load, geometry, frequency or mobility condition does
not validate the others. A study with no validation against a target system says so, and its claims are about
the declared model.

## Calibration

For each calibrated parameter, record:

- name, unit, prior or range, fitted value and uncertainty interval;
- data source and collection context;
- estimation method and objective function;
- calibration and holdout split where applicable;
- version or hash of the source data and fitting script.

Uncalibrated parameters are marked nominal in the track's declared parameter block.

## Randomness and seeds

Use independent random-number streams for at least, where present:

- spatial topology and population;
- shadowing and fading;
- traffic arrivals and packet sizes;
- mobility;
- failures and attacks;
- stochastic tie-breaking;
- exploration, initialisation and sampling in learned methods.

Record all root seeds, stream derivation rules and software versions. Comparative experiments should use paired
stochastic realisations where this improves statistical power. A fully deterministic model declares its
determinism and the test that shows it (identical output for identical input); one run per configuration is
then the complete record for that configuration.

## Statistical reporting

Every primary KPI reports:

- sample and replication count;
- a central estimate appropriate to the metric;
- dispersion or an uncertainty interval;
- percentiles and tails when latency, reliability or outage matter;
- the population and aggregation window;
- the warm-up removal policy for steady-state simulations;
- the stopping rule or simulation horizon.

A single stochastic realisation does not support a comparative performance claim. Packets or events within one
run are not independent replications.

## Sensitivity and robustness

Each study varies the assumptions that could plausibly reverse its conclusion, as relevant:

- path-loss and shadowing parameters;
- interference density and load;
- traffic demand and burstiness;
- bandwidth, buffer, scheduler and retransmission policy;
- mobility and topology;
- compute, inference and control delay;
- failure frequency, duration and correlation;
- objective weights, observation delay, action constraints and training seed;
- world mode, guard width or truncation radius;
- problem-instance family and size, for algorithmic claims.

Report the parameter regions where conclusions weaken, reverse or become statistically indistinguishable, not
only the nominal point.

### Abstraction validity

To judge whether a reduced abstraction $A$ is adequate, compare it with a designated reference model $R$ on each
primary metric $M$:

$$
\Delta_M(A, R) = \frac{|M(A) - M(R)|}{\max(|M(R)|, \varepsilon)}.
$$

$A$ is acceptable when $\Delta_M(A, R) \le \tau_M$ for all primary metrics, with $\tau_M$ declared in advance,
or when the deviations are reported as a limitation and do not alter the qualified conclusion. Study families
worth running where they apply: spatial-world and boundary sensitivity, RF and channel alternatives
(free-space, log-distance, shadowing correlation, fading on and off, interference- versus noise-limited),
network and service variation (load, burstiness, queues, scheduler, retransmission, backhaul, recovery timing)
and control variation (observation noise and delay, action delay, constraints, objective weights, held-out
scenarios).

## Reproducibility artifact

A reproducible study artifact includes:

- source code and commit revision;
- scenario files and fully resolved configurations;
- a dependency lockfile or container recipe;
- the simulator and adapter revision;
- seed tables;
- raw outputs or an immutable retrieval manifest;
- metric-extraction and plotting scripts;
- hardware, OS and runtime information;
- a README with execution commands and expected outputs;
- licence and data-access restrictions.

## Result provenance

Each result set stores machine-readable provenance:

```json
{
  "provenance": {
    "experiment_id": "string",
    "resolved_config_hash": "string",
    "code_commit": "string",
    "simulator_version": "string",
    "container_or_environment_hash": "string",
    "seed_bundle": "reference",
    "run_start_time": "ISO-8601",
    "run_end_time": "ISO-8601",
    "hardware": "declared",
    "raw_output_manifest": "reference"
  }
}
```
