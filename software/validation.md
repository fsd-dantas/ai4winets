# Contract-foundation validation record

**Date:** 2026-09-21. **Scope:** ECoRA package 0.1.0 contract foundation in this checkout.

Local validation used Windows and CPython 3.13.12 in a fresh project virtual environment.
`pip install -e .` built and installed the editable package successfully; `pip check`
reported no broken requirements. The [dependency snapshot](requirements-validation.txt)
records the runtime versions used. Python 3.11 is the declared minimum, but this validation
record does not claim a local test on every supported Python or operating-system version.

`python -m unittest discover -s tests -v` passed **106 tests**, including generated JSON
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

The **symbolic core and the three planners** are exercised against the properties the
design declares. A* with a zero heuristic matches uniform-cost search on the same graph
and costs, across four problems; the optimal cost matches the enumerated certificate; and
every planner's plan is replayed through the shared validator, which separates
executability from goal achievement. An unknown precondition prohibits the edge, so no
planner switches onto a leg it has no evidence it can reach. Operator effects are
configuration only, checked structurally: none may assert a service outcome. A bounded GPS
failure reports that it found nothing within its budget, which is not infeasibility, and
an exhausted search budget is reported rather than truncated.

One of those tests found a real defect. GPS returned a plan whose second step deleted the
goal its first step had achieved, because it checked only the goals still outstanding.
decision-methods.md warns of exactly this, and the planner now rechecks every goal before
returning, with the undone goals recorded in its trace.

**Rule-based diagnosis** is exercised in both organisations over one shared rule
inventory. The hypothesis under test (RQ-E) is that they agree and that their
orchestration cost does not: a test asserts agreement across four snapshots, including one
where an input is unknown, and it can fail because the two schedule their work
differently. A second test reads the cost difference from the recorded trace rather than
assuming it. Further tests pin that a chained rule waits for its premises, that unknown
evidence is never read as a negative, that a snapshot with no evaluable rule yields an
explicit `insufficient_evidence` hypothesis, that a contradiction is settled by priority
and recorded as inhibited, that equal authority on a contradiction stays unresolved rather
than being decided arbitrarily, that an exhausted activation budget is a typed refusal,
and that a malformed rule inventory is refused when it is bound rather than when it runs.

The **Proposed telemetry provider** is exercised against its declared projection: it
relays the permitted local signals and reports full coverage when they all arrive; an
expected signal the adapter never supplies becomes an explicit unknown with its reason and
lowers declared completeness; a signal older than the declared freshness bound is reported
as stale rather than relayed as fresh; another site's signal is dropped even when offered
and counted in the trace; and a projection that expects a signal it holds no capability
for is refused at configuration rather than at run time.

**Boundary playback** is exercised against a stage whose output depends on its input,
with a negative control: different recorded evidence must not reproduce the same output,
so the test can fail if playback delivered the wrong thing. Replayed evidence names the
run and invocation it was recorded in, belongs to the replaying run's scope, claims no
lineage there, and cannot shed the privilege of what it replays. A provider resumes from a
recorded state snapshot and continues its own counter. Component substitution and
closed-loop continuation are refused rather than approximated, because neither the
simulator continuation nor the prefix verification they would need exists yet.

**Verified continuation** is exercised with its negative control. A recorded run's causal
prefix is regenerated under the recorded configuration and the commands that run actually
applied, and checked against the observations it ingested; rebuilding under a different
world is refused, and the divergence it is refused on appears at the second epoch rather
than the first, so verification has to catch a prefix that started out plausible. A branch
from a verified prefix continues that world under a different treatment, produces evidence
only from its branch point onward, and reports under its own run identity. A closed-loop
branch is refused at the replay seam, because a branch is a run over a verified prefix
rather than a payload spliced into another run's lineage.

The **declared failure cases** each have a test: missing observations retained as unknown
rather than dropped, a batch refused for claiming full coverage while withholding a signal,
competing proposals resolved to one with the rest deferred and exactly one command issued,
a receipt for a command that was never issued refused, an unknown receipt retained while
claiming no application, and interrupted runs quarantined until inspected.

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

Projected against the nominal parameter block, at `run_duration_s=140` and
`decision_period_s=0.100` a run is 1400 epochs, about **4.8 minutes**. The 1935 base runs
then need about **6.43 days of aggregate worker CPU**. The two declared ceilings are
missed by different amounts, and an earlier note here conflated them:

| Resource | Needed | Declared ceiling | Over by |
| --- | --- | --- | --- |
| Aggregate worker CPU | 6.43 days | `max_compute_time_s` = 4.00 days | 1.61x |
| Wall clock at `max_workers=2` | 3.21 days | `max_wall_time_s` = 3.00 days | 1.07x |

CPU is the binding constraint, not wall clock, so raising `max_workers` does not help.
With the declared supplemental and pilot reserves (2395 runs) the CPU figure is 1.99x.

These ceilings are nominal and uncalibrated by declaration, and the pilot that freezes the
final budget is where measurement replaces them. Raising `decision_period_s` to 0.200
halves the epoch count and fits comfortably, but the decision period governs controller
responsiveness and so changes what is being measured; fewer replications trade against the
declared precision target. Group committing journal appends is the one lever with no
research cost, and `fsync` is now about a quarter of the per-epoch figure.

Every number here was measured against the finite reference model, which is a toy. The
ns-3 cost is unmeasured, so **6.43 CPU days is a floor rather than an estimate**.

`python -m ecora showcase .ecora-runs/showcase` runs three treatments over one frozen
study, each differing from the previous one in a single stage binding: the Null baseline,
the closed loop with the action stage bound to the world, the observing arm with the
Proposed telemetry projection, then the two expert organisations. It closes with the RQ-E
comparison, and prints the sensed and relayed signal counts, the
applied actions, the resulting path, the assurance verdict, which binding changed between
each pair, the provenance of the final claim and a re-read integrity check. It completes
in a few seconds and is covered by a test, since it is demonstrated live.

`python -m ecora demo .ecora-runs/example` runs the same invocation sequence for two
frozen treatment bindings. Both produce valid DiagnosisRecord payloads with different
synthetic fixture labels. Each treatment yields three committed datasets, three messages
and ten journal events. `python -m ecora verify .ecora-runs/example/reference` successfully
reopens and verifies the corresponding store. Use fresh demo paths on each execution.

This is contract and integration evidence. It is not evidence for network behaviour,
diagnostic accuracy, formal safety, optimal planning, convergence, real actuator effects,
simulator replay or power-loss durability. Those claims retain their separate acceptance
obligations. See the [package limits](README.md#persistence-limits-and-verification).
