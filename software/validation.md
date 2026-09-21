# Contract-foundation validation record

**Date:** 2026-09-21. **Scope:** ECoRA package 0.1.0 contract foundation in this checkout.

Local validation used Windows and CPython 3.13.12 in a fresh project virtual environment.
`pip install -e .` built and installed the editable package successfully; `pip check`
reported no broken requirements. The [dependency snapshot](requirements-validation.txt)
records the runtime versions used. Python 3.11 is the declared minimum, but this validation
record does not claim a local test on every supported Python or operating-system version.

`python -m unittest discover -s tests -v` passed **56 tests**, including generated JSON
round-trip properties, malformed inputs, required fields, freeze membership, capability
scope, future/stale evidence, terminal outcomes, inherited privileges and state, immutable
lineage, duplicated deliveries/dispatches, and corruption/interruption handling.

One test drives all seven stages in sequence, including the two assembled inputs, and
checks that each invocation commits an `ok` dataset. Another checks that an assembled
input departing from the frozen study's goals, budgets, costs or cohort windows is
rejected, while the measured counts remain free. The providers these drive are synthetic
fixtures: they emit schema-valid payloads with no diagnostic, planning or measurement
content, so this establishes that the contracts compose and nothing about behaviour.

A further test runs the same seven stages on the **all-Null treatment**, whose providers
are the declared trivial policies rather than fixtures: omitted telemetry, a first-candidate
guess, a one-step plan left `unmet`, a first-feasible resolution, a suppressed receipt, a
receipt-only result and inconclusive claims. It produces a complete traceable report in
which nothing was observed, decided or applied — the baseline a Proposed arm is measured
against, not a failure.

The **finite reference model** has its own tests: repeatability, equality between stepwise
and single-step advance, a monotonic clock, demand that is never lost from the ledger,
refused actuation that does not mutate state, pacing that delays AMI without touching
SCADA, a disturbance that degrades service and then drains its backlog without loss, and
exported observations that satisfy the telemetry contract. It is a deterministic
queueing model with no radio, protocol conformance or calibrated value, and no run of it
is evidence about a wireless network.

**Run orchestration** is exercised end to end: a run produces an assurance report that
resolves to its frozen benchmark and run identity; two runs of one treatment under one
seed plan produce byte-identical journals; stage state carries forward between epochs; a
closed-loop treatment applies the command the Null arm suppresses, and its applied
receipts cite observations the run actually exports. Named random streams are independent:
500 controller draws leave the arrival and disturbance sequences unchanged.

## Measured orchestration cost

A closed-loop run on this workstation costs about **2.1 s per decision epoch** (measured
over 4-epoch and 16-epoch runs, 32 and 116 committed datasets). The cost is dominated by
`fsync` on every object write and journal append, which is the durability the artifact
store deliberately buys.

Projected against the nominal parameter block, this does not fit the declared envelope.
At `run_duration_s=140` and `decision_period_s=0.100` a single run is 1400 epochs, roughly
**49 minutes**; the 1935 base runs of the screening and confirmation designs would need
about **66 days** of wall time against a declared `max_wall_time_s` of 259200 s, exceeding
it by more than twenty times.

This is a measurement of the current harness, not a property of the design. Group-committed
journal appends, a declared durability mode for exploratory runs, or a longer decision
period would each move it. It is recorded here so the pilot that freezes the final budget
starts from a number rather than an assumption.

`python -m ecora demo .ecora-runs/example` runs the same invocation sequence for two
frozen treatment bindings. Both produce valid DiagnosisRecord payloads with different
synthetic fixture labels. Each treatment yields three committed datasets, three messages
and ten journal events. `python -m ecora verify .ecora-runs/example/reference` successfully
reopens and verifies the corresponding store. Use fresh demo paths on each execution.

This is contract and integration evidence. It is not evidence for network behaviour,
diagnostic accuracy, formal safety, optimal planning, convergence, real actuator effects,
simulator replay or power-loss durability. Those claims retain their separate acceptance
obligations. See the [package limits](README.md#persistence-limits-and-verification).
