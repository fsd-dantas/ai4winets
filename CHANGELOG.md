# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project follows
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added

- **Cohort extraction and requirement evaluation** in `software/ecora/assessment.py`, the
  Proposed arms for the last two stages. Every run previously ended inconclusive by
  construction, because nothing in the pipeline could reach a verdict; a run now returns
  `met` for the declared delivery requirement with the ratio and population it rests on.
  Neither provider will be more confident than its evidence: a ratio without a population
  is unknown rather than perfect, and a requirement is inconclusive when its measurement
  is missing, unmeasured, computed over an empty population, or when outstanding demand
  exceeds the declared missingness limit. Requirements and comparators are frozen in the
  binding, so substituting the evaluator cannot change what passing means.
- **The action Oracle as a declared equivalence** with the model adapter rather than a
  separate implementation, which is what stage-arms.md asks for where the integration is
  direct: a fabricated difference between two arms would be measured as though it were real.
- **Exact references for planning and resolution** in `software/ecora/exact.py`, kept
  apart from the privileged ones because the distinction matters: an exact reference reads
  no more than the arm it references, so Proposed-minus-exact is an algorithmic gap while
  contract-limited-minus-privileged is an information gap, and reporting one as the other
  would answer a question nobody asked. A plan is called optimal only when its cost matches
  the enumerated table it is checked against, and a reference that cannot finish returns
  unknown with its bound and no certificate.
- **A finding about the experimental design.** The v1 configuration domain has six
  reachable states with every goal one operator away, so uniform cost, A* and GPS return
  the same optimal cost on every problem in it. Planning headroom is therefore zero here
  by construction rather than by measurement, and the planning factor cannot discriminate
  over this domain. S8's interacting-goal microbenchmark is where it can, which is what
  that scenario is for; a test records the limitation so it stays visible.
- **The diagnosis Oracle**, sharing the rule inventory and the inference with the
  Proposed arm so that the gap between them reads as a difference in information rather
  than two implementations disagreeing. It diagnoses only what the model establishes: an
  unmodelled physical cause has no ground truth to read, so the gap it measures is bounded
  by what the world represents.
- **A privilege leak closed.** Lineage was harvested from the payload, which works for a
  telemetry batch and silently fails for a diagnosis, a plan or a receipt, none of which
  carry observations. A provider holding truth access now declares what it read and the
  boundary taints the invocation with it, so the label follows the access rather than the
  shape of the output; one that succeeds while declaring no read is refused.
- **The restricted, logged truth interface** in `software/ecora/truth.py`, and the
  telemetry Oracle that uses it. Access is capability-scoped, so holding one truth grant
  is not permission to read anything else; it serves the current instant only, refusing a
  later or an earlier one, so neither the future nor a stale value is reachable; and every
  read is logged and returns a reference that travels with what it produces, so an
  Oracle-derived value keeps its lineage through every stage that touches it. The port
  projects current state and holds no calendar, schedule or random stream, so there is
  nothing in it to read a future from. Truth is granted separately from observation and
  actuation, and an ordinary binding that holds a truth capability is refused at admission.
  Every stage now has a Null and a Proposed arm, and telemetry has an Oracle.
- **Coordination and reasoning measurement** in `software/ecora/metrics.py`: reversals,
  repeated applications, deadlocked epochs, coordination starvation, expert activations,
  search expansions, plan size, claim churn, mark reads, writes and bytes, and a stability
  verdict over the declared window. Everything is read from recorded evidence, so a
  measurement can be recomputed from stored artifacts and none can depend on something the
  controller was never allowed to see. Stability consults no service outcome by design,
  and what the evidence cannot support is reported as unknown rather than approximated.
  The showcase now prints the measured behaviour beside each treatment.
