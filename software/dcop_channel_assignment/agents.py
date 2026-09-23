"""Local-state distributed DFS and upward UTIL propagation."""

from dataclasses import dataclass
from enum import Enum

from .dcop import Cost, DcopInstance, Factor, LocalView, identifier
from .tables import TableBudgetExceeded, check_size, join, minimize
from .protocol import Explore, Kind, Message, MessagePort, ProtocolError, QueueTransport, Return, Seen, SendPort


class Phase(str, Enum):
    NEW = 'new'
    DFS = 'dfs'
    READY = 'ready_for_util'
    UTIL = 'waiting_for_child_util'
    UTIL_DONE = 'util_complete'
    FAILED = 'budget_exceeded'


@dataclass(frozen=True)
class TreePosition:
    agent_id: str
    parent: str | None
    ancestors: tuple[str, ...]
    children: tuple[str, ...]
    pseudo_parents: tuple[str, ...]
    pseudo_children: tuple[str, ...]
    separator: tuple[str, ...]
    owned_factors: tuple[str, ...]


class AgentSession:
    def __init__(self, run_id: str, view: LocalView, port: MessagePort):
        identifier(run_id)
        self.run_id, self.view, self.port = run_id, view, port
        self.id = view.variable.id
        self.neighbors = tuple(sorted(v.id for v in view.neighbors))
        domains = {v.id: v.domain for v in (view.variable, *view.neighbors)}
        if self.id in self.neighbors or len(set(self.neighbors)) != len(self.neighbors):
            raise ProtocolError('Local neighbors must be unique and exclude self')
        if len({f.id for f in view.factors}) != len(view.factors):
            raise ProtocolError('Duplicate local factor')
        for f in view.factors:
            if self.id not in f.scope or len(f.scope) not in (1, 2):
                raise ProtocolError('DFS adapter supports incident unary/binary factors only')
            if any(domains.get(n) != d for n, d in zip(f.scope, f.domains)):
                raise ProtocolError('Local factor scope/domain mismatch')
        self.phase = Phase.NEW
        self.parent = None
        self.ancestors = ()
        self.children = []
        self.pending = None
        self._remaining = []
        self._separator = set()
        self._sequence = 0
        self._received = set()
        self._child_separators = {}
        self._child_tables = {}
        self.projection = None
        self.max_join_entries = 0
        self._max_entries = None

    def _send(self, recipient, kind, payload):
        message = Message(self.run_id, self.id, recipient, self._sequence, kind, payload)
        self.port.send(message)
        self._sequence += 1

    def start(self):
        if self.phase != Phase.NEW:
            raise ProtocolError('Root already started')
        self._enter(())

    def _enter(self, ancestors):
        self.phase = Phase.DFS
        self.ancestors = ancestors
        self.parent = ancestors[-1] if ancestors else None
        self._remaining = [n for n in self.neighbors if n not in ancestors]
        self._separator = set(self.neighbors).intersection(ancestors)
        self._advance()

    def _advance(self):
        if self._remaining:
            self.pending = self._remaining.pop(0)
            self._send(self.pending, Kind.EXPLORE, Explore((*self.ancestors, self.id)))
        else:
            self.pending = None
            self.phase = Phase.READY
            if self.parent is not None:
                self._send(self.parent, Kind.RETURN, Return(tuple(sorted(self._separator))))

    def receive(self, message: Message):
        if message.run_id != self.run_id or message.recipient != self.id:
            raise ProtocolError('Wrong run or recipient')
        if message.sender not in self.neighbors:
            raise ProtocolError('Sender is not a local neighbor')
        key = (message.sender, message.sequence)
        if key in self._received:
            raise ProtocolError('Duplicate delivery')
        if message.kind == Kind.EXPLORE:
            path = message.payload.path
            if self.phase == Phase.NEW:
                if self.id in path:
                    raise ProtocolError('Unvisited agent already in DFS path')
                self._received.add(key)
                self._enter(path)
            elif self.phase == Phase.READY and message.sender in self.ancestors:
                if path != self.ancestors[:self.ancestors.index(message.sender)+1]:
                    raise ProtocolError('Probe does not match ancestor path')
                self._received.add(key)
                self._send(message.sender, Kind.SEEN, Seen())
            else:
                raise ProtocolError('Unexpected DFS probe for current phase')
        elif message.kind in (Kind.RETURN, Kind.SEEN):
            if self.phase != Phase.DFS or message.sender != self.pending:
                raise ProtocolError('Unexpected DFS response')
            if message.kind == Kind.RETURN:
                separator = set(message.payload.separator)
                if self.id not in separator or not separator <= {*self.ancestors, self.id}:
                    raise ProtocolError('Child separator contains invalid ancestor scope')
                self.children.append(message.sender)
                self._child_separators[message.sender] = message.payload.separator
                self._separator.update(separator - {self.id})
            self._received.add(key)
            self._advance()
        elif message.kind == Kind.UTIL:
            self._receive_util(message)
            self._received.add(key)
        else:
            raise ProtocolError('VALUE execution is not implemented')

    def position(self) -> TreePosition:
        if self.phase not in (Phase.READY, Phase.UTIL, Phase.UTIL_DONE, Phase.FAILED):
            raise ProtocolError('Pseudo-tree position is not complete')
        above = set(self.ancestors)
        owned = tuple(sorted(f.id for f in self.view.factors
                             if set(f.scope) - {self.id} <= above))
        return TreePosition(self.id, self.parent, self.ancestors, tuple(self.children),
                            tuple(n for n in self.neighbors if n in above and n != self.parent),
                            tuple(n for n in self.neighbors if n not in above and n not in self.children),
                            tuple(sorted(self._separator)), owned)

    def start_util(self, *, max_entries: int):
        if self.phase != Phase.READY:
            raise ProtocolError('UTIL requires a completed DFS and starts only once')
        check_size((), max_entries)
        self._max_entries = max_entries
        self.phase = Phase.UTIL
        self._compute_util_if_ready()

    def _receive_util(self, message):
        if self.phase != Phase.UTIL or message.sender not in self.children:
            raise ProtocolError('UTIL must come from a child during UTIL phase')
        if message.sender in self._child_tables:
            raise ProtocolError('Child already supplied a UTIL table')
        table = message.payload
        if table.scope != self._child_separators[message.sender]:
            raise ProtocolError('UTIL scope differs from child DFS separator')
        if any(tuple(sorted(d)) != d for d in table.domains):
            raise ProtocolError('UTIL domains must be canonical')
        known = {v.id:tuple(sorted(v.domain)) for v in (self.view.variable,*self.view.neighbors)}
        for previous in self._child_tables.values():
            known.update(zip(previous.scope, previous.domains))
        if any(n in known and known[n] != d for n,d in zip(table.scope,table.domains)):
            raise ProtocolError('UTIL domain disagrees with local or prior child domain')
        try:
            check_size(table.domains, self._max_entries)
        except TableBudgetExceeded:
            self.phase = Phase.FAILED
            raise
        self._child_tables[message.sender] = table
        self._compute_util_if_ready()

    def _compute_util_if_ready(self):
        if len(self._child_tables) != len(self.children):
            return
        owned = set(self.position().owned_factors)
        # Namespace local and child contributions to avoid collisions with caller factor IDs.
        factors = [Factor(f'local-{i}',f.scope,f.domains,f.costs)
                   for i,f in enumerate(self.view.factors) if f.id in owned]
        factors.extend(Factor(f'child-{i}',f.scope,f.domains,f.costs)
                       for i,(_,f) in enumerate(sorted(self._child_tables.items())))
        if not any(self.id in f.scope for f in factors):
            # An isolated variable without a unary cost still has a domain and zero cost.
            try:
                check_size((self.view.variable.domain,), self._max_entries)
            except TableBudgetExceeded:
                self.phase = Phase.FAILED
                raise
            factors.append(Factor('domain-zero',(self.id,),(self.view.variable.domain,),
                                  tuple(Cost(0) for _ in self.view.variable.domain)))
        try:
            joined = join(factors,table_id=f'joined-{self.id}',max_entries=self._max_entries)
            self.max_join_entries = len(joined.costs)
            projection = minimize(joined,self.id,table_id=f'util-{self.id}',max_entries=self._max_entries)
        except TableBudgetExceeded:
            self.phase = Phase.FAILED
            raise
        if projection.table.scope != tuple(sorted(self._separator)):
            raise ProtocolError('Computed UTIL scope differs from own DFS separator')
        self.projection = projection
        self.phase = Phase.UTIL_DONE
        if self.parent is not None:
            self._send(self.parent,Kind.UTIL,projection.table)


