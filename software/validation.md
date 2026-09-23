# Contract-foundation validation record

**Date:** 2026-09-21. **Scope:** ECoRA package 0.1.0 contract foundation in this checkout.

Local validation used Windows and CPython 3.13.12 in a fresh project virtual environment.
`pip install -e .` built and installed the editable package successfully; `pip check`
reported no broken requirements. The [dependency snapshot](requirements-validation.txt)
records the runtime versions used. Python 3.11 is the declared minimum, but this validation
record does not claim a local test on every supported Python or operating-system version.

`python -m unittest discover -s tests -v` passed **178 tests**, including generated JSON
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

**Cohort extraction and requirement evaluation** give the last two stages a Proposed arm.
Until they existed every run ended inconclusive by construction rather than by finding,
because nothing in the pipeline could reach a verdict. A run now returns `met` for the
declared delivery requirement, citing the ratio and the population it was computed over.

Both refuse to be more confident than their evidence. A ratio with no population is
unknown rather than perfect, since zero delivered out of zero generated is not full
delivery. A requirement is inconclusive, and says which, when its measurement is absent,
present but unmeasured, computed over an empty population, or when outstanding demand
exceeds the declared missingness limit, because delivery can look perfect while most of
the demand is still withheld. The report states how many requirements it could evaluate
and that an inconclusive one is not a passing one.

The **action Oracle is a declared equivalence** rather than a second implementation. The
integration is direct enough that a privileged application and the Proposed one are the
same operation, and stage-arms.md says to declare that instead of inventing a gap, since a
fabricated difference between two arms would be measured as though it were real.

**Exact references at contract-limited information** cover planning and resolution. The
exact planner enumerates the bounded configuration graph and will only call a plan optimal
when its cost matches that enumerated table, so the claim is checked against an exact
answer rather than asserted by the search that produced it. Where it cannot finish it says
so: an unreachable goal, a space beyond its declared bound and an exhausted budget each
yield no certificate and no optimality claim. The exact resolver enumerates proposal
subsets, keeps the conflict-free ones and ranks them by the declared objective in its
declared order, refusing rather than approximating when there are more proposals than its
bound permits.

Measuring the planning stage produced a finding about the experimental design rather than
about any method. The v1 configuration domain has six reachable states and every goal is
one operator away, so uniform cost, A* and GPS return the same optimal cost on every
problem in it. Planning headroom against an exact reference is therefore zero here by
construction rather than by measurement, and a factorial varying the planning stage over
this domain would be varying something that cannot differ. The design already anticipates
this, since S8 is a separate planner microbenchmark over interacting configuration goals,
and a test now records the limitation so it stays visible. What does remain measurable on
this domain is effort: means-ends expands fewer states than exhaustive search.

The **diagnosis Oracle** shares the rule inventory and the inference with the Proposed
arm, so the only difference between them is what each was given. On a faithful run the two
conclude exactly the same thing, and that is the first headroom measurement rather than a
null result: for these predicates in this state, the observation contract loses nothing. A
separate test lets the relayed evidence go stale and the gap opens, with the
contract-limited arm concluding nothing while exact truth still concludes everything.

Reporting that number carries a boundary with it. A small gap alone would not identify
telemetry as the bottleneck; it could equally be an adequate diagnoser, a downstream limit
or a saturated metric, and the showcase says so where it prints the figure.

Wiring the Oracle found a privilege leak. Lineage was harvested from the payload, which
works for telemetry and silently fails for a diagnosis, a plan or a receipt, because those
carry no observations. A truth-holding provider now declares what it read and the boundary
taints the invocation with it, so the label follows the access rather than the shape of
the output, and a provider that succeeded while declaring no read is refused.

The **truth interface** is exercised against each of its restrictions. It opens only what
a truth capability grants, and an observe capability is not a key to it. It serves the
present and refuses both a later and an earlier instant, so a provider can neither look
ahead nor quietly reuse a stale value. Every read is logged and returns a reference that
travels with whatever it produces, and a run confirms that privilege reaches every stage
downstream while the contract-limited arm beside it stays unprivileged throughout.

Truth cannot be handed to an ordinary provider, and two independent guards refuse it:
editing a binding's capabilities fails because they must match the registered provider
spec, and a spec that legitimately holds truth bound at `contract_only` fails because the
two cannot coexist. Wiring the Oracle arm hit that second guard for real, which is how the
capability split between ordinary and privileged grants came to be explicit rather than
assumed.

