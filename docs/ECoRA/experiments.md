# Experimental design and ablation

**Status: proposed experiments; no measurements or validated parameter values.** [Index](README.md)

The [methodology](methodology.md) separates within-run operational control from across-study research revision. Every comparative study freezes one scenario-set version and its evaluation protocol before measurement. The catalog below supplies candidate scenarios; it is not a mutable benchmark that can gain or lose cases between runs of the same study.

## Research questions and hypotheses

| ID | Question | Falsifiable hypothesis |
| --- | --- | --- |
| RQ-E | Does distributing rules across experts change results or cost? | With identical snapshots, rules and conflict policy, single and multi-expert diagnoses agree; orchestration cost can differ |
| RQ-P | How do planner strategies behave on shared problems? | A useful admissible heuristic reduces expansions relative to uniform-cost search without increasing optimal plan cost |
| RQ-G | How does means–ends planning handle interacting goals? | GPS effort and success depend on goal/operator ordering, exposed by interference cases |
| RQ-C | Can local eco-agents coordinate SCADA/AMI competition? | Marks and conflict handling improve feasible-case service/stability relative to uncoordinated local agents |
| RQ-F | Does priority protection cause starvation? | Removing the AMI minimum-service guard increases starvation under sustained pressure |
| RQ-A | Can assurance distinguish appearance from success? | Stable but unsatisfactory and insufficient-evidence runs receive distinct non-pass outcomes |
| RQ-H | Which stage has useful conditional headroom? | Paired Null/Proposed/Oracle substitutions separate contribution from remaining headroom under fixed downstream providers |
| RQ-T | How much assurance is reachable with the observation contract? | Specified ambiguous observation histories lose decision value relative to privileged current-state information under matched downstream methods |

These hypotheses may be rejected. No method is presumed universally superior.

## Staged environment

First use a small logical resource model to verify contracts and expose coordination behaviour. Then repeat applicable cases in ns-3 with identical workload definitions and an explicitly declared network abstraction.

The proposed ns-3 topology has synthetic SCADA and AMI endpoints at edge sites, a destination/application endpoint, an LTE path and an alternative abstract path. Both classes must share at least one measured bottleneck. Otherwise the run does not test competition.

SCADA uses identifiable request/response transactions. AMI uses separately identified periodic readings and optional declared bursts. Synthetic UDP payloads can model these workload roles without claiming SCADA or AMI protocol conformance.

If the adapter only permits site-level path switching, experiments must honour that scope. Per-class path selection is disabled until supported. Queue-local agents can still coordinate eligible pacing/defer actions once those actions are implemented.

## Scenario catalog

| ID | Condition and disturbance | Intended question | Expected assessment, not a promised result |
| --- | --- | --- | --- |
| S0 | Both classes comfortably below measured usable capacity | Does control avoid unnecessary churn? | Requirements may hold with no intervention |
| S1 | AMI burst during steady SCADA | Does coordination protect SCADA and drain AMI backlog? | Temporary AMI deferral followed by recovery if feasible |
| S2 | SCADA burst during sustained AMI | Are resource claims adapted and released? | Priority response without permanent AMI starvation |
| S3 | Temporary reduction of available path service | Does the system detect stress and recover after restoration? | Recovery with bounded side effects |
| S4 | Sustained demand beyond a declared feasible region | Is overload honestly reported? | Violation or degraded service, never an invented all-pass outcome |
| S5 | Competing simultaneous action proposals | Which anti-collision method avoids repeated conflicts? | Distinct conflict, retry and stability measurements |
| S6 | Delayed/missing observations and delayed/expired marks | Does partial information cause unsafe or ineffective decisions? | Inconclusive decisions and stale-action rejections are retained |
| S7 | Same demand from different initial allocations/agent states | Does self-organisation depend on initial conditions? | Basin and activation-order sensitivity |
| S8 | Interacting configuration goals in an enumerable symbolic model | Do planners undo earlier goals or exceed budgets? | Valid final plan or explicit bounded failure |

S3 requires independently verified impairment and restoration hooks. S6 requires explicit observation/communication delay modelling. S8 is a planner microbenchmark, not a wireless performance result.

Capacity classifications must use measured attainable service or a declared analytical bound with assumptions. Aggregate offered bitrate alone is insufficient when deadlines, directionality, overhead and bottleneck placement matter. A planner timeout is not evidence of physical infeasibility.

## Treatment matrix

These are within-arm method comparisons. Every row still binds all interfaces in [Stage arms](stage-arms.md); a blank or absent stage is invalid. The Null/Proposed/Oracle design below is the primary stage-ablation matrix.