@dataclass(frozen=True)
class PseudoTreeResult:
    run_id: str
    root: str
    positions: tuple[TreePosition, ...]
    messages: tuple[Message, ...]


def build_pseudotree(instance: DcopInstance, *, run_id='dfs-demo', root=None) -> PseudoTreeResult:
    """Composition/evaluation harness; all traversal choices are made inside agents."""
    return _prepare(instance,run_id=run_id,root=root)[2]


def _prepare(instance, *, run_id, root):
    if any(len(f.scope) not in (1, 2) for f in instance.factors):
        raise ProtocolError('Pseudo-tree harness supports unary/binary instances only')
    names = sorted(v.id for v in instance.variables)
    root = names[0] if root is None else root
    if root not in names:
        raise ProtocolError('Unknown root')
    transport = QueueTransport(run_id)
    agents = {n: AgentSession(run_id, instance.local_view(n), SendPort(transport.send)) for n in names}
    for name, agent in agents.items():
        transport.register(name, agent.receive)
    agents[root].start()
    transport.drain()
    if any(a.phase != Phase.READY for a in agents.values()):
        raise ProtocolError('DFS failed to span all agents (disconnected instance)')
    result = PseudoTreeResult(run_id, root, tuple(agents[n].position() for n in names), transport.trace)
    validate_pseudotree(instance, result)
    return agents, transport, result