**Coordination and reasoning measurement** reads a recorded run and reports how the
controller behaved, never how well it served. Stability consults action churn, claim churn
and stale retries and no service outcome at all, because a controller that sat still while
failing its requirements is stable and failing, and folding the two together would hide
the distinction the measurement exists for. Service starvation needs per-reading delivery
evidence the v1 observation contract does not carry, so it is reported as unknown rather
than approximated by something else; what is reported instead is coordination starvation,
an agent that kept proposing and kept being refused.

Two false positives were found and fixed while measuring real runs. A settled controller
proposes a no-op once its goal holds, and refusing a no-op was being counted as deadlock
and as starvation, which reported a system that had finished as one that could not
proceed. Starvation was also keyed by proposal identity, and a fresh proposal each epoch
reset the count of an agent that had been refused throughout; it now follows the agent.

**Pacing** gained an actuator readback and, in the course of adding it, a correction. The
versioned telemetry catalog now carries `pacing_profile` alongside `path_state`: both are
actuator readbacks, reporting the setting an actuator holds so that an applied command can
cite an observation of its application instead of asserting one. The rationale is recorded
in the telemetry contract, which is the normative owner.

Testing it showed the model had implemented pacing as a reduction of the service rate
rather than as a release gate. v1-scope.md says pacing governs gateway release, and the
difference is not cosmetic: a slowly served reading sat at the head of a shared queue and
held SCADA up behind it, so tightening the AMI profile made SCADA service worse and drove
drops from 19 to 443. A researcher reading that would have concluded the AMI lever harms
SCADA, which is the opposite of what it is for. Pacing now holds readings at the gateway.
SCADA delivery is identical under every profile, AMI delivery scales with the profile,
nothing is dropped, and the withheld demand is visible as held rather than disappearing.

An earlier test asserted only that a restricted profile delivered no more than a normal
one. That passed on equality, and it was equal: at the baseline period AMI offers
4096 bit/s, at or below every declared profile, so pacing was inert and the test proved
nothing. It now exercises the profiles where they bite and checks that held demand is not
quietly lost.

The **probe signal** closes the loop the planners needed. A leg that is serving answers a
probe and is concluded viable; a leg whose service has been taken away does not answer,
and the absence is exported as unknown rather than as a slow reply. One test drives the
whole chain -- probe, diagnosis, symbolic projection, plan, command, world -- and asserts
that a probed leg can be switched to while an unprobed one cannot, with only the silent
leg refused and the one still answering left viable.

Two defects surfaced while wiring it, both caught by the contract rather than by
inspection. The adapter batch reported full coverage while carrying a timed-out probe, and
the projection relayed an input observation that was itself missing without counting it as
withheld. Each would have let a batch claim it had seen something it had not.

**Eco-problem solving** is exercised in both halves. The local assessment shows the
asymmetry the design asks for: two services reading the same occupancy reach different
conclusions, one seeing immediate contention and the other room to defer, and the same
reading satisfies one agent while dissatisfying the other. Satisfaction stays a vector of
predicates carrying its own evidence, and an unobservable signal leaves it unknown rather
than false.

The four anti-collision mechanisms are exercised separately before any combination. Each
admits one contender and defers the rest while naming what each was contending with;
uncontended proposals on separate resources both proceed; yield-with-aging follows the
waiting time rather than identity, and reverses when the waits reverse; a conceding agent
keeps its place in the queue rather than being starved by losing; a lost reservation grant
deadlocks rather than proceeding anyway; and backoff draws are per-agent and reproducible.
Marks are visible only in their own neighbourhood, expire on read, and report their reads,
writes and bytes as ideal local shared memory that is explicitly not network overhead.

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

**Scenarios are read, not written in code.** Every file in `scenarios/` builds a world and
that world matches what the file declares, checked scenario by scenario. A world built from
one scenario, described again, hashes to the scenario it came from, so the description and
the thing described cannot drift apart. A model that does not hold what its scenario
declares is refused, field by field, with the field named: a different period, payload,
deadline, site set, egress or leg rate each refuses on its own. A scenario naming a site,
leg or path it does not declare is refused when it is read, and one the finite model cannot
build — the contract fixture among them — is refused before a run starts. Changing a
scenario changes behaviour with no change to code: a silent serving leg delivers less than
the nominal baseline, and a degraded one puts traffic past its deadline.