| ID | Diagnosis | Planning/proposal | Resolution |
| --- | --- | --- | --- |
| B0 | Null first-candidate/abstention provider | Explicit no-op PlanProposal | Null deterministic resolver; action stage returns no-op receipt |
| B1 | Fixed service policy | Static priority policy where supported | Fixed arbitration |
| E1 | Single expert | Fixed rule-to-action mapping | Central arbitration |
| E2 | One-rule experts and blackboard | Same mapping as E1 | Same arbitration |
| P1 | Frozen common diagnosis | STRIPS operators plus uniform-cost search | Common central arbitration |
| P2 | Same diagnosis | GPS over same operators | Same arbitration |
| P3 | Same diagnosis | A* over same operators and costs | Same arbitration |
| C0 | Local dissatisfaction | Local actions | Null local first-feasible resolver with explicit empty mark view |
| C1 | Same local assessment | Same local actions | Eco coordination with selected mechanism |

E1/E2 isolate inference organisation. P1/P2/P3 isolate planning. C0/C1 isolate peer coordination. For end-to-end comparisons, compose explicitly named diagnosis/planning/resolution components in a treatment manifest. Do not attribute an end-to-end difference solely to one component when several change.

A central controller with global information is a useful reference but has an information advantage. Compare central and local controllers under matched information where possible, and label the unrestricted central reference separately. Match available actuators, goals, demand and service requirements.

## Declared factorial and confirmatory design

The four initial factors are telemetry, diagnosis, planning and resolution. Each has exactly the Null, Proposed and current-state Oracle levels defined in [Stage arms](stage-arms.md). Fix one provider/version for each level before execution. Hold action execution, result extraction, assurance generation and the independent study evaluator fixed. Do not include STRIPS/GPS/A*, expert organisation or multiple eco protocols as hidden extra Proposed levels.

| Phase | Frozen study scope | Configurations | Inferential scope |
| --- | --- | --- | --- |
| Factorial screen | Small, tractable scenario set with supported/certified Oracles | 3^4 = 81 | Preregistered main effects and interactions within this screening set |
| Full-set confirmation | Separately frozen full scenario set and fresh declared replications | All-Proposed plus Null and Oracle substitutions at each of four stages: 1 + 4 × 2 = 9 | Conditional paired effects around the all-Proposed configuration |
| Supplemental stage studies | Action/result/assurance arms, information-regime controls and within-arm method comparisons | Separately declared cells and replications | Only their named questions; not part of the 81-cell design by default |

The screening set and full set are different frozen studies; never expand one active study's scenario membership. Screening can guide the later manifest, which must be frozen before confirmation runs. Selected interaction checks carried to the full set add explicitly budgeted cells. Full-set one-factor-at-a-time results cannot establish the absence of interactions outside the screen.

Let S_screen and S_full be the numbers of scenarios and R_screen and R_full the independent replications per cell. The base run budget is **81 × S_screen × R_screen + 9 × S_full × R_full**. Add a separately itemised B_extra for supplementary cells, execution-failure reruns allowed by the protocol, and method comparisons. Estimate wall time, solver-memory limits and storage for all boundary datasets before launch. Cell counts are experimental design sizes, not calibrated runtime parameters.

The screen should include feasible contention, simultaneous proposals and an observability-stress case, provided all exact references are tractable. Preregister at least telemetry × diagnosis and planning × resolution interactions and the model/contrasts used to estimate them. Higher-order interaction exploration and multiplicity policy must be declared. Use scenario/seed blocks and paired treatment differences; packets within a run are not independent replications.

Report Proposed-minus-Null and Oracle-minus-Proposed with uncertainty and a prespecified practically meaningful gap. Do not equate a small or nonsignificant gap with equivalence. Solver timeout or missing Oracle support is a failed/unsupported cell, not a win for Proposed. Resolve support before freezing the scenario set; if a cell later fails, retain it and qualify the factorial inference rather than silently shrinking the matrix.

For telemetry sufficiency, separately budget contract-limited reference versus privileged-current-state comparisons and named observation-subset interventions. A small perfect-diagnoser service gap alone does not identify telemetry as limiting; check diagnostic errors, information ambiguity and downstream interactions. Exact/empirical bounds and deployment-compatible/privileged verdicts remain distinct.

## Ablation matrix

These are mechanism-level substitutions beneath the stage arms, not instructions to remove interfaces. Each substitute emits the same schemas, including explicit empty marks, no-ops and terminal reasons.