- **`pacing_profile` in the versioned telemetry catalog**, an actuator readback of the
  same kind as `path_state`, so an applied `set_ami_pacing` command can cite an
  observation of its application rather than assert one. A receipt now cites the readback
  of the actuator it moved. The rationale is recorded in the telemetry contract, its
  normative owner; the change widens the catalog and invalidates no existing record.
- **Pacing corrected to a release gate.** It had been implemented as a reduction of the
  service rate, which left a paced reading at the head of a shared queue holding SCADA up
  behind it; tightening the AMI profile therefore made SCADA service worse and drove drops
  from 19 to 443. v1-scope.md specifies that pacing governs gateway release. It now holds
  readings at the gateway: SCADA delivery is unaffected by the AMI profile, AMI delivery
  scales with it, nothing is dropped, and withheld demand is reported as held.
- **Path probes**, which make leg reachability observable instead of assumed. The model
  answers a probe on a serving leg and stays silent on one whose service has been taken
  away; each leg is its own subject, so probing one is not permission to probe the other.
  A rule concludes viability only from a probe that came back, so an unknown precondition
  prohibits the switch and a planner cannot move onto a leg it has no evidence it can
  reach. The Proposed planner and the eco resolver are now bound into the chain, which
  runs seven treatments each a single binding apart.
- **Eco-problem solving** in `software/ecora/eco.py`: per-agent local satisfaction with
  differentiated interpretation, an environmental mark substrate, and four anti-collision
  mechanisms (expiring marks, randomised backoff, local reservation, yield with aging).
  Two services reading the same signal reach different conclusions, which is the design's
  intent rather than an inconvenience, and satisfaction stays a vector of predicates
  because collapsing it into a score would need declared weights and a sensitivity
  analysis. The substrate stores and exposes marks without choosing an allocation, and its
  read API enforces local scope; its reads, writes and bytes are reported as ideal local
  shared memory and explicitly not as network overhead. Backoff draws are derived from an
  agent's own identity, so they are agent-specific and reproducible without a shared
  generator whose position would depend on how often other agents consulted it.
- **Symbolic core and three planners** in `software/ecora/symbolic.py` and
  `software/ecora/planning.py`: one state projection, operator catalog and plan validator,
  searched by forward uniform cost (the STRIPS baseline), GPS means-ends analysis and A*.
  They share the representation, costs and validator, so a difference between them is a
  difference in search. An unknown precondition prohibits the edge, so a planner cannot
  switch onto a leg it has no evidence it can reach; operator effects are configuration
  and never predicted service; and only the validator may say a goal was achieved. A*
  starts from a zero heuristic, which makes it a correctness reference against uniform
  cost rather than a claim about heuristics. A bounded search that finds nothing says so,
  and does not report infeasibility.
- **Rule-based diagnosis in two organisations** in `software/ecora/experts.py`: a single
  engine evaluating a versioned rule collection to a fixed point, and one expert per rule
  scheduled by a blackboard controller over a revisioned board. They share the rule
  inventory, the conflict policy and the evidence snapshot, and differ only in how the
  work is organised, which is what makes them comparable. Support is categorical: a
  conclusion is supported, contradicted or unknown, with no numeric confidence attached,
  because a score without a calibration procedure would be a probability in costume. A
  rule whose inputs are absent is unknown and never false. Contradictions are settled by
  declared priority and recorded as inhibited; equal authority leaves the conflict
  unresolved rather than decided arbitrarily. An exhausted activation budget is a typed
  refusal, not a silent truncation.
- **Proposed telemetry provider** in `software/ecora/telemetry.py`: contract-constrained
  normalisation, quality assessment and local projection onto one site's declared view. It
  never invents a value; an expected signal that is absent, or older than the declared
  freshness bound, is relayed as an explicit unknown carrying its reason and lowers
  declared completeness. It cannot report the absence of a signal it holds no capability
  to observe, and a projection expecting one is refused at configuration. Nothing from
  another site reaches a local projection, whatever the adapter offered.