Running the scenarios exposed how narrow the frozen cohort is. The fixture study's cohort
window is the single instant `end_s: 0`, so an assurance verdict is reached over the one
reading generated at time zero, whatever else the run did: a silent serving leg still
returns `met`. The showcase now prints the population each verdict was scored on beside it,
so a verdict cannot be read as a finding about the run. Widening the window is a study
design decision rather than a fix — a cohort is frozen before measurement — and it is
carried as B36 along with per-service keying.

This closed a defect rather than only adding a feature. The frozen scenario previously
declared a topology and a disturbance list that nothing read, while the world that ran was
built from constants in the harness, so the scenario hash bound into every claim described
conditions that were not the ones the claim came from. Both directions are now closed: a
run from a file is verified against it, and a run from a hand-built model derives its
scenario from that model.

Giving a cohort the service it counts closed a second one. `cohort:ami` had been every
packet generated in its window whatever its service, so an AMI delivery ratio was drawn
from a population that was mostly SCADA. A cohort now counts only the service it names,
and a test checks each cohort's count against the generated packets of that service. A
second requirement is still not evaluable: measurements are keyed by metric alone and the
study freezes one cohort, so a SCADA requirement naming `within_age_delivery` would be
scored against the AMI population. The scenarios therefore declare the one requirement this
pipeline can evaluate, and per-service keying is carried as B36.

**The decision knowledge is data, and three mechanisms now fire that never had.** A study
file supplies the rule inventory, the projection, the planner and coordination
configuration, the predicate map and the frozen assembly. `studies/baseline.json` was
extracted from the constants it replaced and the suite passed unchanged against it, so the
baseline is the same study it was. A file missing a section, or carrying an unknown one, is
refused when it is read: a misspelled section that was skipped would leave the default in
place while appearing to have changed it. So is an inventory whose rule identifiers repeat,
that contradicts a conclusion no rule reaches, whose goals are malformed, or whose predicate
map names a label no rule concludes.

Making the knowledge data was not presentation. Each of three implemented and tested
mechanisms was unreachable, and each was reachable only by changing what the system knows.

**Rule arbitration** could never run. Every contradicting pair in the baseline inventory has
mutually exclusive conditions, so no two contradicting rules can hold at once and the
priority and equal-authority machinery was dead code in practice. `Study.arbitrable()`
reports which pairs can both hold; for the baseline it reports none, and a test asserts
that. Under an inventory that has them, two competing explanations for one growing queue at
equal authority are recorded as unresolved rather than decided, and the weaker of two
unequal authorities is inhibited with the inhibition on the record.

Exercising it exposed a defect in the trace. An inhibited rule is reconsidered on every
later pass and was inhibited again each time, so one inhibition was reported as nine. The
trace is evidence, and a reader counting entries would have been counting passes. It is
recorded once now, and a test checks the entries are distinct.

**Multi-step planning** could never run. The baseline freezes one goal over one fluent, so
every plan was a single action. Two goals over two fluents produce a two-step plan at cost
three under all three searches.

**Coordination had no conflict to resolve.** One site means one agent, so the resolution
stage saw one proposal per epoch for the whole life of the demonstration and its admit,
defer, yield and backoff behaviour was exercised only in its own tests. A planner now emits
one proposal per declared agent, each planning over its own goals, and every agent goal must
be one the study froze. Two service agents at one site with incompatible objectives over the
same resource produce a real contention: one admitted, one deferred, each decision naming
what it conflicted with.

That exposed a second defect, and a more serious one. The pacing operators carried no
preconditions, while the resolver refuses to issue any mutation with no precondition to
cite. Both are defensible alone, and together they made the pacing lever unreachable: a plan
that changed pacing was admitted and then never became a command. It never showed because
the baseline's only goal is path selection. Pacing operators now declare the profile they
move from, which is also what makes their delete effect well founded, and a test asserts
that no pacing operator has empty preconditions.

**Outcomes are measured per service, over cohorts that cover a declared interval.**
Measurements carry the service class their population came from, and a requirement is
judged against its own service: keyed by metric alone, a SCADA requirement was answered by
whatever population the extraction happened to produce, and the coverage check consulted
outstanding demand belonging to another service. Both are tested, including that one
service's outstanding demand does not block another service's verdict.

