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
expected signal withheld once. All eighteen cells run under one study hash.

The harness scores every diagnosis against ground truth at each decision instant through a
logged port of its own, whose reads go to no provider; the contract arms' datasets stay
`contract_only` with it running. Identifiability is computed from the rule inventory rather
than inferred from a run: a label whose every derivation needs a withheld signal is lost to
every diagnoser on that subset, privileged or not. Tests assert that no arm misses a label
outside that set and that none concludes anything false.

On `s1-degraded-primary` revision 4, four epochs at 0.5 s: a cell-edge site in a busy cell
(ADR-30), the LTE leg read through the measured rate table, and probes as real traffic
(B22a). The figure has moved three times and each move is explained. Revision 1 (one-way
SCADA, nominal rate) measured 0.381; revision 2 (SCADA as a round trip over a leg its
nominal table made nearly silent) 0.429; revision 3 (degraded but still delivering) 0.143.
With realistic probes no evidence exists at the first decision epoch, in either world, so
the switch comes one epoch later in both arms: 0.190 for SCADA and 0.143 for AMI, and
withholding path state now costs three applications rather than four. Access headroom is
zero on every subset throughout. With B22c and B23a the projection gained three signals and
so three subsets; the figures above did not move.

| Subset withheld | Access headroom | Subset cost (within-age delivery, SCADA / AMI) | Applied actions |
| --- | --- | --- | --- |
| none | 0 | 0 | 1 |
| `site-1/alternative/path_probe` | 0 | 0.190 / 0.143 | 0 |
| `site-1/selected_path/actuator_version` | 0 | 0.190 / 0.143 | 0 |
| `path_state` | 0 | 0 | 3 |
| any other single signal | 0 | 0 | 1 |

Access headroom is zero on every subset: the projection relays fresh values each epoch, so
exact truth of the same signals concludes and delivers the same. Staleness is where a gap
opens, which the diagnosis Oracle tests exercise separately. Withholding the alternative
probe makes `alternative_viable` unidentifiable, so the switch has no precondition
evidence, and neither arm can make it. Withholding path state costs no service but
triples the actions applied, because a planner that cannot see the current path reapplies
the switch every epoch. Withholding the path version costs the same service as withholding
the alternative probe for a different reason: diagnosis is exact, but resolution will not
write a version it was not shown. Withholding `scada_response` loses its two labels and no
service, because no goal reads them.

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

## Shared bottleneck

`python -m ecora bottleneck-pilot` demonstrates and measures the contention v1-scope places
at the shared egress, in both worlds, uncontrolled, and writes the grid to
`data/simulator/bottleneck-pilot.json`. The workload is fixed at the nominal scenario with
AMI every 100 ms, so the two classes offer comparable load. The egress capacity is swept and
each capacity runs twice: AMI released at the normal pacing profile, and throttled to the
minimum. Both worlds instrument the egress independently of their ledgers: per class,
arrivals, departures, drops and queueing delay (arrival to start of transmission), and the
queue's occupancy over time. One definitional difference is stated rather than hidden: ns-3
removes the datagram on the wire from the queue, and the finite world counts it until its
service ends. The LTE leg's queue in ns-3 is the RLC buffer, which exposes no trace, so it
is reported as not instrumented.

SCADA transactions on time out of 56, finite world / simulator:

| Egress | AMI normal | AMI throttled | SCADA mean wait at the egress, AMI normal / throttled |
| --- | --- | --- | --- |
| 48 kbit/s | 0 / 0 | 56 / 5 | 1.63 / 0.02 s; 1.87 / 0.19 s |
| 64 kbit/s | 0 / 0 | 56 / 56 | 0.87 / 0.003 s; 1.20 / 0.005 s |
| 80 kbit/s | 53 / 0 | 56 / 56 | 0.09 / 0.002 s; 0.52 / 0.003 s |
| 96 kbit/s and above | 56 / 56 | 56 / 56 | under 1 ms |

What it establishes:

