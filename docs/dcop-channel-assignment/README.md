# Distributed channel assignment as map coloring with DPOP

**Status: architecture and research question fixed; domain foundation and the full
DFS/UTIL/VALUE solve implemented and tested; the independent evaluator, the colored-map
demonstration, mobile-cell epochs and all results remain planned. Revision: 0.3. Date: 2026-09-23.**

## What is this study?

**Agents, one per coverage region, color a planar map's regions with four colors so that no
two neighboring regions share one, using only messages to their neighbors and an original
implementation of the Distributed Pseudotree Optimization Procedure (DPOP).** Read as a
wireless problem, the same computation assigns one of four channels to each region's access
point so that neighboring cells do not reuse a channel. The same solver then minimizes a
synthetic channel-busyness cost under the same hard constraints, and re-plans when a mobile
cell arrives or moves, preferring to leave existing channels where they are.

The map is the explanation, not a simplification: a map makes adjacency, conflicts and the
agents' local view visible at a glance, and every map element has a direct wireless reading.

The study sits within the repository's theme as multi-agent AI applied to a wireless
coordination problem: a distributed constraint optimization problem (DCOP), solved exactly
by cooperating agents that never see the whole network. It is a standalone study, not an
ECoRA stage and not a change to ECoRA's contracts.

## Reading guide

| Document | Purpose |
| --- | --- |
| This page | Problem, research questions, claims, system model and protocol |
| [Architecture](architecture.md) | Bounded contexts, agent lifecycle, DFS/UTIL/VALUE protocol, invariants and decisions |
| [Package](../../software/dcop_channel_assignment/README.md) | Implemented modules, commands and verification |
| [Curitiba inputs](../../data/geography/curitiba-metropolitan/README.md) | Sourced municipal boundaries and their provenance |
| [Protocol replay](visualization.html) | Offline replay of actual DFS/UTIL messages on the 14-region map |

The replay shows protocol activity, not channel assignments. Colors there identify senders,
recipients and phases. The colored map is drawn once the evaluator and demonstration land.

## Purpose and provenance

This design originated in a structured learning context and has been adapted as an
independent, reproducible research artifact. It is not an institutional submission or a
validated research result, and instructional material and assessment details are not
reproduced. Artifact type: implementation with correctness validation and a descriptive
demonstration; a comparative study is a declared, deferred extension.

Research relevance: cooperative resource allocation among autonomous network elements, a
building block for the repository's assurance directions. The initial model does not measure
service deadlines, resilience, multi-RAT behavior or self-healing.

## One problem, read two ways

| Map coloring | Wireless channel assignment | Model element |
| --- | --- | --- |
| Region of a map | Coverage region, one access point (AP) and one agent | Variable `x_i`, owned by agent `i` |
| Color | Abstract orthogonal channel | Domain `C = {c1, c2, c3, c4}` |
| Two regions share a border | Neighboring cells risk co-channel interference | Hard binary constraint `f_ij` |
| Dual graph of the map | Surrogate interference graph | Simple, connected, planar `G = (V, E)` |
| Four-color theorem | Four channels always suffice on a planar surrogate | Feasibility guaranteed on admitted maps |
| Color preference | Synthetic channel-busyness score | Optional unary cost `u_i(c)` |

The surrogate is deliberate and bounded. Real interference graphs can be nonplanar and
SINR-dependent, and administrative geography is not radio coverage. The four channels are
abstract, not a claim about non-overlapping channels in any real band.

## Research questions

**Primary question: can agents that each control one region's color, and exchange only
DFS, UTIL and VALUE messages with their neighbors, compute a four-coloring of a simple,
connected, planar map with at least ten regions in which no two adjacent regions share a
color, verified independently of the solver?**

- **RQ1 — Validity.** Does the distributed solve produce a complete, conflict-free
  coloring, with no agent reading another agent's state and no centralized coloring step?
- **RQ2 — Optimality under channel costs.** With synthetic channel-busyness scores, does
  the same solver return a minimum-cost conflict-free channel plan, and where does that plan
  differ from each AP independently choosing its cheapest channel?
- **RQ3 — Cost of coordination.** How do the pseudo-tree's separator sizes determine UTIL
  table sizes and message volume on the demonstration maps?
- **RQ4 — Mobile cells.** When a mobile cell enters or moves across the map, how many
  existing APs must change channel to restore a conflict-free plan, with and without a
  cost that favors keeping each AP's current channel?

## Claims and the evidence each needs

| Claim | Kind | Evidence that settles it |
| --- | --- | --- |
| **C1** Every admitted map is colored with zero conflicts | Correctness | Independent evaluator on every demonstration map and generated small instance |
| **C2** The solver's cost equals the exact optimum, and an infeasible instance is reported as infeasible | Correctness | Exhaustive enumeration on instances of 2 to 8 agents; K5 with four colors as the certified-infeasible case |
| **C3** Independent choice can violate the constraints that coordination satisfies | Illustrative | Conflicts of the independent baseline on the same maps and costs, reported beside DPOP's |
| **C4** Table size follows the separator, not the region count | Descriptive | Separator sizes, largest tables and message counts per phase on the demonstration maps |
| **C5** A stability cost reduces reassignment when a mobile cell moves, at no loss of validity | Descriptive | Reassignments and conflicts across a declared sequence of mobile-cell snapshots, solved with and without the stability cost |