The frozen cohorts were the single instant `end_s: 0`, so every verdict rested on the one
reading generated at time zero and a silent serving leg still returned met. A study now
declares a warm-up and a measured cohort per service over explicit windows. Censoring is
derived from the run rather than asserted: a cohort is right-censored when the clock
stopped before an outstanding obligation's deadline had elapsed, so a SCADA cohort whose
deadlines have passed is not censored while an AMI cohort still within its deadline is.
Marking every cohort censored told a reader nothing.

**The last two stages have the references stage-arms.md designates for them.** Result and
assurance were the only stages without an Oracle arm. Independent extraction reads the
complete event record through its own declared truth capability, and reference evaluation
re-derives measurements from that record rather than trusting the result it was handed, so
a result stage that under-reported is visible as a difference between the arms rather than
inherited by both. What the evaluator Oracle may not do is score differently: its
requirements and comparators are the study's, exactly as the Proposed arm's are.

An Oracle without the grant it needs is **unsupported and says so**. It returns a refusal
naming the missing capability and emits nothing, rather than quietly becoming the Proposed
arm under an Oracle's name. A test removes the capability and asserts the refusal.

All seven stages now carry all three arms, every declared binding resolves to a provider
that can be invoked, and every Oracle binding declares its information regime. Those are
asserted by tests rather than surveyed by hand, because coverage that is assumed is how an
unsupported cell comes to be reported as though it had been measured.

An **unattended** treatment measures without deciding: the Null arm's telemetry, diagnosis,
planning and resolution with the two assessment stages that can reach a verdict. Without
it, every requirement shown met belonged to an arm that also acted, and a reader had no way
to see what the world does when nothing intervenes.

**Two hygiene results from the previous round's findings.** An operator declaring no
precondition is refused where the catalog is built: it can never be issued, because the
resolver refuses a mutation with no precondition evidence, so it would be planned,
admitted, and silently never become a command. And every list that accumulates across
inference passes is deduplicated where it is written rather than where it is read, with a
test over both organisations asserting that no trace field repeats an entry.

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

`python -m ecora showcase .ecora-runs/showcase` runs ten treatments over one frozen study:
the Null baseline, the closed loop with the action stage bound to the world, the observing
arm with the Proposed telemetry projection, the two expert organisations, uniform-cost
search, means-ends analysis, eco-resolution, the assured arm that reaches a verdict, and
the diagnosis Oracle. `--scenario` selects any world in `scenarios/`, so the demonstration
is not fixed to one set of conditions.

It prints the sensed and relayed signal counts, the applied actions, the resulting path,
the assurance verdict with the population that verdict was scored on, which binding changed
between each pair, the RQ-E and RQ0-headroom comparisons, the provenance of the final claim
and a re-read integrity check. It completes in about twenty seconds and is covered by a
test, since it is demonstrated live.

Two of its statements are derived rather than asserted, because both had drifted from what
the pipeline does. The closing line had claimed every verdict was inconclusive, which
stopped being true once the assurance stage gained an arm that can reach one; it now
reports the verdicts actually reached and the population behind them. The chain summary
reports the bindings that differ between each pair rather than claiming exactly one.

Means-ends analysis and uniform-cost search reach the same plan over this domain, and the
showcase says so and says why: every goal is reachable within a few actions and no operator
interacts with another, so every admissible procedure returns the optimal cost. That is a
property of the v1 domain rather than a result about search, planning headroom here is zero
by construction, and no procedure is claimed better than another. A domain where they
separate is what the interacting-goal microbenchmark is for.

## Run reports and telemetry sufficiency

`python -m ecora report <run-directory>` reads one recorded run and reports it in four
sections that are never merged: service outcomes per service with each requirement's
verdict, coordination stability, missing evidence, and privileged-information results
(`--json` for the structured form). Everything is read from the artifact store; reopening
the store with no model in reach reproduces the report byte for byte, and a test asserts
it. Privilege follows lineage, so a verdict resting on truth anywhere upstream is labelled
as a privileged reference in the service section itself, not only in the fourth. An
inconclusive requirement is listed as missing evidence and is never tallied as met.

`python -m ecora sufficiency <directory>` runs the comparison stage-arms.md and the
telemetry contract prescribe. Planning, resolution, action, result and assurance are
identical across every cell, and a test asserts that by provider and configuration hash.
Diagnosis varies between the contract-limited arm (the study's rules over the telemetry
projection) and the privileged arm (the same rules over exact current truth of the same
signals). Observation subsets are declared leave-one-out: the full projection, then each
expected signal withheld once. All twelve cells run under one study hash.

