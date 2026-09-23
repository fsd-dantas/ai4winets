# Simulator adapter contract

**Status: normative specification, partly implemented. The finite reference world satisfies
this interface in-process. The ns-3 simulator process and its Python adapter
(`ecora.simulator`) implement `configure`, `advance`, `observe` and `cohorts` across the
process boundary; `apply`, `truth` and `fork` are refused by the simulator with a reason
until their items land. Of the acceptance list below, item 1 is demonstrated and item 3
in part: a probe returned through `observe` carries the capability of the leg it probed,
and a `truth` request is refused, but only because truth is not yet served at all.**

This document settles how a simulator becomes a world the pipeline can drive. It exists
because the decision that unblocks simulator integration is architectural rather than
procedural: a build produces a library, not a world, and every remaining integration item
depends on where the boundary between the decision loop and the simulator is drawn.

Read [Interfaces](interfaces.md) for the envelope and replay rules, [Telemetry
contract](telemetry-contract.md) for evidence and privilege, and [Action
contract](action-contract.md) for authority and receipts. This document does not restate
them; it says how a simulator in another process satisfies them.

## The interface a world must satisfy

The orchestrator drives any world through six calls, and through nothing else. The finite
reference world implements them directly; a simulator adapter implements the same six
across whatever boundary it needs.

| Call | Obligation |
| --- | --- |
| `advance_to(time_s)` | Run every event up to and including `time_s`, in deterministic order. Refuse a clock that moves backwards. |
| `apply(command)` | Apply an admitted `ActionCommand`. Return whether it applied and, when it did not, why. |
| `observations(capability_ids, window_s)` | Export the declared observable signals, and only those the passed capabilities permit. |
| `observation_id(subject, metric, at_s)` | The canonical identity of an exported signal, stable across runs of the same world. |
| `truth()` | Current state for privileged references only. Never ordinary input. |
| `cohorts(cohort_specs)` | Measured counts for the study's frozen cohort specifications. |

Two properties of this list matter more than its contents. It is **small** — six calls,
none of which mentions a queue, a radio or a packet — so a second world is a bounded
obligation rather than a rewrite. And it is **already the seam every
arm is measured across**, so a simulator that satisfies it inherits the Null, Proposed and
Oracle structure without any stage being rewritten to know which world it is running over.

## The decision that has to be made first

The pipeline is a stepped closed loop: advance, observe, diagnose, plan, resolve, act,
advance again. ns-3 is a run-to-completion C++ event loop. The providers, contracts,
artifact store and hash-chained journal are Python. Something has to bridge that, and the
choice determines the rest of the integration.

### Option A — in-process Python bindings

The adapter imports ns-3 through its Python bindings and calls it directly.

Against it: the bindings are a generated surface whose coverage of the LTE module is not
guaranteed and is not part of the release's test obligations, so a missing binding is
discovered during integration rather than declared in advance. More decisively, the
simulator would then live inside the same process as the decision loop, which forecloses
the branching strategy and weakens the privilege boundary to a naming convention — the
same class of boundary that has already leaked here once, when privileged state reached a
planner through a harness helper that claimed it did not.

### Option B — separate process, per-epoch protocol (selected)

The simulator is a C++ program holding the topology and the event loop. The adapter is a
Python object implementing the six calls by exchanging framed messages with it over a
pipe. One exchange per call; the simulator is idle between exchanges.

For it:

- **The privilege boundary becomes real.** `truth` is its own request kind, which the
  simulator answers only when the grant accompanying it names the signal asked for. An
  observation request cannot return truth because it is a different message on the wire,
  not a different method on an object that happens to hold both.
- **Branching becomes possible at all.** ns-3 has no checkpoint or restore. Forking the
  simulator process at a declared epoch uses the operating system to duplicate state the
  simulator cannot duplicate itself, and a fork requires a process to fork. Causal-prefix
  regeneration remains the portable fallback and is already implemented.
- **A crash is contained.** A simulator that dies takes its process down, and the run is
  quarantined by the existing interrupted-run path rather than taking the journal with it.
- **The cost becomes measurable.** Per-epoch exchange cost is observable at the adapter,
  which is what the cost item needs and what no budget can be frozen without.

Against it: it is more work than a direct call, and it introduces a protocol that must
itself be specified and tested. That cost is accepted. Both of the other requirements —
branching and an enforceable privilege split — are unavailable without it.

### Option C — the pipeline in C++

Rejected without further analysis. It would duplicate the contract layer, the store and
the journal in a second language to avoid a pipe.

## The protocol

One request, one response, framed as length-prefixed canonical JSON — the same
serialisation the records already use, so the adapter introduces no second encoding.