C1 is guaranteed to be achievable by the four-color theorem; what it tests is the
implementation. C2 is an implementation check, not a novelty claim. C3 is illustrative:
the independent baseline is a deliberately uncoordinated lower bound on local cost, not a
competing solver, and no claim says DPOP beats it on unconstrained cost. C4 and C5 are
descriptive and make no causal claim beyond the declared instances.

**Not claimed:** throughput, packet loss, SINR, airtime or service-assurance gains; behavior
during a solve while costs or topology change, under lost messages or on nonplanar
interference; performance on real radio data. Mobile cells are handled by re-solving
between moves, not by an incremental or dynamic DCOP algorithm.

## System model

Each region holds one AP and one agent. An edge joins two regions that share a boundary
segment of positive length; corner-only contact creates no edge. Every admitted map is
simple, connected and planar, and its adjacency derives from its geometry.

Each agent `i` owns one variable `x_i` in `C`. For each unordered edge `{i, j}`:

`f_ij(a, b) = forbidden (+infinity) if a = b, and 0 otherwise`

The objective is:

`minimize F(x) = sum_i u_i(x_i) + sum_{unordered {i,j} in E} f_ij(x_i, x_j)`

Each edge is counted once. Forbidden is an explicit value with defined arithmetic and its own
serialization, never a large finite penalty, so no finite optimum can hide a conflict. All
agents cooperate on this one objective; local scores do not define a strategic game.

Two modes share one solver:

1. **Map coloring:** all unary costs are zero. Any conflict-free coloring is optimal, with cost 0.
2. **Channel cost optimization:** unary scores vary from 0 to 100; the solver minimizes
   their sum subject to the same hard constraints.

Costs and topology are static during a solve. Messages travel over a reliable, lossless,
ordered logical transport that does not depend on the channels being assigned. This models
coordination over a separate control path; its message counts are not wireless airtime.

### Mobile cells: re-planning over snapshots

A mobile cell is a coverage region that moves: a cell on wheels, a vehicle-mounted or an
airborne cell deployed where the fixed network needs support. Its movement is modeled as a
declared sequence of epochs. Each epoch `t` has its own validated map `M_t`, in which the
mobile cell is one region of the partition with its own agent, and the solver runs once per
epoch, from scratch, on a static instance. Nothing moves during a solve.

Changing an AP's channel disrupts its users, so each epoch after the first may add a
stability cost for every AP that already held a channel:

`u_i^t(c) = u_i(c) + s if c != x_i^(t-1), and u_i(c) otherwise`

With `s = 0` the plan is re-optimized freely. With `s > 100 x |V_t|`, one avoided
reassignment outweighs any possible difference in channel scores, so the solver first
minimizes the number of reassignments and then the score. The mobile cell itself has no
previous channel and carries no stability cost. This stays inside the static model: a
stability cost is an ordinary unary cost, so no protocol change is needed.

While the mobile cell is a region of a planar partition, four channels still always suffice.
A mobile cell that overlaps existing coverage would add edges that can make the graph
nonplanar, and then four channels may not suffice. That case is outside the core; it is
where the K5 validation instance stops being a test fixture and becomes a real outcome, and
it is kept as an optional successor study.

## Why DPOP

