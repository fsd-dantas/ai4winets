# Contract-foundation validation record

**Date:** 2026-09-21. **Scope:** ECoRA package 0.1.0 contract foundation in this checkout.

Local validation used Windows and CPython 3.13.12 in a fresh project virtual environment.
`pip install -e .` built and installed the editable package successfully; `pip check`
reported no broken requirements. The [dependency snapshot](requirements-validation.txt)
records the runtime versions used. Python 3.11 is the declared minimum, but this validation
record does not claim a local test on every supported Python or operating-system version.

`python -m unittest discover -s tests -v` passed **57 tests**, including generated JSON
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

A closed-loop run on this workstation costs about **0.20 s per decision epoch**, measured
over 8-epoch and 32-epoch runs (177 and 205 ms respectively; the difference is the growing
model event history, not the store).

An earlier measurement put this at 2.1 s per epoch and attributed it to `fsync`. That
attribution was wrong, and the correction is worth recording. Direct measurement shows
57 `fsync` calls per epoch at 0.88 ms each, about 50 ms — under three per cent of the
original figure. Stubbing `fsync` out entirely left the epoch cost essentially unchanged.

Profiling found the actual cost: `ArtifactStore.get` was called 16417 times in a six-epoch
run, roughly 2700 reads per epoch for nine invocations, and every read re-parsed the JSON
and re-ran full schema validation on a record that is content-addressed and immutable.
Twenty-one of thirty-five profiled seconds were inside `jsonschema`. Records are now
memoised by content hash, which removes the revalidation without changing what is stored:
a run under a one-entry cache produces the same journal as one under the default.

The trade is explicit. An ordinary read no longer revalidates; it confirms the object is
still present, so deleted evidence is still caught on the read that needs it, while a file
whose contents changed underneath the process is caught by `verify()` or by reopening the
store. Both are exercised by tests.

Projected against the nominal parameter block this still does not fit the declared
envelope. At `run_duration_s=140` and `decision_period_s=0.100` a run is 1400 epochs,
about **4.8 minutes**; the 1935 base runs need roughly **6.4 days** against a declared
`max_wall_time_s` of 259200 s, exceeding it by about a factor of two rather than twenty.

Closing the remainder is a budget decision rather than an engineering one, and belongs to
the pilot that freezes it. `fsync` is now about a quarter of the per-epoch cost, so group
committing journal appends would reach roughly 4.9 days; raising `decision_period_s` to
0.200 halves the epoch count. Either alone is insufficient and both together fit. These
are measurements of this harness on one workstation, not properties of the design.

`python -m ecora demo .ecora-runs/example` runs the same invocation sequence for two
frozen treatment bindings. Both produce valid DiagnosisRecord payloads with different
synthetic fixture labels. Each treatment yields three committed datasets, three messages
and ten journal events. `python -m ecora verify .ecora-runs/example/reference` successfully
reopens and verifies the corresponding store. Use fresh demo paths on each execution.

This is contract and integration evidence. It is not evidence for network behaviour,
diagnostic accuracy, formal safety, optimal planning, convergence, real actuator effects,
simulator replay or power-loss durability. Those claims retain their separate acceptance
obligations. See the [package limits](README.md#persistence-limits-and-verification).