| Ablation | Change only | Measure | Interpretation hazard |
| --- | --- | --- | --- |
| A-MARK | Bind an empty-mark provider that records suppressed writes and empty reads | Conflicts, recovery, service and communication cost | Keep direct signals/actions fixed; distinguish audit cost from simulated transport cost |
| A-COLLISION | Substitute first-feasible resolution for the selected conflict protocol | Rejected actions, oscillation, starvation | Preserve actuator consistency checks and typed defer/reject outputs |
| A-INTERPRET | Use a common signal interpretation | Per-class service and coordination | Keep evaluation requirements unchanged |
| A-EXPIRY | Disable mark expiry | Stale claims and recovery failure | Bound run duration; do not silently clean stale marks |
| A-GUARD | Remove AMI minimum-service protection from decisions | Longest no-service interval and AMI violations | Retain AMI assurance requirements |
| A-ORDER | Vary activation/initial allocation | Outcome distribution and convergence time | Independent controller stream; same network workload |
| A-EXPERT | Replace one-rule experts with one engine | Diagnosis agreement, activations and runtime | Same rules, snapshots and conflict policy |
| A-HEURISTIC | Set A* heuristic to zero | Expansions, cost and plan validity | Same graph and tie-break policy |
| A-INFO | Restrict central observation to local scope | Service versus information advantage | Report what each controller can observe |
| A-DELAY | Add mark/decision delivery delay | Conflicts and degradation | Separate delay effect from loss effect |

One-factor substitutions do not establish interaction effects. Marks × conflict handling and mark expiry × message delay require separately registered mechanism-factorial cells if pursued. They do not silently enlarge the initial four-stage design. Do not hide these interactions by averaging across incomparable substrates.

## Parameter register

This is the single source of proposed parameter names for this architecture. **All values are unset, nominal and uncalibrated until pilot experiments define a versioned ParameterSet.** Units below are definitions, not recommended settings.

| Group | Parameters | How values are chosen |
| --- | --- | --- |
| Model | site_count, endpoint_count, path_capacity_bps, queue_limit_bytes, propagation_delay_s, loss_model | Minimal topology with a verified shared bottleneck; declare model fidelity |
| Workload | scada_period_s, request_bytes, response_bytes, ami_period_s, reading_bytes, burst_size, burst_duration_s | Pilot workload sweep below/near/above attainable service |
| Requirements | scada_deadline_s, scada_miss_budget, class_delivery_min, ami_age_limit_s, ami_service_min_bps, starvation_limit_s | Declare research objectives before comparative runs; not industry compliance claims |
| Timing | warmup_s, disturbance_time_s, impairment_duration_s, observation_window_s, decision_period_s, recovery_window_s, drain_s, run_duration_s | Verify enough samples and post-disturbance coverage |
| Eco | mark_ttl_s, backoff_min_s, backoff_max_s, aging_rate, lease_renewal_s, visibility_scope | Sensitivity sweep constrained by observation/action timing |
| Stability | stability_window_s, action_churn_limit, claim_churn_limit, allocation_change_limit | Preregister behavioural definition and test boundary cases |
| Search | action_costs, expansion_budget, memory_budget, time_budget_s, gps_depth_bound, heuristic_version | Shared budgets where comparable; disclose algorithm-specific limits |
| Statistics | seed_manifest, replication_count, confidence_level, target_precision, multiple_comparison_policy | Pilot variance and precision target; fixed analysis plan |
| Design budget | screening_scenario_set, full_scenario_set, screening_replications, confirmation_replications, supplemental_cells, max_compute_time_s, max_log_storage_bytes | Freeze each study before execution; account for 81-cell screen, 9-cell confirmation and every extra cell |
| Arms and references | stage_binding_manifest, null_variant, oracle_information_regime, oracle_horizon, reference_objective, optimality_certificate_policy, meaningful_effect_gap | Fix schemas, method versions, privilege access and estimand before measurement |
| Replay | snapshot_policy, serialization_version, digest_algorithm, dataset_schema_versions, prefix_verification_policy | Demonstrate reconstructability before using replay for inference |
| Evidence | max_observation_age_s, missingness_limit, action_expiry_s, receipt_timeout_s | Timing contract and coverage study |
| Substrate | mark_delay_s, mark_loss_probability, mark_transport_model, controller_delay_s | Separate idealised from communication-aware treatments |

Numeric IDs in this document identify treatments and are not runtime settings. No frequency, band or ownership type is a default parameter.

## Metrics and denominators