DPOP is exact, uses three message phases with a linear number of messages, and concentrates
its cost in table size, which grows exponentially with the separator width. That makes its
correctness checkable against enumeration and its resource use explainable from the
pseudo-tree alone, which is what RQ3 asks. The alternative, ADOPT, uses small messages but an
exponential number of them and asynchronous search that is harder to verify step by step.
The algorithm follows Petcu and Faltings (2005); the [architecture](architecture.md#decisions)
records this and the other design decisions.

## Demonstration and validation instances

| Instance | Regions | Edges | Role | Status |
| --- | --- | --- | --- | --- |
| Synthetic 3 x 4 grid | 12 | 17 | Hand-sized demonstration; zero and preference costs | solved, tested |
| Curitiba Central Urban Core | 14 | 29 | Primary demonstration on real municipal geography | solved, tested |
| Curitiba metropolitan area | 29 | 66 | Limit case: shows the exponential table cost | UTIL stops with `budget_exceeded` |
| Hand-authored map | at least 10 | as drawn | A map supplied at presentation time, validated before solving | planned |
| Small trace map | 5 | with one non-tree edge | Every UTIL table and VALUE message checkable by hand | planned |
| Mobile-cell sequence | fixed regions + 1 mobile | per epoch | A mobile cell crossing a map in declared epochs (RQ4) | planned |
| K5 with four colors | 5 | 10 | Certified infeasible; not a map, since K5 is nonplanar | tested |
| K5 minus one edge | 5 | 9 | Feasible counterpart one edge away | tested |

Figures from the current integration checks, with a 1,000,000-entry table budget:

| Instance | Root | Largest separator | Largest joined table | DFS messages | Outcome |
| --- | --- | --- | --- | --- | --- |
| 3 x 4 grid | lowest ID | 4 | 1,024 | 34 | optimal cost (0; 60 with preferences) |
| Central Urban Core | lowest ID | 5 | 4,096 | 58 | optimal cost 0 |
| Central Urban Core | Curitiba | 6 | 16,384 | 58 | optimal cost 0 |
| Metropolitan area | lowest ID | 11 | stops at 1,048,576 | 132 | `budget_exceeded`; next join needs 16,777,216 |
| Metropolitan area | Curitiba | 10 | stops at 65,536 | 132 | `budget_exceeded`; next join needs 4,194,304 |

These are software integration checks, not frozen results. They already show C4's point on
the same map: changing only the root changes the largest table fourfold. The 29-region map
cannot complete in the pure-Python table algebra at any practical budget, so it is the
demonstration of DPOP's limit, not of its answer.

K5 and its one-edge counterpart are built directly as DCOP instances. The map layer
correctly rejects K5 as nonplanar, and the solver core does not depend on planarity.

## Protocol

### Declared values (nominal, uncalibrated)

This block is the single source of numeric settings. A change records its rationale.

| Parameter | Value |
| --- | --- |
| Colors / channels | 4 abstract values, ordered `c1 < c2 < c3 < c4` |
| Tie rule | Lowest channel ID among equal costs, at every agent |
| Root policy | Lowest agent ID unless a run declares a root |
| Neighbor order | Ascending agent ID |
| Table budget | 1,000,000 entries per materialized table |
| Cost scale | Integers 0 to 100, arbitrary units |
| Preference profiles | Shared: every AP scores `(0, 10, 20, 30)`; independent: per-AP seeded scores |
| Exact reference | Exhaustive enumeration, instances of 2 to 8 agents |
| Stability cost `s` | `0` (free re-optimization) and 101 x the epoch's region count (reassignments minimized first) |
| Mobile-cell epochs | At least 3 declared snapshots: arrival, one move, departure |

### Runs

1. **Correctness suite.** Generated small instances and K5 cases, each solved under every
   root and compared with exhaustive enumeration (C2). Order of variables, factors and
   children must not change the optimal cost.
2. **Demonstration runs.** Each demonstration map in both modes. The evaluator checks every
   returned assignment (C1); the independent baseline runs on the same map and costs (C3).
   Runs are deterministic, so one run per map, mode and root is the complete record.
3. **Resource description.** For each demonstration run, separator sizes, the largest
   outgoing and intermediate tables, and message counts per phase (C4), under two roots.
4. **Mobile-cell sequence.** Each epoch solved in order, once with `s = 0` and once with the
   dominant stability cost, both starting from the same first-epoch plan (C5).

### Metrics

- Completeness, conflict count and conflict rate (`conflicting edges / total edges`).
- Total unary cost of a feasible assignment; for the baseline, its conflicts and its unary
  score, the latter never treated as a feasible objective value.
- Messages by phase (DFS, UTIL, VALUE), transmitted table entries, largest separator,
  largest outgoing table and largest intermediate table.
- Reassignments between consecutive epochs: APs present in both whose channel changed.
- Outcome: `optimal_cost`, `infeasible`, `budget_exceeded` or execution error. A budget stop
  is never reported as infeasibility; an infeasible result is never given an assignment.

Timing and process memory are not RQ3 metrics: agents share one process, so table entries
are the reported resource measure.

## Deferred extension: a comparative study

Declared so that it cannot be mistaken for part of the core claims. It starts only after the
core milestones close, with its own frozen protocol:

- **Question.** Across planar structures and cost profiles, how often does independent
  selection conflict, and how does separator width relate to UTIL burden?
- **Matrix.** 4 sizes (10, 12, 16, 20) x 2 density strata x 3 maps x 2 cost profiles x 10
  paired seeds x 2 arms = 960 runs, after a pilot of at most 24 runs.
- **Controls.** Separate random streams for topology and costs; paired arms; actual density
  and separator widths recorded rather than inferred from stratum labels; cost seeds nested
  within maps in the analysis; 95% intervals with the estimator frozen after the pilot.

It is deferred and is not part of the core study.

## Delivery and reproducibility

The package lives in `software/dcop_channel_assignment/`. When runs produce evidence, the
experiment directory `experiments/001-dcop-channel-assignment/` will hold commands, pinned
dependencies, inputs with hashes, raw message traces, assignments, outcomes and the figures
regenerated from them; verify the numeric ID is free when it is created. No placeholder
directory is created now.

Completion of the core means: every demonstration map colored and independently verified,
the correctness suite passing against enumeration, a hand-checkable trace, and the colored
map regenerated from recorded runs. A successful solver exit alone is not completion.

## References

- A. Petcu and B. Faltings, [A Scalable Method for Multiagent Constraint Optimization](https://jmvidal.cse.sc.edu/library/petcu05a.pdf), IJCAI 2005. The algorithm is implemented from this specification; no solver code is vendored.
- Wireless channel allocation as a distributed optimization problem: [Channel allocation algorithms for WLANs using distributed optimization](https://doi.org/10.1016/j.aeue.2011.10.012), AEU, 2012.