@dataclass(frozen=True)
class UtilResult:
    status: str
    tree: PseudoTreeResult
    cost: Cost | None
    messages: tuple[Message, ...]
    max_join_entries: int
    required_entries: int | None = None
    entry_limit: int | None = None


def propagate_util(instance: DcopInstance, *, max_entries: int,
                   run_id='util-demo', root=None) -> UtilResult:
    check_size((),max_entries)
    agents, transport, tree = _prepare(instance,run_id=run_id,root=root)
    try:
        # Lifecycle barrier only: every agent uses its own DFS state and child messages.
        # FIFO delivery begins after all agents are ready to accept the new phase.
        for agent in agents.values():
            agent.start_util(max_entries=max_entries)
        transport.drain()
    except TableBudgetExceeded as exc:
        return UtilResult('budget_exceeded',tree,None,transport.trace,
                          max(a.max_join_entries for a in agents.values()),exc.required,exc.limit)
    if any(a.phase != Phase.UTIL_DONE for a in agents.values()):
        raise ProtocolError('UTIL phase stalled without completing all agents')
    cost = agents[tree.root].projection.table.at(())
    return UtilResult('infeasible' if cost.value is None else 'optimal_cost',tree,cost,
                      transport.trace,max(a.max_join_entries for a in agents.values()))


def validate_pseudotree(instance: DcopInstance, result: PseudoTreeResult):
    """Independent post-run checks; this evaluator never instructs agents."""
    positions = {p.agent_id: p for p in result.positions}
    names = {v.id for v in instance.variables}
    if set(positions) != names or len(positions) != len(result.positions):
        raise ProtocolError('Invalid pseudo-tree coverage')
    if [p.agent_id for p in result.positions if p.parent is None] != [result.root]:
        raise ProtocolError('Invalid pseudo-tree root')
    owners = []
    for p in result.positions:
        ancestors = []
        parent = p.parent
        while parent is not None:
            if parent not in positions or parent in ancestors or parent == p.agent_id:
                raise ProtocolError('Invalid parent chain')
            ancestors.append(parent)
            parent = positions[parent].parent
        if tuple(reversed(ancestors)) != p.ancestors:
            raise ProtocolError('Ancestor path mismatch')
        children = {q.agent_id for q in result.positions if q.parent == p.agent_id}
        if children != set(p.children) or len(children) != len(p.children):
            raise ProtocolError('Parent/child mismatch')
        neighbors = {v.id for v in instance.local_view(p.agent_id).neighbors}
        if not children <= neighbors or (p.parent is not None and p.parent not in neighbors):
            raise ProtocolError('Tree edge missing from constraint graph')
        for n in neighbors:
            if n not in p.ancestors and p.agent_id not in positions[n].ancestors:
                raise ProtocolError('Non-tree edge is not ancestor/descendant')
        if set(p.pseudo_parents) != neighbors.intersection(p.ancestors) - {p.parent}:
            raise ProtocolError('Pseudo-parent mismatch')
        if set(p.pseudo_children) != neighbors - set(p.ancestors) - children:
            raise ProtocolError('Pseudo-child mismatch')
        subtree = {n for n in names if n == p.agent_id or p.agent_id in positions[n].ancestors}
        boundary = {n for f in instance.factors if set(f.scope).intersection(subtree)
                    for n in f.scope if n not in subtree}
        if set(p.separator) != boundary:
            raise ProtocolError('Separator mismatch')
        expected = {f.id for f in instance.factors if p.agent_id in f.scope
                    and set(f.scope) - {p.agent_id} <= set(p.ancestors)}
        if set(p.owned_factors) != expected:
            raise ProtocolError('Factor owner mismatch')
        owners.extend(p.owned_factors)
    if sorted(owners) != sorted(f.id for f in instance.factors):
        raise ProtocolError('Factors must have exactly one owner')