- **The bottleneck is shared, and it is the egress.** In the contended band, 56 to
  80 kbit/s in the simulator and 48 to 80 in the finite world, SCADA fails every deadline
  with AMI at normal pacing and meets every one with AMI throttled. The difference appears
  as SCADA's wait at the egress, one to two orders of magnitude longer with AMI competing,
  while the finite world's LTE leg never holds more than one datagram.
- **Both worlds agree where full service starts:** 96 kbit/s with AMI at normal. They
  differ on SCADA alone, 48 against 56 kbit/s, by the envelope and header bytes the finite
  world does not count.
- **Pacing is the lever that relieves it.** Throttling AMI never made SCADA worse at any
  capacity in either world.
- **S5 is overload, not contention.** Its egress, 44 kbit/s, is below what SCADA needs on
  its own in both worlds, so no pacing decision can save it: throttled, the finite world
  reaches 24 of 56 and the simulator none. It is kept as deliberate overload and its note
  now says so.
- **S9 adds contention at the egress to the set.** A 64 kbit/s egress with AMI every
  100 ms and both legs unimpaired: SCADA 0 of 56 on time at normal pacing and 56 of 56
  throttled, in both worlds, with SCADA's egress wait falling from 0.87 s (finite) and
  1.20 s (simulator) to a few milliseconds. With S1, S3 and S4, where the site's services
  contend for its LTE share, the set now holds contention at both places v1-scope names.

A light workload below the contended band never queues, which is why the pilot fixes AMI at
100 ms: a capacity label is only meaningful against the demand it was measured under.

## Simulator observations

`observe` makes the decision pipeline run over the simulator unchanged. Batches from every
scenario at several instants pass the same telemetry contract as the finite world's, only
granted signals are exported, and an unheld signal or subject is refused with its code. On
S2 every treatment completes over ns-3 evidence; the diagnosing treatments conclude what the
finite world concludes before its switch, the planner decides to switch, and the action
stage records the simulator's refusal of `apply` as `rejected` rather than stopping the run.

The two worlds' evidence at the same instants, uncontrolled:

| Signal | Finite world | Simulator |
| --- | --- | --- |
| Path state, pacing | as declared | identical |
| LTE probe, unimpaired | 20.0 ms | 17.0 ms |
| Alternative probe | 20.5 ms | 21.0 ms |
| Site queue, S1 at 2 s and 4 s | 2048, 5632 bytes | ~2932, ~8580 bytes (derived) |
| LTE probe, S1 degraded | 27.5 ms | missing: timed out behind the backlog |
| LTE probe, S2 in the 0.5 s after the leg goes silent | missing at once | last acknowledgement still valid |

The table above was measured before B22a, when the finite probe was idealised: computed
from the leg's rate, so it neither waited behind queued traffic nor lagged as evidence. The
simulator's probe does both, which is what a real probe does. B22a made the finite probe
real traffic with the simulator's schedule, timeout and validity: sent every 0.2 s from
0.2 s, echoed at the far end of the leg, lost after 0.15 s, evidence for 0.5 s. With the
same rules over each world's own evidence, diagnoses now agree exactly at every instant
checked, including S2's transition, where both still hold the last acknowledgement.

What that cost and what it kept:

- **No probe evidence exists at the first instant**, in either world, so nothing is
  switched on no evidence at t = 0. Tests that assumed otherwise now observe from 0.5 s.
- **The arbitration study stays reachable, as a window.** Its equal-authority conflict
  needs a leg slow but still answering, which holds from when the load arrives until the
  backlog makes the probe time out: 1.2 to 2.0 s in the finite world and 1.4 to 1.7 s in
  the simulator, in S1, S3 and S4. The priority inhibition holds from 0.3 s. A test now
  requires the window rather than one instant, so a window that closed would fail loudly.
- **The bottleneck pilot's conclusions are unchanged**: probes never cross the egress, and
  no SCADA outcome or egress wait moved by more than 0.1 ms.

One difference remains, recorded for follow-up:

