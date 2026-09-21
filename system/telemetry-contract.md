# Telemetry and information-access contract

**Status: planned normative specification; no adapter is implemented by this document.**

[Interfaces](interfaces.md) · [Stage arms](../docs/ECoRA/stage-arms.md)

A signal absent from the declared deployment telemetry contract is not observable by a Proposed or Null controller and may not be treated as evidence. Simulator truth is supplied only through an explicit, separately logged Oracle interface. An Oracle result cannot validate that signal's availability in a real deployment.

## Observation schema

Each observation identifies its subject/flow, metric, value or missing-value reason, unit, source adapter/trace, event time, availability time, measurement window, sampling policy, valid range, quality flags, evidence kind and calibration/model assumptions. The inter-stage envelope in [Interfaces](interfaces.md#message-envelope-and-durable-log) binds it to the study, scenario, run, stage invocation and dataset.

TelemetryBatch additionally carries sequence, watermark, coverage and completeness. A locally visible EnvironmentalSignal names the originating observation IDs, projection/interpretation version and permitted agent neighbourhood. A derived metric names its formula and complete source cohort. A missing observation remains unknown, never zero or healthy.

Configured ranges and sampling intervals live in the frozen ParameterSet. Rates are nonnegative, probability-valued metrics lie in their declared probability range, and timestamps must use a consistent clock; implementation schemas must enforce the corresponding ranges and units.

## Signal catalog

The [selected v1 projection](../docs/ECoRA/v1-scope.md#agent-scope-observations-and-control)
is per site/service: own workload, queue/release and delivery summaries, local path
selector/version, round-trip probe events and same-site marks. `path_probe` records the
probe ID, leg, send/acknowledgement times and timeout disposition; all are availability-
gated and do not imply a physical cause. Proposed and Null never receive injected-failure
labels, configured loss rates, hidden capacity, other-site queues or future schedules.
The central bottleneck trace is independent evaluator evidence, not extra local telemetry.
Remote delivery summaries carry the declared delay. Optional radio measurements are
excluded from the initial Proposed projection even if the LTE trace can export them.

| Signal | Semantics and unit | Required source |
| --- | --- | --- |
| packet_generated | Unique packet/flow ID and generation time | Application trace |
| packet_delivered | Matching packet ID and reception time | Receiver trace |
| scada_response | Request ID and completion time, for RTT | Request/response application |
| queue_occupancy | Bytes or packets, never implicitly interchangeable | Queue trace |
| offered_load | Generated payload bits/s over declared interval | Application accounting |
| goodput | Unique received application bits/s, excluding duplicates | Receiver accounting |
| packet_drop | Packet ID and reason where observable | Queue/device/application trace |
| path_state | Applied path identifier and configuration version | Actuator observation |
| path_probe | Probe/leg ID, send and acknowledgement times or timeout; seconds | Gateway probe application and delayed acknowledgement trace |
| claim_state | Local claim owner, resource, version and expiry | Coordination substrate |
| control_message | Message event, size, endpoints and visibility | Coordination transport |
| link_measurement | Explicitly named metric and unit such as model-supported received power | Actual radio trace; absent on a surrogate without that model |

The run's CapabilityManifest selects the supported subset. The catalog is a specification, not evidence of implementation. A configured error probability is not an observed packet-loss ratio. One-way delay and request/response RTT remain separate metrics.

Windows declare interval boundaries, generation cohort, deadline/drain policy, duplicate handling and right-censoring. Lost or pending packets cannot disappear from denominators. Late observations preserve both event and availability times, so replay cannot give a past decision evidence it did not yet have.

## Telemetry stage providers

| Arm | Provider behaviour | Output and permission |
| --- | --- | --- |
| Null | Explicit empty/missing observation policy, or a preregistered minimal pass-through; choose one before the study | Valid TelemetryBatch with watermark, omissions and quality; contract-only |
| Proposed | Normalise declared adapter traces and enforce locality, timing and quality | Valid measured/derived evidence from the supported catalog |
| Oracle | Project exact current simulator quantities for a declared truth catalog | Same envelope with privileged provenance and oracle-state regime; never relabelled as deployment observations |

The initial factorial Null policy is `telemetry.empty`, so its output declares all dynamic fields unknown. Static scenario knowledge available to every arm remains fixed. A minimal pass-through is a separate Null variant, not an unrecorded fallback. Missing input must be handled by all downstream providers through their declared degenerate or abstention behaviour.

Oracle telemetry does not erase sensor absence from the Proposed contract. Its fields map through a versioned truth projection and are labelled simulator truth. The study declares whether perfect freshness/precision or extra state fields are provided; those changes are experimental information interventions.

## Privileged truth channel

Oracle providers may request current truth through a logged TruthPort with named capabilities. It identifies simulation time, query type, returned variables, requesting invocation, truth dataset and allowed recipients. A perfect diagnosis may be read directly from the evaluator's current ground-truth labels, so a downstream Oracle can intentionally bypass information loss at an upstream stage. That bypass is recorded in the factor definition and all causal traces.

Current-state truth is not future truth. Future arrivals, random outcomes or disturbance schedules remain hidden unless a separate clairvoyant treatment is explicitly registered. The default Oracle arm excludes future information. Deployment-compatible providers cannot open the TruthPort. Privilege labels propagate to descendants and reports.

## Measuring telemetry sufficiency

Distinguish:

- **Contract-limited reference:** the best certified decision procedure available for exactly the same observations, locality and history. It cannot use simulator truth at decision time; on tractable models it may compute an exact decision under a declared uncertainty model.
- **Privileged current-state Oracle:** exact simulator state or diagnosis at the decision watermark, with the same allowed actuators and declared objective.
- **Optional clairvoyant bound:** future information, isolated from the initial factorial and never described as deployable.

A small downstream service gap between a Proposed diagnoser and a perfect diagnoser only shows small diagnostic headroom for that downstream configuration. It does not prove that telemetry is the bottleneck. The proposed diagnoser may already be adequate, the planner/actions may be limiting, or the metric may be saturated.

For an information-limit claim, hold downstream providers and objectives fixed, compare a contract-limited reference with a privileged reference, and vary named observation subsets. If the same observed history corresponds to distinct hidden states requiring different actions, no diagnoser using only that history can always disambiguate them; quantify the frequency and consequence in the declared model. A finite reference policy is an empirical comparator unless its optimality over that information set is certified.

Report diagnosis accuracy/calibration where applicable alongside end-to-end service and assurance coverage. Ground truth may score all arms after the decision; that does not grant it to their controllers. Claims apply to the evaluated observation contract and simulator assumptions, not automatically to real deployments.

## Acceptance obligations

Future checks must show visibility and time enforcement, unavailable-signal rejection, missingness propagation, exact evidence lineage, complete TruthPort logging, privilege nonleakage, deterministic replay and agreement between truth labels and the simulator mechanisms they purport to represent.
