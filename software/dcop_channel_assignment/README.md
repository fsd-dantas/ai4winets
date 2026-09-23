# Wireless channel assignment domain foundation

Status: implemented domain contracts, fixtures, message transport, distributed DFS and
upward UTIL propagation. VALUE reconstruction remains planned. This package has no ECoRA imports. Its DCOP core uses only the Python standard
library; optional geographic adapters use Shapely for geometry and NetworkX for graph
validation, not for channel allocation.

## First implementation decisions

- Python 3.11 or newer, immutable dataclasses and exact integer costs. No agent framework,
  ontology reasoner, expert-system engine or third-party optimization solver is required.
- `wireless.py` owns region/AP identity, four abstract channels and synthetic channel
  scores. Coordinates are integers and regions are interior-disjoint rectangles. Shared
  boundary segments generate edges; corner contact does not. Connectivity is validated.
  The representation guarantees planarity by construction, rather than accepting an
  arbitrary graph and assuming it is planar. `geography.py` separately supports GeoJSON
  Polygon/MultiPolygon maps, rejecting invalid geometry, interior overlaps, disconnected
  graphs and nonplanar adjacency. `curitiba.py` builds sourced municipal inputs and previews.
- `dcop.py` owns generic variables, dense factors, assignments, explicit forbidden costs
  and local input views. Factors declare axis order; the last axis varies fastest. Scalar
  factors have empty scope and exactly one entry. Costs serialize as nonnegative integers
  or `"forbidden"`; null, booleans and non-finite JSON numbers are rejected.
- `translation.py` is the boundary between the two domains. It emits one variable and
  unary factor per AP, and one inequality factor per unordered adjacency edge. Both
  endpoints can see their shared constraint. Runtime factor ownership at the deeper
  pseudo-tree endpoint is computed by each agent after DFS and independently validated;
  visibility is not ownership.
- `fixtures.py` supplies the 12-region map and smaller grid maps, with zero costs or
  competing shared channel preferences. All data is synthetic. These grids use only a
  subset of possible planar structures and are not yet a representative experiment set.

The harness can evaluate an instance cost, but this method is not an agent decision
procedure or the future independent evaluator. A local view exposes only the agent's
variable, neighboring variable domains and incident factors. The planned execution harness
must pass only these views, not a global instance, into agents.

## Verify from the repository root

PowerShell:

```powershell
$env:PYTHONPATH = 'software'
python -m unittest discover -s tests -p test_dcop_domain.py -v
```

Linux/macOS:

```sh
PYTHONPATH=software python -m unittest discover -s tests -p test_dcop_domain.py -v
```

The checks independently enumerate all 256 assignments of a four-agent fixture to verify
translation preserves costs and forbidden assignments. Other checks exercise geometry,
invalid inputs, local visibility, immutable inputs, serialization and order independence.
They do not establish DPOP correctness because its protocol is not implemented yet.

Table joins/projection and UTIL propagation are implemented. Next: VALUE reconstruction
(CA-10). See the [architecture](../../docs/dcop-channel-assignment/architecture.md).

The optional [Curitiba map package](../../data/geography/curitiba-metropolitan/README.md)
contains source provenance, reproduction commands and the geographic validation results.

## Inspect distributed DFS

```powershell
$env:PYTHONPATH = 'software'
.\.venv\Scripts\python.exe -m dcop_channel_assignment --geojson data/geography/curitiba-metropolitan/central-core-14.geojson --root ap-4106902 --trace
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_dcop*.py' -v
```

Without `--geojson`, the command uses the 12-region synthetic grid and needs no map
dependencies. The default root is the lowest agent ID; the command above explicitly
selects Curitiba. Output contains parent/child relationships, ancestors, pseudo-neighbors,
separators, factor ownership and optionally every delivered message. Without `--util`,
the command stops after pseudo-tree construction.

`AgentSession` receives only a local view and a send port. An agent probes neighbors in
sorted order, one at a time. An unvisited neighbor adopts the received ancestor path and
explores its own neighbors. Completed descendants answer later ancestor probes with SEEN;
child RETURN messages carry subtree separator identifiers. Each agent combines these with
its ancestor neighbors to derive its separator locally. Agents progress NEW -> DFS ->
READY_FOR_UTIL. With UTIL enabled, agents then enter WAITING_FOR_CHILD_UTIL and UTIL_COMPLETE;
entry-budget failures enter BUDGET_EXCEEDED. VALUE execution is still rejected.