- **SCADA deadline-miss ratio:** requests not completed by their deadline divided by eligible generated requests; report counts, including losses.
- **AMI delivery and age:** unique delivered readings over eligible generated readings; age measured from generation to receipt. Report censored readings explicitly.
- **Latency:** per-class quantiles with sample count; distinguish RTT from one-way delay and disclose missing deliveries.
- **Goodput and backlog:** delivered application bits per interval and queued/withheld demand. Pacing must not make unmet demand disappear.
- **Starvation:** longest interval with pending eligible demand and no service, plus violations of the configured service floor.
- **Fairness:** per-class requirement satisfaction and normalised service shares; aggregate fairness does not replace class-specific requirements.
- **Recovery time:** disturbance-to-first sustained service recovery interval; nonrecovery is censored, not dropped.
- **Coordination:** proposal conflicts, retries, stale claims, action/claim churn and time to behavioural stabilisation.
- **Reasoning cost:** expert activations, search expansions, memory, plan length/cost and host computation time.
- **Execution validity:** rejected preconditions, unsupported commands, unknown receipts and state/receipt mismatches.
- **Overhead:** coordination messages/bytes and computation, with the substrate accounting model.
- **Assurance coverage:** evaluable requirements, missing evidence and unsupported claim attempts.
- **Stage contribution/headroom:** paired Proposed-minus-Null and Oracle-minus-Proposed, explicitly conditional on other bindings and information regimes.
- **Information headroom:** privileged versus contract-limited references under fixed downstream methods, with ambiguity/identifiability and reference-certification scope.
- **Replay integrity:** logged boundary coverage, verified dataset hashes, restored-state agreement and supported versus unsupported continuation modes.

## Run procedure and analysis

1. Verify generators and the shared bottleneck in a pilot; choose the scenario set and parameter values. Exclude pilot runs from confirmatory comparisons.
2. Freeze the StudyManifest: scenario-set version/hash and member revisions, stage provider/arm bindings, Oracle permissions and certification scope, capabilities, action catalog, requirements, factorial or confirmation matrix, parameter sets, analysis policy, compute/storage budget and seed/replication plan. Verify membership and hashes before every run.
3. Generate named independent random streams under the frozen plan for arrivals, network errors, disturbances and controller behaviour. Reuse exogenous inputs across paired treatments; controller random draws must not shift traffic draws.
4. Randomise execution order where host timing matters. Apply consistent warm-up, workload and drain policies.
5. Run all treatments for each replication, retaining failures and timeouts.
6. Validate all inter-stage messages and stage datasets before computing metrics; verify study → scenario → run → stage → dataset lineage. Report missing/corrupt runs and their causes. Replay component inputs separately from any action-changing simulator continuation.
7. Compute per-run metrics, then paired treatment differences and uncertainty across independent replications. Do not treat packets from one run as independent experiment replications.
8. Publish distributions, counts, effect sizes and configured confidence intervals. Declare multiplicity handling for many comparisons.
9. Produce claims and assurance reports naming the study and frozen scenario-set version/hash. Close the study under its declared completion rule; researchers may then propose a successor set for a new study.

A scenario-set revision chosen from prior results belongs to the outer research process. It cannot replace the active study's set, even between runs. Keep holdout scenarios/seeds protected from tuning. To claim a controller improved, compare old and new controllers on the same frozen set. When moving from v1 to v2, use separate frozen studies and the explicit cross-version comparison protocol in [Methodology](methodology.md#claims-and-comparisons); do not compare raw run rankings across changing benchmarks.

## Property checks and completion criteria

Future executable checks must establish: a changed set hash or nonmember scenario rejects run admission; every claim resolves to the study's frozen set; runtime actions cannot edit benchmark definitions or scoring; report generation cannot mutate a scenario set; unsupported capabilities fail before a run; no controller reads future evidence; stale commands cannot mutate state; plan replay satisfies all symbolic goals; A* matches uniform-cost optimal cost on enumerable cases; unknown telemetry is not healthy; mark visibility and expiry are enforced; stable starvation is not success; report evidence links resolve; and different random streams remain independent of controller call counts.

Additionally, check every stage's three arm bindings, schema round trips, complete boundary logging, valid degenerate outputs, replay state restoration, Oracle privilege isolation, certificate status, fixed external scoring under assurance substitution, and the declared 81/9 configuration counts. No pipeline implementation should precede agreement on the normative interface, telemetry and action schemas and their acceptance criteria.

A study is complete when its frozen manifest and scenario-set hashes, source versions, execution commands, raw traces, analysis definitions, failed-run accounting and version-scoped claim limitations are available under its declared completion rule. A successful simulation process exit alone is insufficient.