- **The simulator's site queue is larger** for the envelope and header bytes the finite
  world does not count.
- **No site signal shows contention at the shared egress.** In S9 the site's queue is
  empty in both worlds; the backlog is central. The v1 catalogue's remote delivery
  summaries are the signal that would reveal it, and neither world exports them yet.

## Closing the loop in the simulator

The simulator applies `select_path` and `set_ami_pacing` as the finite world does: for the
same commands at the same instant the two worlds return the same `(applied, reason)` and
the same actuator readback, including every refusal. Over twelve decision epochs, SCADA on
time among transactions generated from 1 to 5 s:

| Scenario | Treatment | Final path, version | Finite world | Simulator |
| --- | --- | --- | --- | --- |
| S2 silent | Null baseline | lte, 0 | 0 of 40 | 0 of 41 |
| S2 silent | planner, eco | alternative, 1 | 40 of 40 | 41 of 41 |
| S1 degraded | Null baseline | lte, 0 | 5 of 40 | 5 of 41 |
| S1 degraded | planner, eco | alternative, 1 | 40 of 40 | 41 of 41 |

The planner and eco treatments switch once, at the first epoch with probe evidence; the
blackboard treatment, planning with the Null planner, reapplies its switch every epoch,
reaching version 12 in both worlds, which is the churn B32's instrumentation measures. The
generated counts differ by one because the finite world's floating-point generation times
drift across the window's closing edge.

Receipts now state the actuator's readback as the resulting state. The action provider had
read `truth()` for it, which is the privileged channel; a test makes `truth()` raise and
runs the loop to show no receipt needs it.

**State versions.** The contract's compare-and-swap is enforced in both worlds. Each
actuator's version is exported as `actuator_version`, subject `site/selected_path` or
`site/pacing_profile`; the harness carries the versions it relayed into the planning
problem, planners copy them into their proposals, and a resolver writes the version of the
actuator each step targets, abstaining when it was not shown one. Both worlds refuse a
command with no version (`missing_version`) or an outdated one (`stale_version`) and change
nothing; a second write planned on the version the first consumed is stale, and the two
actuators version independently. The same commands receive the same answers in both worlds.