- **`ecora showcase`**: runs five treatments over one frozen study, each differing from
  the previous one in a single stage binding, and closes with the RQ-E comparison between
  the two expert organisations. It prints the sensed and relayed signal counts,
  the applied actions, the resulting path, the assurance verdict, the provenance of the
  claim and a re-read integrity check. It completes in about three seconds and is covered
  by a test, because it is meant to be run in front of people.
- **Verified simulator continuation** in `software/ecora/runner.py`: a recorded run's
  causal prefix is regenerated under the recorded configuration and the commands that run
  actually applied, then verified against the observations it ingested before anything may
  branch from it. An unverified prefix is not a branch point. A branch is a new run with
  its own identity that produces evidence only from the branch point onward, so an
  action-changing replay generates its own subsequent outcomes instead of borrowing the
  recorded ones. Component substitution re-runs a stage on its recorded inputs.
- **Failure-case coverage** for the cases the milestone declares: missing observations,
  stale commands, conflicting proposals, unknown receipts and interrupted runs, with the
  module naming which test covers each.
- **Boundary playback and state restore**: a recorded stage output can be fed into the
  next stage without re-running its producer, and a provider can resume from a recorded
  state snapshot. Replayed payloads re-enter under the replaying run's scope carrying the
  run and invocation they were recorded in, so replayed evidence is attributable and never
  joined to the original run's lineage; privilege travels with what is replayed. Component
  substitution and closed-loop continuation are **refused**, not approximated: a mode that
  would license a counterfactual claim must not be served by machinery that cannot support
  one. See [interfaces](system/interfaces.md) for the mode table and its status column.
- **Run orchestration** in `software/ecora/runner.py`: a decision loop that advances the
  finite world, exports observations, drives all seven stages across the audited boundary,
  assembles the two built-from inputs and closes the run with a result and an assurance
  report. Named random streams (`arrivals`, `errors`, `disturbances`, `controller`) are
  independent generators, so controller draws cannot shift the exogenous inputs and two
  treatments face the same world. Runs are byte-reproducible from the frozen seed plan.
  A closed-loop treatment binds the action stage to the finite world and differs from the
  Null treatment in that one binding, so a paired comparison attributes the difference to
  the stage rather than to the orchestration around it.
- **Measured orchestration cost**: about 0.20 s per decision epoch, roughly 4.8 minutes
  per nominal run and 6.4 days for the 1935 base runs, against a declared 3-day budget.
  Recorded in [`software/validation.md`](software/validation.md) so the pilot that freezes
  the final budget starts from a measurement rather than an assumption.
- **Null providers for all seven stages** in `software/ecora/nulls.py`, implementing the
  policies declared in [stage arms](docs/ECoRA/stage-arms.md): omitted telemetry with
  explicit coverage, a first-candidate diagnosis labelled an unvalidated guess, a
  one-step first-feasible plan recorded as `unmet`, first-feasible resolution with the
  rest deferred, a suppressed action receipt, a receipt-only result and inconclusive
  assurance claims. An all-Null treatment runs every stage and produces a complete
  traceable report in which nothing was observed, decided or applied. A Null arm is a
  declared experimental baseline, not scaffolding; its policies are versioned so that
  changing one after seeing results is visible.
- **Finite reference model** in `software/ecora/model.py`: a deterministic discrete-event
  world of byte-service FIFO queues with finite limits, explicit propagation, two legs
  per site, a shared egress, SCADA and AMI obligations, AMI pacing, path selection and
  scheduled link disturbances. It exports contract-valid observations and frozen cohort
  counts, and keeps model truth separate from observable evidence. It is not an LTE
  emulator and carries no radio, protocol conformance or calibrated value; its declared
  simplifications are listed in the module.
- Executable ECoRA contract foundation in `software/ecora`: versioned schemas, immutable
  JSON records and dataset lineage, frozen-study admission, provider registry, audited
  boundary execution, capability/privilege enforcement, terminal outcomes and duplicate
  delivery/dispatch protection. Includes exported schemas, synthetic fixtures, installation
  metadata, CLI and property/invariant tests. Simulator and research providers remain planned.

