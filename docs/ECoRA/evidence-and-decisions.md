# Evidence boundaries and architectural decisions

**Status: planned architecture; runtime capabilities require evidence from this repository.** [Index](README.md)

## Evidence policy

ECoRA is specified as a new system. Its requirements, contracts, provider interfaces and experimental design define what will be built. Capability claims require executable components and reproducible evidence produced within this repository.

No runtime implementation or simulation result is established by this architectural document. Each capability starts as planned and is assessed against its own acceptance criteria. A design description, dependency feature list or configured parameter alone does not establish an exercised capability.

The proposed ns-3 integration must establish:

- The selected network models, supported abstractions and executed attributes.
- Distinct SCADA and AMI generators, service requirements and a measured shared bottleneck.
- Causal telemetry availability, explicit action authority and verified application receipts.
- Independently observable impairment and restoration mechanisms for the scenarios that require them.
- Serialised stage datasets, reproducible run manifests and evaluator evidence for every reported claim.

The official [ns-3 LTE model description](https://www.nsnam.org/docs/models/html/lte-design.html) distinguishes LTE radio protocol components from EPC components. ECoRA must record the actual selected model and runtime attributes; a general model library capability is not proof that a particular scenario exercises it.

## Capability ledger

| Capability | ECoRA status | Promotion evidence required |
| --- | --- | --- |
| Versioned scenario/telemetry/action contracts | Implemented | [Contract package](../../software/README.md): structural and semantic validation, immutable records and round-trip tests |
| Study-level scenario-set freeze | Implemented | Exact set/member/configuration hash checks and complete binding admission, exercised on synthetic manifests |
| Provider registry and audited boundary | Implemented | Configuration-only fixture substitution, terminal logging, capability/privilege checks, delivery and dispatch deduplication |
| Immutable stage datasets and journal | Implemented | Hash-addressed records, invocation ownership, checked ancestry and corruption/restart tests; no simulator continuation claim |
| Configurable Null/Proposed/Oracle stage providers | Planned | Complete bindings, valid degenerate outputs and identical boundary schemas |
| Replay and simulator continuation | Planned | Restore state, replay boundaries and verify causal simulator continuation using the implemented artifacts |
| Privileged Oracle and contract-limited references | Planned | Access isolation, truth mapping, scoped optimality certificates and matched-information comparisons |
| Single expert and one-rule experts | Planned | Matched rule/snapshot comparison and trace validation |
| STRIPS-domain, GPS and A* planning | Planned | Plan property tests, small-domain reference results and budgets |
| Local satisfaction and environmental marks | Planned | Enforced local visibility, lifecycle checks and coordination experiments |
| ns-3 LTE integration | Planned | Build manifest, inspected attributes, trace and reproducible run |
| Abstract alternative radio path | Planned | Declared surrogate assumptions and measured queue/path behaviour |
| Distinct SCADA and AMI competition | Planned | Separate flow instrumentation and verified shared bottleneck |
| Online closed-loop actuation | Planned | Causal telemetry barrier and application receipts |
| Frequency-specific PHY/MAC claims without an instantiated model | Unsupported | A suitable instantiated model and validated configuration |
| Deployment properties outside the declared network model | Unsupported | Explicit model of the claimed properties and supporting evaluation |
| RF collision claims from point-to-point surrogate | Unsupported | A radio contention/interference model supporting the metric |
| Guaranteed eco-agent convergence | Unsupported | Proof under stated assumptions or a narrower empirical claim |
| Production-network assurance or industrial protocol compliance | Unsupported | Outside the initial model and evidence scope |

Status is scoped to this design, not a judgement that a technology is impossible. New requirements can introduce new models and evidence.

## Decision record

| ID | Decision | Rationale and consequence |
| --- | --- | --- |
| ADR-01 | Keep architectural views under docs/ECoRA and normative seams under system | The interface, telemetry and action stubs are now expanded specifications; remaining system placeholders await their own contracts |
| ADR-02 | Separate diagnosis, planning, resolution, execution and assurance | Prevent inferred or predicted success from becoming a measured claim |
| ADR-03 | Begin with a modular application and adapter boundary | DDD separation without premature distributed deployment |
| ADR-04 | Keep SCADA and AMI as the first competing services | Concrete contrasting requirements with a bounded experimental scope |
| ADR-05 | Propose per-site, per-service-queue eco-agents | Local satisfaction and action ownership are explicit; granularity remains testable |
| ADR-06 | Keep blackboard control separate from the eco environment | Central expert scheduling and decentralised action coordination answer different questions |
| ADR-07 | Use STRIPS operators with explicit search policies | Avoid treating representation, GPS and A* as equivalent layers |
| ADR-08 | Treat marks as local, expiring and advisory unless granted | Prevent an implicit global reservation oracle |
| ADR-09 | Gate every action and observation by capabilities | Admit only behaviours supported by the declared model, adapter and evidence |
| ADR-10 | Keep evaluator ground truth outside controller inputs | Avoid future/fault-label leakage |
| ADR-11 | Assess service and stabilisation independently | Stable starvation must remain visible |
| ADR-12 | Move scenario-set revision to research methodology | Supersedes the single-ring lifecycle; reports inform research review, which proposes a successor set for a new study |
| ADR-13 | Use inline Mermaid and themed SVG overview exports | Keep reviewable relationships and repository-native vector figures |
| ADR-14 | Keep assurance passive throughout a frozen study | Prevent adaptive scoring, benchmark drift between runs or hidden controller intervention |
| ADR-15 | Freeze one scenario-set version per study | Every run checks membership/hashes and every claim names its benchmark; new controllers can be compared on the same set in a new study |
| ADR-16 | Keep the nonautomated research loop outside runtime diagrams | Research review belongs to methodology; a future automated loop would require an explicit component and authority contract before inclusion |
| ADR-17 | Define every stage as a replaceable interface | Null, Proposed and Oracle providers preserve typed outputs; ablation is a frozen configuration binding, never a deleted stage or code fork |
| ADR-18 | Serialise and log every inter-stage message | Extend provenance to study → scenario → run → stage → dataset; retain state, no-ops, errors and privileged lineage for replay |
| ADR-19 | Separate component headroom from information headroom | A small perfect-diagnoser gap alone does not identify telemetry as limiting; compare contract-limited and privileged references with downstream controls |
| ADR-20 | Screen four three-arm factors, then confirm conditional effects | Budget 81 configurations on a small frozen set and 9 on a separately frozen full set; declare extra studies and interaction checks |
| ADR-21 | Complete interface, telemetry and action specifications before pipeline code | These normative contracts define the ablation seams; executable schemas and replay acceptance checks are prerequisites |
| ADR-22 | Keep independent study scoring fixed across assurance arms | A substituted assurance provider cannot improve measured service by changing verdict policy |
| ADR-23 | Select site-to-central wireless backhaul as the v1 system boundary | Field access is outside scope; LTE transport and a point-to-point alternative surrogate support no second-RAT claim |
| ADR-24 | Fix v1 workload, locality and action semantics | Central SCADA transactions and independent site AMI readings retain obligations; site path switching and AMI release control follow [v1 scope](v1-scope.md) |
| ADR-25 | Exclude failure labels from ordinary controller inputs | Proposed/Null use availability-gated operational evidence; truth access belongs to logged privileged references and independent evaluation |
| ADR-26 | Restrict exact optimisation to finite declared problems | Configuration planning, proposal-subset resolution and a supplemental information-ambiguity problem have explicit objectives, horizons and certificates, not global packet-service bounds |
| ADR-27 | Select initial parameters and a bounded local execution envelope | [Initial values](experiments.md#initial-v1-values) are synthetic and uncalibrated; pilots establish feasibility before study freeze |
| ADR-28 | Pin ns-3 3.48 in place of the nominal 3.45 | The nominal value was never tied to a 3.45-specific feature, and no run had been made against it. The pin is the archive's SHA-256 in `software/simulator/ns3-build.json`, and every inherited default is exported in the model manifest, so the change is recorded as data rather than asserted. Results are scoped to 3.48; the LTE components selected in [v1 scope](v1-scope.md#wireless-backhaul-model) are unchanged |

These are proposed architecture decisions, not claims of implementation acceptance.

## Implementation sequence and exit evidence

| Stage | Work | Exit evidence |
| --- | --- | --- |
| Contract foundation | Normative system interfaces, telemetry and action documents, then executable schemas and fixtures; study/set manifests and ontology mappings | Complete stage/arm schemas, serialisation/logging examples, freeze enforcement, privilege isolation and unsupported-action rejection before pipeline code |
| Logical reference world | Small finite resource model, generators and evaluator | Hand-checkable traces, service and stability verdicts |
| Substitution and replay harness | Provider registry, stage datasets, snapshots and typed degenerate providers | Replayable boundaries, exact small-model Oracles, immutable lineage and counterfactual continuation limits |
| Expert comparison | Single engine and one-rule blackboard experts | Agreement under matched inputs; contradiction/retraction tests |
| Planner comparison | STRIPS-domain uniform-cost, GPS and A* | Valid plans; bounded failure; reference optimal costs where applicable |
| Eco reference | Local agents, marks and conflict mechanisms | Locality and expiry enforcement; starvation and oscillation cases |
| ns-3 integration | Explicit LTE/alternative-path model, distinct workloads and causal actuation | Reproducible run, validated trace mapping and action receipts |
| Factorial screen | Frozen small set, four three-arm factors, paired replications and declared interactions | All 81 cells accounted for, Oracle scope, compute/storage usage and stage datasets |
| Confirmatory study | Separately frozen full set, 9 conditional-effect configurations and named supplemental cells | Uncertainty estimates, failed-run accounting, benchmark-scoped claims and no unsupported interaction generalisation |
| Research review (methodology) | Human review of reports and successor scenario-set proposal | New study freeze; same-set controller comparisons and explicit benchmark-version effects |

Implement each component against its declared contract and acceptance criteria. Dependency selection follows the current research requirements and capability needs.

## Remaining implementation and study obligations

The [v1 scope](v1-scope.md) closes the initial workload, backhaul model, agent/locality,
safety, reference-problem and preliminary budget decisions. The alternative remains a
surrogate in v1. Initial resolution uses local intent marks and backoff; performance
prediction is excluded from the initial configuration planner.

- Implement workload accounting, gateway forwarding, visibility enforcement and causal replay; verify the shared bottleneck and enabled actuators.
- Execute finite reference enumeration and certificate checks; unsupported or timed-out Oracles cannot be silently replaced by heuristics.
- Pilot nominal parameters, run cost, storage and uncertainty. Revise candidate values with rationale when needed; freeze final membership, replications, contrasts and budgets before comparative measurement.
- Evaluate separately budgeted agent/activation-order, planner, expert-organisation and communication sensitivities; initial choices are not claims of optimality.
- Establish the bibliographic source for eco-problem solving before historical attribution, and complete literature synthesis before any novelty claim.

Scope selection supplies no calibration, runtime implementation or experimental result.

## Maintenance against stale references

Each runtime capability must name its owner, contract version and evidence. Retire a capability explicitly when its adapter is removed. A documentation link check should accompany contract changes, and schema compatibility should be checked before old artifacts are reanalysed.

Keep parameters in the declared register and eventual versioned ParameterSet, rather than copying thresholds into rules or reports. Maintain one action catalog across methods. A model substitution requires a new study and, when it changes a benchmark definition, a successor scenario-set version; recording it only in the next run's manifest is insufficient. Each dependency and constraint must be justified by a current requirement or supported capability.