Under the synchronous barrier no run reached `stale_version`: evidence was observed and the
command applied at the same instant, and resolution admits one write per target, so the
version planned against was always current. It stays unreachable under any latency shorter
than the decision period, including the baseline's 10 ms, because every command lands
before the next decision reads the version. It is reached once latency exceeds the period;
see [Control latency](#control-latency).

## Delivery summaries

Both worlds export `scada_response`, the centre's delivery summary for a site: the mean
response time of its SCADA transactions completed in the window ending 10 ms ago, and
missing, not zero, when none completed. It separates three conditions the site's own queue
cannot, at 3 s, finite world / simulator:

| Scenario | Site queue | SCADA response |
| --- | --- | --- |
| S0 nominal | empty | 43 / 44 ms |
| S9 contended egress | empty | 677 / 905 ms |
| S1 degraded LTE | 4.1 / 5.8 KB | 422 / 499 ms |
| S2 silent LTE | growing | missing / missing |

S9's contention is invisible to the queue and plain in the summary. Every study's
projection now expects it, and two contradicting rules read it: `overdue_scada` at or above
the SCADA deadline (0.25 s) and `timely_scada` below it, with a privileged truth projection
for the Oracle arm. No goal consumes either label yet, so the rules inform diagnosis without
changing a plan; a sufficiency test shows the full run concludes them and that withholding
the summary loses exactly those labels.

## Impairment and restoration hooks

Disturbances are the scenario's, not the controller's. Both worlds apply the declared
schedule themselves and keep a ledger of what they applied: each disturbance, the time it
took effect and the leg's condition read back afterwards. In the simulator that readback
comes from the model objects (the loss the propagation model applies between site and
cell, the competing terminals running, the point-to-point device's rate and error model),
not from the declaration. `verify_impairments` folds the expected condition from the
scenario alone and refuses a ledger with an impairment missing, late, out of order or
without effect. Both worlds pass it on all seven scenarios, and their read-back conditions
agree entry by entry.

The ledger is the hook's own account, so the effect is also measured through traffic. On
uncontrolled S3, SCADA on time, finite world / simulator:

| Window | Condition | On time |
| --- | --- | --- |
| 0–1 s | 48 dB, cell idle | 11 of 11 / 10 of 11 |
| 2–5 s | 48 dB, 5 competing terminals | 0 of 31 / 0 of 31 |
| 6–11 s | restored at 5.0 s | 50 of 50 / 53 of 53 |

The simulator drains its backlog more slowly after restoration: in the second after 5.0 s it
delivers 6 of 11 on time where the finite world delivers all ten, so recovery is scored
from 6 s. Its one first-second shortfall is a transaction still pending at 14 s, before any
disturbance; its cause is not established here.

The hooks are held apart from controller authority, and tests show it in both worlds:
commands naming a leg condition or a restoration are refused as unsupported operators and
leave the ledger unchanged, no observation exports a leg condition (the simulator refuses
the request as an unsupported signal), and no truth projection carries one. The schedule is
fixed at configure; a hook the harness can call mid-run is needed only for branching (B55)
and is not built.

## Control latency

Each study declares its decision period and control latency (`control`), and the admitted
study manifest freezes them, so they are fixed across every treatment and hashed into
every run's scope. The harness observes and decides at each epoch, then dispatches the
resulting command after the latency while the world runs on. The action stage's watermark
is the dispatch instant, so the boundary checks the command's expiry and not-before time
there, and the actuator checks its version against the state the world has reached by
then. Where a dispatch and an observation fall at the same instant, the dispatch goes
first. A receipt cites the first observation after its dispatch. Zero latency is the
synchronous barrier, which runs and reports as idealised.

Host time spent deciding is measured per epoch and printed beside the simulated latency.
It is never added to the latency and never enters the evidence: two runs of the same
configuration end at the same journal head while their host times differ. About 0.23 s per
epoch on this host, finite world, which includes the store's writes.

Receipts on S1, planner and Null planner (blackboard), six epochs at 0.5 s. The finite
world and the simulator produce these identically, receipt for receipt:

| Study | Latency | Planner | Null planner |
| --- | --- | --- | --- |
| baseline | 10 ms | applied at 0.51 s | applied at every epoch, 0.01 s to 2.51 s |
| delayed-control | 0.6 s | applied at 1.1 s, then `stale_version` | applied, `stale_version`, applied, `stale_version`, applied |

Under `delayed-control` the planner decides the switch at 0.5 s and, since that command has
not landed, again at 1.0 s against the same version. The first lands at 1.1 s and the
second is refused at 1.6 s, changing nothing. The Null planner's switch, which under
the barrier was reapplied every epoch, now alternates. Compare-and-swap still prevents
lost updates, not churn; at this latency it happens to refuse every second write. The last
epoch's decision is due after the run closes, so it never reaches the actuator, and the
showcase reports it as in flight.

What the dispatch instant checks is reachable:

- **Expiry at dispatch.** The study refuses a latency at or beyond any command validity,
  since every command would expire on arrival. Overridden past it (1.2 s against a 1 s
  validity), the boundary rejects each delivery as a stale command and the world does not move.
- **Version at dispatch.** Reached as above, in both worlds.
- **Continuation.** Regeneration reapplies each recorded command at its recorded dispatch
  instant, under the same tie rule, and verifies under 10 ms latency at every branch
  point. A branch is refused while a command decided in its prefix is still in flight: the
  branch would otherwise have to carry the old controller's command or drop it, and either
  changes the world it claims to share.

Nominal values, uncalibrated. The baseline's 10 ms is the register's `controller_delay_s`.
Its 0.5 s period is the showcase's, not the register's 0.100 s, which B41 decides from
measured cost. `delayed-control`'s 0.6 s is chosen to reach a mechanism, not measured. No
control latency is claimed for any real controller.

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