| Request | Carries | Response |
| --- | --- | --- |
| `configure` | the scenario, verbatim | the resolved model manifest, or a refusal |
| `advance` | target time | the time reached |
| `apply` | the admitted command | applied or not, and the reason when not |
| `observe` | capability grants, window | the exported observations |
| `truth` | truth capability grants | the privileged state those grants permit |
| `cohorts` | the frozen cohort specifications | the measured counts |
| `fork` | the epoch to branch at | the child's handle |

Probing is deliberately absent. A leg probe is how the finite world produces a
`path_probe` observation, not a separate question the orchestrator asks, and each leg is
its own subject carrying its own capability: permission to probe one leg is not permission
to probe the other. A simulator answers probes inside `observe`, under the same grants and
the same capability filter as every other signal. Promoting it to its own request would
create a second path by which a value could reach a provider, and the value of this
boundary is that there is one.

Rules the protocol is required to hold, each of which exists because its absence is a way
for a run to claim more than it observed:

1. **The simulator never initiates.** It answers. A simulator that could push would be a
   source of evidence outside the audited boundary.
2. **`truth` and `observe` are distinct requests.** A simulator refuses a `truth` request
   whose accompanying grants do not name the signal asked for, and refuses to return any
   truth-derived value through `observe` under any circumstances.
3. **`advance` is monotonic.** A target earlier than the current time is refused rather
   than silently clamped.
4. **Every response is attributable.** A response carries the request it answers and the
   simulator's model-manifest hash, so a record cannot be attributed to a build other than
   the one that produced it.
5. **A refusal is a result.** A simulator that cannot satisfy a request says so and says
   why. It does not approximate, and the adapter does not substitute.

## What the scenario supplies

Scenarios are already data, and the same scenario builds either world. The finite model
reads it through `ecora.scenario.build_world`; the simulator reads the same declaration
through `configure`.

| Scenario field | Finite world | Simulator |
| --- | --- | --- |
| `topology.sites` | generating sites | site gateway nodes |
| `topology.legs` | byte-service FIFO queues | the LTE leg and the point-to-point leg |
| `topology.egress` | shared egress queue | the shared rate-limited central link |
| `topology.initial_path` | initial selector value | initial gateway forwarding selector |
| `topology.initial_pacing` | initial release profile | initial gateway release profile |
| `flows` | generation period, payload, deadline | the traffic applications |
| `disturbances` | scheduled rate changes | the impairment hooks, held apart from controller authority |

A scenario that declares a world the simulator cannot build is refused at `configure`, in
the same way and for the same reason that the finite world refuses one it cannot build.
The world-matching check that already refuses a model disagreeing with its scenario applies
unchanged: what it compares is the declaration against what the world reports holding, and
a simulator reports through `configure` rather than through attributes.

## What this does not decide

- **The model manifest's contents** beyond the requirement that it be exported at
  `configure` and hashed into every response. Which resolved attributes it must carry,
  including the settings inherited from the pinned release, belongs to the build item.
- **The per-epoch cost.** Unmeasured, and the existing budget is already exceeded by the
  finite world alone. No budget or scenario-set membership may be frozen before it is
  measured with continuation exercised.
- **Whether an action Oracle exists against the simulator.** The action contract permits
  one only where a verified direct-actuation hook is exposed. Until that is demonstrated
  the Oracle cell is unsupported and must not be filled silently by the Proposed arm.
- **Fork semantics under the simulator's own resources.** Sockets, files and any state the
  simulator holds outside its event calendar are not duplicated by a fork in a way this
  document has established, and branching must not be claimed before that is verified.

## Acceptance

The adapter is not integrated until each of these is demonstrated, and each corresponds to
a way the integration could otherwise claim more than it established:

1. The same scenario builds both worlds, and each reports holding what the scenario
   declares. **Demonstrated** for all six scenarios: `verify_world` checks the finite
   model and `verify_simulated` checks what the simulator's `configure` reports it built,
   field by field, including that the finite world's logical reading of the LTE leg is
   reported as not applicable.
2. An admitted action changes simulator state, and observations taken afterwards establish
   its consequences. A suppressed action leaves state unchanged.
3. A `truth` request without the matching grant is refused, and no truth-derived value
   ever reaches an ordinary observation. A probe returned through `observe` carries the
   capability for the leg it probed and no other. A test asserts each refusal and can fail.
4. Two runs of one treatment under one seed plan produce byte-identical journals.
5. A branch from a forked epoch continues that world, produces evidence only from its
   branch point onward, and reports under its own run identity.
6. Per-epoch cost is measured with continuation exercised, and recorded before any budget
   is frozen.
7. A simulator crash quarantines the run rather than corrupting the journal.