The harness scores every diagnosis against ground truth at each decision instant through a
logged port of its own, whose reads go to no provider; the contract arms' datasets stay
`contract_only` with it running. Identifiability is computed from the rule inventory rather
than inferred from a run: a label whose every derivation needs a withheld signal is lost to
every diagnoser on that subset, privileged or not. Tests assert that no arm misses a label
outside that set and that none concludes anything false.

On `s1-degraded-primary` revision 3, four epochs at 0.5 s: a cell-edge site in a busy cell
(ADR-30), with the LTE leg read through the measured rate table. The figure has moved twice
and each move is explained by what S1 declared. Revision 1 (one-way SCADA, nominal rate)
measured 0.381; revision 2 (SCADA as a round trip over a leg its nominal table made nearly
silent) measured 0.429; revision 3, where the leg is degraded but still delivering,
measures 0.143 for SCADA and 0.143 for AMI. A site stuck on a slow leg loses less, over a
short run, than one stuck on a dead one. Every other finding was unchanged by each revision.

| Subset withheld | Access headroom | Subset cost (within-age delivery, SCADA and AMI) | Applied actions |
| --- | --- | --- | --- |
| none | 0 | 0 | 1 |
| `site-1/alternative/path_probe` | 0 | 0.143 | 0 |
| `path_state` | 0 | 0 | 4 |
| any other single signal | 0 | 0 | 1 |

Access headroom is zero on every subset: the projection relays fresh values each epoch, so
exact truth of the same signals concludes and delivers the same. Staleness is where a gap
opens, which the diagnosis Oracle tests exercise separately. Withholding the alternative
probe makes `alternative_viable` unidentifiable, so the switch has no precondition
evidence, and neither arm can make it. Withholding path state costs no service but
triples the actions applied, because a planner that cannot see the current path reapplies
the switch every epoch.

These are findings about this rule inventory, this finite model and these states. They do
not establish that the observation contract is sufficient in general, and the privileged
rows are references rather than deployable evidence.

## ns-3 build and model manifest

`software/simulator/build-ns3.sh` builds ns-3 3.48 (ADR-28) under the declaration in
`software/simulator/ns3-build.json`. It was exercised on Ubuntu 24.04 under WSL2 with GCC
13.3.0, CMake 3.28.3 and Ninja, `release` profile (`-O3 -DNDEBUG`, native optimisation
off, asserts on, logs off). Configure resolved the eight declared modules into nineteen.

Reproducibility was checked rather than assumed. Two independently obtained copies of the
archive had the same SHA-256. A second build into a separate root, downloading and
extracting afresh, produced a byte-identical attribute dump (504 types, 1067 attributes)
and identical build facts. Both builds ran on the same host, so this establishes that the
procedure reproduces, not that another host would. The first dump was *not* reproducible: one
pointer-valued default, `PhasedArrayModel::AntennaElement`, serialised as a process
address. The exporter now records the pointed-to type, and three consecutive runs agree.

Refusals were exercised: a truncated archive is refused with its actual checksum, and a
source tree the script did not extract is refused before anything is built. The
committed manifest's `model_hash` is `64b9a0f7904d...`; tests re-derive both hashes, check
the manifest against the current declaration and exporter source, and require the RLC,
HARQ and selected-component settings v1 scope names.

## Simulator process: first observations

`ecora-sim` answered `configure`, `advance` and `cohorts` for all six scenarios, and
refused a backwards clock and an unimplemented request with their reasons. Every response
carried the build identity the manifest records, recomputed independently by
`ecora.ns3build`. The resolved LTE carrier is 2.12 GHz downlink and 1.93 GHz uplink,
derived from the declared EARFCNs, and both spectrum channels carry the Friis spectrum
model and the per-site impairment model.

Uncontrolled, eight simulated seconds, cohorts over generation in the first seven:

| Scenario | SCADA on time / generated | Lost | Pending | Host time |
| --- | --- | --- | --- | --- |
| S0 nominal | 70 / 71 | 0 | 1 | 0.11 s |
| S1 radio loss 50 dB at 1 s | 9 / 71 | 0 | 62 | 0.09 s |
| S2 radio loss 200 dB at 1 s | 9 / 71 | 18 | 44 | 0.05 s |
| S5 narrow egress | 1 / 71, 68 late | 0 | 2 | 0.10 s |