`QueueTransport` provides reliable FIFO delivery and rejects duplicate identities,
cross-run messages and unknown endpoints. Agents also validate peer identity, phase and
DFS scopes. These are protocol integrity checks, not cryptographic authentication or
Byzantine fault tolerance. The harness chooses the root, wires local views, drains messages
and independently validates the finished tree; it does not direct traversal choices.
No leader-election algorithm, timeout/recovery or lossy transport is claimed.

## Cost-table operations

`tables.join(factors, table_id=..., max_entries=...)` sums costs over the union of factor
scopes. Output variable and value IDs are lexicographically ordered; input axis orders
may differ. Shared domains must contain the same values, and factor IDs cannot repeat.
Joining no factors returns the scalar zero, while forbidden costs remain absorbing.

`tables.minimize(factor, variable_id, table_id=..., max_entries=...)` returns a projected
factor and an immutable conditional-choice table. Equal finite costs choose the lowest
value ID. A forbidden context has no choice, represented by `None` rather than a fabricated
channel. `Projection.choice_for(Assignment(...))` requires exactly the residual scope.

Both operations require an explicit positive entry budget. A join checks its union
cardinality before enumerating output assignments; minimization also checks its input
cardinality. `TableBudgetExceeded` records required entries and the limit, and is distinct
from a forbidden/infeasible result. The limit applies to each table, not aggregate Python
memory or elapsed time; those execution limits remain a later milestone. These operations
are invoked locally during upward UTIL propagation.

## Compute the root cost through UTIL

```powershell
$env:PYTHONPATH = 'software'
.\.venv\Scripts\python.exe -m dcop_channel_assignment --geojson data/geography/curitiba-metropolitan/central-core-14.geojson --root ap-4106902 --util --preferences --max-table-entries 1000000
```

The synthetic preference mode assigns every agent channel costs `(0,10,20,30)`; without
`--preferences` all costs are zero. The command above returns cost 140 and 13 UTIL messages.
This is an integration example, not a measured wireless benefit or a frozen study result.
No channel assignment is returned yet: conditional choices remain local to agents for
the later VALUE phase. `optimal_cost`, `infeasible` and `budget_exceeded` are distinct
outcomes. An infeasible cost serializes as `"forbidden"`; interrupted computation has
no cost (`null`). `--trace` includes delivered DFS and UTIL messages with explicit cost encoding.

## Interactive message replay

The [offline visualization](../../docs/dcop-channel-assignment/visualization.html) embeds
the actual 14-region integration trace and map geometry. Play, step backward/forward, drag
the timeline or jump to UTIL. Every step highlights sender/recipient and shows the first
12 rows of the current UTIL table; complete tables remain embedded in the HTML. Root cost
appears only after the final delivered message. Playback time is illustrative, not latency.

Regenerate from the repository root with map dependencies installed:

```powershell
$env:PYTHONPATH = 'software'
.\.venv\Scripts\python.exe -m dcop_channel_assignment.visualize
```

The viewer is read-only: it never chooses channels or changes the solver. It is an
integration demonstration, not a frozen study report. The default data uses synthetic
preferences, Curitiba as root and a 1,000,000-entry table budget. Geometry source hash and
settings are embedded. `#step=59` opens the first UTIL message; `#step=71` shows completion.
The HTML template is package data so regeneration also works from an installed package.

Each child table must match the separator established by DFS. Known variable domains
are checked against local inputs and prior child tables; remote ancestor domains are
learned from the child protocol under the cooperative, reliable-message assumption.
The harness transitions all agents to UTIL before draining queued messages; it supplies
no tables, choices or global costs. Agents wait for every child, join exactly their owned
factors with those child tables, minimize locally, and send one UTIL message to their parent.
The root's scalar is the global optimum when this complete phase finishes successfully.

With the same root and budget, the 29-region map requests a 4,194,304-entry intermediate
join and returns `budget_exceeded`, without claiming infeasibility or an optimum. Retained
messages are those successfully delivered before interruption. This table limit does not
provide process-level memory/time enforcement; CA-16 still owns those controls.

The current DFS adapter supports unary/binary factors only, matching the channel model;
generic scalar/higher-order factors are rejected explicitly. For connected admitted graphs,
this protocol sends two DFS messages per undirected edge. This is a count of logical
messages, not a measure of wire bytes or wireless airtime.