- Selected ECoRA v1 research scope for synthetic wireless backhaul: workload obligations,
  label-free ordinary controller inputs, local agent and actuator boundaries, service/safety
  criteria, finite Oracle problems and preliminary parameter/resource budgets. The
  presentation and experimental questions are linked to the scope; runtime work remains planned.

- Repository charter in [`README.md`](README.md): purpose, research focus, the three exploratory research
  directions, the experimental philosophy and its four capability levels, reproducibility requirements, and
  the status and limitations that govern how any artifact here should be read.
- System contract stubs under [`system/`](system/): architecture, domain model, interfaces, control loop,
  assurance mode, and the telemetry and action contracts. Each declares `Status: planned` and states its
  intended scope; none carries a normative specification yet.
- Repository governance: [`LICENSE`](LICENSE), [`CITATION.cff`](CITATION.cff),
  [`CONTRIBUTING.md`](CONTRIBUTING.md) with the sanitisation checklist for open configurations and data, and
  [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
- `.gitignore` and `.gitattributes`, the latter pinning LF endings for files consumed by Linux tooling.
- Repository banner and social preview under `docs/assets/img/`, in light and dark variants with SVG sources,
  under the tagline *Assurance for critical wireless networks*. Rasters are rendered from the SVG sources with
  headless Chrome at the viewBox dimensions:
  `chrome --headless=new --disable-gpu --hide-scrollbars --screenshot=<out>.png --window-size=<w>,<h> file:///<in>.svg`
- Image policy in [`CONTRIBUTING.md`](CONTRIBUTING.md): explanatory figures in `docs/assets/img/`, evidence
  figures with the experiment that produced them.
- Statement of the open data and open configurations commitment in [`README.md`](README.md).
- First content under [`literature/`](literature/): citation conventions, `references.bib`, and a provenance
  note for the service assurance constraint recording that it is the standard statistical delay bound rather
  than a formulation original to this work. Entries carry a verification status, and the note lists the
  verification tasks still outstanding.

- **ECoRA — Expert Coordination, Resolution, and Assurance**: the architectural proposal under
  [`docs/ECoRA/`](docs/ECoRA/), covering the context map and bounded contexts, the domain ontology and its
  machine-readable vocabulary, the stage contracts, the decision methods, the nested-loop methodology with its
  study freeze contract, the experimental design and ablation matrix, and the recorded architectural
  decisions. Every capability it describes is declared **planned**.
- The ECoRA package presents the framework as a single instrumented pipeline: the two-loop separation,
  Coordination and Resolution as cross-cutting concerns, the Null/Proposed/Oracle ablation arms, and an
  explicit statement that no architectural novelty is claimed.

### Changed

- `StudyManifest` gains a required study-level `assembly` block that freezes what the
  assembled stage inputs contain: planning goals, operator catalog version, action costs,
  budgets and horizon, and the cohort identities, generation windows and deadlines. An
  assembled input departing from it is rejected at the boundary; only run-derived parts —
  predicates, and a cohort's measured counts — stay free. It is study-level rather than
  per treatment, so varying an assembly parameter starts a new study instead of becoming
  an undeclared factor beside the arms being compared. This adds a required field to a
  record type; no frozen study exists yet, so the contract stays at schema version 1.
- Stage inputs that the interface defines as **built from** upstream evidence — a
  `PlanningProblem` from a `DiagnosisRecord`, a `ResultInput` from receipts and a cohort
  specification — are assembled by a separate logged harness invocation rather than routed
  as the previous stage's raw output. That construction carries goal and cohort selection,
  which a study holds fixed across a stage's Null, Proposed and Oracle arms, so it cannot
  sit inside the provider being compared. A record the next stage cannot consume is now
  addressed to `sink` and retained as evidence. One test drives all seven stages.
- An invocation is marked delivered when a single consumer has received its whole output
  dataset. Delivery was previously pooled across consumers, which would report completion
  when no one consumer held all of it.
- `README.md` drops the *Candidate Research Directions* section; it prescribed a template
  under a `research-directions/` directory that does not exist. The three directions remain
  in *Research Focus*, which now states the criteria each is weighed against.
- Spelling normalised to `artifact` throughout.
- The quick start moved from `README.md` into [`docs/ECoRA/README.md`](docs/ECoRA/README.md), where the
  reading order and the eventual Python and ns-3 environments belong to the framework they describe.
  `README.md` points to that quick start; it now distinguishes the executable contract
  foundation from the planned simulator and research methods.
- `README.md` states what the repository is and guarantees, rather than instructing contributors. *Experimental
  philosophy* and *Reproducibility and scientific claims* merged into **Evidence and Reproducibility**; the
  metric list and the hold-conditions-fixed rule were removed in favour of the framework documents that make
  them binding, and the material duplicating [`CONTRIBUTING.md`](CONTRIBUTING.md) now points to it instead.
- `README.md` is scoped to the repository rather than to one framework. The ECoRA exposition moved to
  [`docs/ECoRA/README.md`](docs/ECoRA/README.md), which now carries the framework-element and arm tables and
  the statement that every method in it is a baseline. In its place `README.md` carries an **experiment
  index**: the studies this repository intends to run, the framework each is designed under, its status, and a
  link to its design. Every entry is declared planned; `experiments/` is empty.
- Scenarios are data. `scenarios/` holds six declared worlds as JSON, and
  [`software/ecora/scenario.py`](software/ecora/scenario.py) builds the finite model from one:
  topology declares the sites, legs and shared egress, flows declare the workloads, and
  disturbances declare the schedule. `python -m ecora showcase --scenario <id>` runs any of
  them, and changing a condition needs no change to code. `topology` and `disturbances` carry
  real shape in the schema, where they had been opaque objects.

  This closed a provenance defect. The frozen scenario had declared a topology nothing read
  while the world that ran was built from constants in the harness, so the scenario hash bound
  into every claim described conditions the claim did not come from. A run given a scenario is
  now refused unless the model matches it, and a run given only a model derives its scenario
  from that model, so neither direction can drift.
- A cohort names the service it counts. `cohort:ami` had been every packet generated in its
  window whatever its service, so an AMI delivery ratio was drawn from a mostly SCADA
  population. Scoring a second, per-service requirement still needs measurements keyed by
  service as well as metric, which is carried as B36; a scenario declares only what the
  assembled result stage can evaluate today.
- A means-ends treatment joins the showcase beside uniform-cost search, so GPS is
  demonstrated and not only tested. It differs from the uniform-cost arm in the planning
  binding alone. Both reach the same plan, and the showcase states why rather than leaving
  a duplicate row unexplained: over the v1 domain every goal is reachable within a few
  actions and no operator interacts with another, so every admissible procedure returns the
  optimal cost. Planning headroom here is zero by construction.
- The showcase no longer claims every verdict is inconclusive. That stopped being true when
  the assurance stage gained an arm that can reach one; the line is now derived from the
  results and names the population each verdict rests on.
- [`system/simulator-adapter.md`](system/simulator-adapter.md) settles how a simulator becomes a
  world the pipeline can drive. The decision that blocked simulator integration was
  architectural, not procedural: a build produces a library, not a world. The document states
  the seven calls any world must answer, selects a separate simulator process with a per-epoch
  request/response protocol over in-process bindings, and says why — the privilege boundary
  becomes a property of the wire rather than a naming convention, and branching by forking the
  simulator is impossible without a process to fork. It also records what it does not decide,
  including the per-epoch cost, which no budget may be frozen before measuring.