**These are observations, not calibration.** The nominal 50 dB was expected to degrade the
LTE leg to roughly the finite world's 32 kbit/s; in ns-3 it effectively silences it, and
transactions stay pending in the radio's buffers. The finite world's loss-to-rate table
therefore does not yet describe the simulator, which is the gap B21 exists to close. S5 is
harsher in ns-3 because the envelope and UDP/IP headers add bytes the finite world does not
count. The one pending S0 transaction is the one sent before the UE attached, which the
UE discards silently and which is therefore not attributed as a loss.

## LTE rate calibration

`python -m ecora calibrate-lte --apply` measured the LTE leg in the simulator and wrote the
result into every scenario's `logical` block, which now cites the dataset
`data/simulator/lte-rate-calibration.json` by hash. The measurement is saturation goodput of
application payload, over a window after attach, built by the simulator's own LTE code,
and tied to the manifest's build identity. 567 points: 23 losses in both directions on the
unloaded cell, and 11 losses uplink under each of 13 competitor counts, three runs each,
median taken. Away from the cliffs every run agreed exactly; two points differed across
runs, both past a cliff, where the error model occasionally decodes a stray block.

What it established, with the LTE leg the scenarios declare:

- **Loss alone is binary for the v1 workload.** Uplink capacity falls smoothly from
  17.3 Mbit/s to 627 kbit/s at 48 dB and to nothing at 49.75 dB. The downlink holds to
  about 53 dB. SCADA was on time at every loss up to 49.5 dB and never at 49.75 dB.
- **Load alone leaves a site plenty.** At 0 dB a saturating site's share falls roughly as
  capacity over the number of UEs, to 461 kbit/s at 35 competitors; at 40 the cell stops
  admitting UEs, so 35 is the model's declared range.
- **Degradation needs both, and demand near the share.** Proportional fairness serves a
  light site promptly, so a site well under its share is unharmed. At 48 dB with 5
  competitors the share is 68 kbit/s; with AMI every 100 ms the site asks for about 82, and
  SCADA runs late rather than stopping. That is what S1, S3 and S4 now declare (ADR-30).

With the measured table both worlds agree on every LTE condition, over eight seconds,
SCADA on time out of 56 generated after 1.5 s:

| Scenario | Finite world | Simulator |
| --- | --- | --- |
| S0 nominal | 56 | 56 |
| S1 degraded | 2, 51 late | 1, 48 late |
| S2 silent | 0 | 0 |
| S3 transient | 22, 34 late | 18, 38 late |
| S4 no alternative | 2, 51 late | 1, 48 late |
| S5 narrow egress | 15, 41 late | 0, 54 late |

S5 still differs because the finite world does not count envelope and header bytes, a
declared simplification that this calibration does not address. The table is a saturation
share: below the share it overstates harm, and between measured points it takes the more
favourable neighbour. The logical delay of the LTE leg is still nominal.

The arbitration study's `degraded_primary` threshold was re-set from 30 ms to 25 ms, against
the calibrated leg's 20 ms unimpaired and 27.5 ms degraded probe round trip; at 30 ms the
rule could no longer fire, which is the unreachable-mechanism shape recorded in the backlog.

## Simulator adapter

`ecora.simulator` drives the simulator from Windows through WSL. For every scenario the
same file built the finite world, which `verify_world` accepted, and the simulated one,
whose `configure` report `verify_simulated` accepted field by field. Across the process
boundary, two runs under one seed returned identical cohorts, every cohort's generated
count equalled delivered on time, late, lost and pending combined, a backwards clock and an
unbuilt request were refused with their codes, and the world answered the next request
normally afterwards. The first start on a host costs about 5 s while WSL starts; later ones
take about 0.15 s per scenario including eight simulated seconds.

The protocol rules are tested against an in-memory stub as well, so they are exercised on
hosts with no build: a response from another build, a response to another request and a
silent process are each refused. On a host without a build the five tests that need one
skip with that reason.

`python -m ecora demo .ecora-runs/example` runs the same invocation sequence for two
frozen treatment bindings. Both produce valid DiagnosisRecord payloads with different
synthetic fixture labels. Each treatment yields three committed datasets, three messages
and ten journal events. `python -m ecora verify .ecora-runs/example/reference` successfully
reopens and verifies the corresponding store. Use fresh demo paths on each execution.

This is contract and integration evidence. It is not evidence for network behaviour,
diagnostic accuracy, formal safety, optimal planning, convergence, real actuator effects,
simulator replay or power-loss durability. Those claims retain their separate acceptance
obligations. See the [package limits](README.md#persistence-limits-and-verification).
