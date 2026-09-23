# Channel assignment development backlog

[Study design](README.md) · [Architecture](architecture.md) ·
[Experiment Index](../../README.md#experiment-index)

Status: `todo` · `wip` · `blocked` · `done` · `dropped`

This is the public delivery plan. Item IDs are stable: an item keeps its ID when it moves
between milestones. The core is D0 through D4; D5 is a declared, deferred comparative study,
and D6 packages whatever has been completed. No dates or estimates are commitments.

**Position (2026-09-23): 10 of 39 items done; 15 of the 25 core items (D0–D4b) remain. D0 and D1 are complete; D2 is in progress.
Next: CA-10, downward VALUE reconstruction.** The critical path is at the end of this page.

---

## D0 — Fix the research scope and architecture

**Status: done, 2026-09-23.** The study is reframed with map coloring as the primary
problem and channel assignment as its wireless reading. RQ1–RQ4 and claims C1–C5 are in the
[study design](README.md#research-questions); the comparative study is moved to D5. The
[architecture](architecture.md) records contexts, protocol, lifecycle, invariants and
decisions D1–D10. Mobile cells enter as re-solved snapshots with a stability cost (D9).

| ID | Item | Status |
| --- | --- | --- |
| CA-00 | Reframe the question: map coloring first, channel costs second, separators descriptive, mobile cells as epochs; move the 960-run comparison to a deferred extension | done |
| CA-01 | Record scope and dependency decisions: two modes, four-channel hard constraints, static costs per solve, reliable transport, standalone package, original solver; permitted utility libraries named, none solving the DCOP | done |

**Gate:** every claim has a named kind (correctness, illustrative or descriptive) and a
named piece of evidence that would settle it.

---

## D1 — Domain contracts and validated instances

**Status: done, 2026-09-23.** Implementation record: [package](../../software/dcop_channel_assignment/README.md),
[domain tests](../../tests/test_dcop_domain.py), [geography tests](../../tests/test_dcop_geography.py).

| ID | Item | Status |
| --- | --- | --- |
| CA-02 | Region, AP and channel value objects and the scenario aggregate. Rectangle and GeoJSON inputs; adjacency derived from shared boundaries; duplicate IDs, invalid scores, overlapping or invalid geometry, disconnected and nonplanar graphs rejected | done |
| CA-03 | Immutable variables, factors, assignments and instances; exact finite and forbidden costs with explicit wire form; scope, domain and cardinality validation | done |
| CA-04 | Deterministic translation to local agent views: one variable per region, one factor per edge, unchanged scores, no wireless type inside the solver | done |
| CA-05 | Synthetic 12-region grid and smaller grids; sourced Curitiba maps of 14 and 29 municipalities with hashes, graph summaries and light/dark previews | done |

**Gate:** a validated map translates to a DCOP instance whose every assignment costs the
same as in the map, checked by exhaustive enumeration on a small fixture.

---

## D2 — A distributed coloring, end to end

**Status: in progress.** DFS and UTIL run on every fixture and both Curitiba maps. The root
reports the optimal cost, but no agent reports its channel yet: agents keep their
conditional choices, and VALUE execution is still rejected at
[agents.py](../../software/dcop_channel_assignment/agents.py).

Integration figures are in the [study design](README.md#demonstration-and-validation-instances):
the 14-region core completes with a largest joined table of 4,096 to 16,384 entries,
depending on the root; the 29-region map stops with `budget_exceeded` under either root.

| ID | Item | Status |
| --- | --- | --- |
| CA-06 | Agent session lifecycle, typed DFS/UTIL/VALUE envelopes and a deterministic queue transport. Wrong-run, malformed, duplicate and out-of-phase messages rejected; no agent can read global state | done |
| CA-07 | Distributed DFS pseudo-tree. Spanning coverage, parent/child consistency and the ancestor relation of every non-tree edge checked after each run; 152 small-graph/root combinations tested | done |
| CA-08 | Table join and minimization with canonical ordering, conditional choices, forbidden costs and entry budgets checked before allocation; 100 generated cases against enumeration | done |
| CA-09 | Upward UTIL propagation. Each factor counted once at its owner; child table scopes must match DFS separators; root cost matches enumeration on 30 generated instances under every root | done |
| CA-10 | Downward VALUE reconstruction. The root chooses; each parent sends each child exactly the child's separator assignment; each agent looks up its conditional choice and sends on. Every agent chooses once; the reconstructed cost equals the root cost; an infeasible root sends no VALUE and no channel is fabricated. Adds the `assigned` state | todo |
| CA-11 | Independent evaluator. Checks completeness, domain membership, conflicting edges, conflict rate and unary sum, without importing solver code or trusting its status. Corrupted assignments are caught | todo |
| CA-12 | `solve` entry point and CLI: map in; pseudo-tree, messages by phase, final coloring and the evaluator's verdict out. A tested command in the package README | todo |

**Gate:** a planar map of at least ten regions is colored with zero conflicts through agent
messages alone, and the independent evaluator confirms it.

---

## D3 — Correctness evidence

**Status: todo.** Enumeration already exists as a test helper; CA-14 makes it a reference
module and adds the independent baseline.

| ID | Item | Status |
| --- | --- | --- |
| CA-13 | Channel-cost mode end to end. A hand-checked case where two neighbors prefer the same channel and the optimum sends one of them to a more expensive channel. Zero-cost mode remains valid | todo |
| CA-14 | Exhaustive reference for 2 to 8 agents and the independent baseline (each AP takes its cheapest channel, same tie rule). Neither is reachable from an agent's decision path; an interrupted reference never claims optimality | todo |
| CA-15 | Generated-instance checks of full solves: DPOP cost equals the reference under every root; reordering inputs preserves the cost; forbidden assignments never pass; invalid inputs are rejected | todo |
| CA-33 | Infeasibility cases built directly as DCOP instances: K5 with four colors is `infeasible` under every root, with and without unary costs, with no assignment; K5 minus one edge and K4 solve with a finite cost. Checked against enumeration and the pigeonhole argument | todo |

**Gate:** DPOP matches the exact reference on every generated instance, and an infeasible
instance ends as `infeasible` with no agent holding a channel.

---

## D4 — Demonstration

**Status: todo.** The demonstration is built on recorded runs, so every figure regenerates
from a run and agrees with the evaluator's record.

| ID | Item | Status |
| --- | --- | --- |
| CA-27 | Colored map: the final assignment drawn on the map with channel labels as well as colors, conflicting edges marked, pseudo-tree edges optional; the replay extended with VALUE messages. Light and dark variants | todo |
| CA-31 | Hand-authored map input: a small file listing regions and shared borders, validated as simple, connected and planar before solving, and drawn from a planar embedding. Lets a new map of at least ten regions be solved on the spot | todo |
| CA-32 | Hand-checkable trace on a five-region map with one non-tree edge: every DFS message, every UTIL table and every VALUE message written out and derived by hand | todo |
| CA-37 | Resource description (C4): separator sizes, largest tables and message counts by phase for each demonstration map under two roots, plus the baseline's conflicts on the same maps and costs (C3) | todo |
| CA-38 | Demonstration runbook: exact commands, expected outputs and timings for every demonstration map, tested from a clean checkout | todo |

**Gate:** each demonstration map, including one supplied at run time, is solved, verified
and shown colored from recorded runs, with a trace a reader can follow by hand.

### D4b — Mobile cells

| ID | Item | Status |
| --- | --- | --- |
| CA-34 | `MobileCellSequence` in Wireless Planning: an ordered list of epochs, each a complete validated map in which the mobile cell is one region; AP identities stable across epochs | todo |
| CA-35 | Epoch runner: solve epoch 1; for each later epoch, add the stability cost `s` to every surviving AP's non-current channels from the previous validated plan, then solve from scratch. The solver receives ordinary unary costs and no epoch information | todo |
| CA-36 | Mobile-cell demonstration (C5): at least three epochs (arrival, move, departure) solved with `s = 0` and with the dominant `s`; reassignments, conflicts and cost per epoch reported and drawn | todo |

**Gate:** across every epoch both settings stay conflict-free, and the reassignment count of
each is reported beside it.

---

## D5 — Deferred comparative study

**Status: deferred.** Starts only after D4 closes, with its own frozen protocol. Declared in
the [study design](README.md#deferred-extension-a-comparative-study).

| ID | Item | Status |
| --- | --- | --- |
| CA-16 | Enforce wall-time and process-memory limits beside the table budget; interrupted runs are never scored as feasible or infeasible | todo |
| CA-17 | Synthetic planar-map and cost-profile generators for the declared strata; separate random streams; actual density and separator widths recorded | todo |
| CA-18 | Study freeze and run records: scenario hashes, arms, seeds, budgets, root policy, source and dependency versions, analysis definition; mismatches refused | todo |
| CA-19 | Measurement adapters: messages by phase, payload bytes, table entries, separator sizes, memory and timing, with the byte encoding and timer boundaries stated | todo |
| CA-20 | Persist manifests, traces, assignments, outcomes and measurements with checksums; verify reload and replay | todo |
| CA-21 | Paired batch execution with randomized timing order; resume skips only verified complete runs; failures stay in the ledger | todo |
| CA-22 | Pilot of at most 24 runs; revise nominal settings with recorded rationale; pilot seeds excluded from the main analysis | todo |
| CA-23 | Freeze estimators, pairing rules, nesting of seeds within maps, intervals and failure accounting | todo |
| CA-24 | Freeze the main study; audit membership and the 960-run count | todo |
| CA-25 | Execute the frozen matrix; reconcile every scheduled run to a terminal record | todo |
| CA-26 | Feasibility and cost comparisons, resource distributions and separator-versus-table analysis, generated from artifacts with denominators and uncertainty | todo |

**Gate:** every scheduled run has a terminal record, and every figure resolves to run IDs.

---

## D6 — Package and reproduce

**Status: todo.** Applies to whatever D2–D5 has completed; D5 is not a prerequisite.

| ID | Item | Status |
| --- | --- | --- |
| CA-28 | Report answering each research question, separating correctness from description, with the limits of planar adjacency, synthetic scores, reliable transport and table growth | todo |
| CA-29 | Experiment directory with pinned environment, exact commands, inputs with hashes, raw traces and regenerable figures; reproduced from a clean environment | todo |
| CA-30 | Experiment Index updated with the actual evidence status; synthetic provenance, attribution and link integrity verified | todo |

**Gate:** a reader reproduces every reported figure from the experiment directory alone.

---

## Optional successor studies

Not part of the core or of D5. Each needs its own question and protocol.

| ID | Extension | Depends on |
| --- | --- | --- |
| CA-X1 | Validate assignments in a packet-level simulator with a declared radio model and traffic before any radio-performance claim | D6 |
| CA-X2 | Compare root and DFS ordering policies on fixed instances | D4 |
| CA-X3 | An independently implemented ADOPT, or another declared comparator, on equal inputs and budgets | D4 |
| CA-X4 | Nonplanar interference and limited channel availability, including a mobile cell that overlaps fixed coverage; four colors are then no longer guaranteed and `infeasible` becomes a real outcome | D4b |
| CA-X5 | Changing costs or lost messages during a solve, with explicit protocol changes; static DPOP is not relabeled as a dynamic solver | D4b |
| CA-X6 | Integration with ECoRA through a translator and explicit contracts, only if a new research question requires it | D6 |

---

## Critical path

**D2 → D3 → D4 → D4b**, with D6 closing whatever is complete. D5 is off the critical path.

1. **CA-10** VALUE. Everything after it depends on agents actually holding channels.
2. **CA-11** evaluator, then **CA-12** `solve` and CLI. D2's gate closes here.
3. **CA-33**, **CA-13**, **CA-14**, **CA-15**. The correctness evidence; CA-33 is the
   smallest and exercises the infeasible path of CA-10 first.
4. **CA-27**, **CA-31**, **CA-32**, then **CA-37** and **CA-38**. The demonstration.
5. **CA-34**, **CA-35**, **CA-36**. Mobile cells reuse CA-12 and CA-27 unchanged.

Dependency notes:

- **CA-10 before any figure.** No figure shows a channel until an agent has chosen one.
- **CA-11 shares no code with the solver.** If it reused the table algebra, a bug in the
  algebra could pass its own check.
- **CA-31 before the demonstration runbook.** A map supplied at run time must pass the
  same validation as the prepared ones.
- **CA-35 reads only validated plans.** The stability cost comes from the evaluator's
  record of epoch `t - 1`, never from an agent's internal state.
- **The 29-region map stays a limit case.** It shows `budget_exceeded`; no item promises
  to solve it.
