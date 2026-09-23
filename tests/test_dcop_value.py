from itertools import combinations, product
import random
import unittest

from dcop_channel_assignment.agents import AgentSession, Phase, solve
from dcop_channel_assignment.dcop import Assignment, Cost, DcopInstance, Factor, Variable, inequality_factor
from dcop_channel_assignment.fixtures import grid_map
from dcop_channel_assignment.protocol import Explore, Kind, Message, ProtocolError, Return, SendPort
from dcop_channel_assignment.translation import to_dcop

CHANNELS = ('c1','c2','c3','c4')


def evaluate(instance, values):
    # Independent of the solver: direct table lookup, no join/minimize or DcopInstance.cost.
    total = 0
    for f in instance.factors:
        cost = f.costs[list(product(*f.domains)).index(tuple(values[n] for n in f.scope))].value
        if cost is None:
            return None
        total += cost
    return total


def optimum(instance):
    best = None
    for values in product(*(v.domain for v in instance.variables)):
        cost = evaluate(instance,dict(zip((v.id for v in instance.variables),values)))
        if cost is not None and (best is None or cost < best):
            best = cost
    return best


def complete_graph(n, *, missing=(), costs=None):
    vs = tuple(Variable(f'v{i}',CHANNELS) for i in range(n))
    fs = [inequality_factor(f'e{a}{b}',vs[a],vs[b]) for a,b in combinations(range(n),2)
          if (a,b) not in missing]
    if costs:
        fs.extend(Factor(f'u{i}',(v.id,),(CHANNELS,),tuple(Cost(c) for c in costs[i]))
                  for i,v in enumerate(vs))
    return DcopInstance(vs,tuple(fs))


class ValueTests(unittest.TestCase):
    def assert_value_protocol(self, instance, result):
        positions = {p.agent_id:p for p in result.tree.positions}
        values = [m for m in result.messages if m.kind == Kind.VALUE]
        self.assertEqual(len(values),len(instance.variables)-1)
        self.assertEqual(sorted(m.recipient for m in values),
                         sorted(n for n,p in positions.items() if p.parent is not None))
        channels = dict(result.assignment.values)
        for m in values:
            self.assertEqual(m.sender,positions[m.recipient].parent)
            context = dict(m.payload.values)
            self.assertEqual(tuple(sorted(context)),positions[m.recipient].separator)
            # A VALUE context repeats choices already made; it never proposes new ones.
            self.assertEqual(context,{n:channels[n] for n in context})

    def test_generated_instances_reconstruct_the_exact_optimum_for_every_root(self):
        rng = random.Random(72)
        outcomes = set()
        for case in range(30):
            vs = tuple(Variable(str(i),('b','a','c')) for i in range(4))
            edges = {(0,1),(1,2),(2,3)}
            edges.update((a,b) for a,b in ((0,2),(0,3),(1,3)) if rng.choice((False,True)))
            fs = [Factor('unary-'+v.id,(v.id,),(v.domain,),tuple(Cost(rng.randrange(10)) for _ in v.domain)) for v in vs]
            # Odd cases are forbidden-heavy so that some instances have no feasible assignment.
            entries = (None,None,None,0,1) if case % 2 else (None,0,1,4)
            for i,(a,b) in enumerate(sorted(edges)):
                fs.append(Factor('pair-'+str(i),(vs[b].id,vs[a].id),(vs[b].domain,vs[a].domain),
                                 tuple(Cost(rng.choice(entries)) for _ in range(9))))
            instance = DcopInstance(vs,tuple(fs))
            expected = optimum(instance)
            for root in vs:
                with self.subTest(case=case,root=root.id):
                    result = solve(instance,max_entries=81,root=root.id)
                    self.assertEqual(result.cost,Cost(expected))
                    outcomes.add(result.status)
                    if expected is None:
                        self.assertEqual(result.status,'infeasible')
                        self.assertIsNone(result.assignment)
                        self.assertFalse(any(m.kind == Kind.VALUE for m in result.messages))
                        continue
                    self.assertEqual(result.status,'optimal_cost')
                    channels = dict(result.assignment.values)
                    self.assertEqual(set(channels),{v.id for v in vs})
                    self.assertEqual(evaluate(instance,channels),expected)
                    self.assert_value_protocol(instance,result)
        # The generator must reach both outcomes, or one branch above is untested.
        self.assertEqual(outcomes,{'optimal_cost','infeasible'})

    def test_grid_maps_are_colored_without_conflict(self):
        for rows,columns,preferences,cost in [(1,1,False,0),(2,2,False,0),(3,4,False,0),
                                              (2,2,True,20),(3,4,True,60)]:
            with self.subTest(rows=rows,columns=columns,preferences=preferences):
                scenario = grid_map(rows,columns,preferences=preferences)
                instance = to_dcop(scenario)
                result = solve(instance,max_entries=4096)
                channels = dict(result.assignment.values)
                self.assertEqual(result.cost,Cost(cost))
                self.assertEqual(evaluate(instance,channels),cost)
                self.assertEqual([e for e in scenario.edges if channels[e[0]] == channels[e[1]]],[])
                self.assert_value_protocol(instance,result)

    def test_ties_choose_the_lowest_channel(self):
        result = solve(to_dcop(grid_map(1,3)),max_entries=64)
        self.assertEqual(result.assignment.values,(('ap-00','c1'),('ap-01','c2'),('ap-02','c1')))

    def test_k5_is_infeasible_with_four_channels_under_every_root(self):
        rng = random.Random(5)
        for costs in (None,[[rng.randrange(101) for _ in CHANNELS] for _ in range(5)]):
            instance = complete_graph(5,costs=costs)
            self.assertIsNone(optimum(instance))
            for root in instance.variables:
                with self.subTest(costs=costs is not None,root=root.id):
                    result = solve(instance,max_entries=1024,root=root.id)
                    self.assertEqual(result.status,'infeasible')
                    self.assertEqual(result.cost,Cost(None))
                    self.assertIsNone(result.assignment)
                    self.assertFalse(any(m.kind == Kind.VALUE for m in result.messages))

    def test_k5_minus_an_edge_and_k4_are_feasible(self):
        near = complete_graph(5,missing={(0,1)})
        for root in near.variables:
            channels = dict(solve(near,max_entries=1024,root=root.id).assignment.values)
            self.assertEqual(evaluate(near,channels),0)
            # v2-v4 form a triangle using three colors; v0 and v1 border all three, so both
            # must take the fourth.
            self.assertEqual(channels['v0'],channels['v1'])
        channels = dict(solve(complete_graph(4),max_entries=1024).assignment.values)
        self.assertEqual(sorted(channels.values()),list(CHANNELS))

    def test_deterministic_under_input_reordering(self):
        instance = to_dcop(grid_map(2,3,preferences=True))
        reverse = DcopInstance(tuple(reversed(instance.variables)),tuple(reversed(instance.factors)))
        self.assertEqual(solve(instance,max_entries=4096),solve(reverse,max_entries=4096))

    def test_budget_stop_returns_no_assignment(self):
        result = solve(to_dcop(grid_map(2,2)),max_entries=4)
        self.assertEqual(result.status,'budget_exceeded')
        self.assertIsNone(result.cost)
        self.assertIsNone(result.assignment)

    def test_agent_validates_value_sender_phase_scope_and_domain(self):
        # Middle agent of a 1x3 path, driven by hand: parent ap-00, child ap-02.
        instance = to_dcop(grid_map(1,3))
        sent = []
        agent = AgentSession('r',instance.local_view('ap-01'),SendPort(sent.append))
        good = Message('r','ap-00','ap-01',1,Kind.VALUE,Assignment((('ap-00','c1'),)))
        agent.receive(Message('r','ap-00','ap-01',0,Kind.EXPLORE,Explore(('ap-00',))))
        agent.receive(Message('r','ap-02','ap-01',0,Kind.RETURN,Return(('ap-01',))))
        with self.assertRaises(ProtocolError):
            agent.receive(good)  # before UTIL
        agent.start_util(max_entries=64)
        agent.receive(Message('r','ap-02','ap-01',1,Kind.UTIL,
                              Factor('util',('ap-01',),(CHANNELS,),(Cost(0),)*4)))
        self.assertEqual(agent.phase,Phase.UTIL_DONE)
        with self.assertRaises(ProtocolError):
            agent.start_value()  # not the root
        for bad in (Message('r','ap-02','ap-01',2,Kind.VALUE,Assignment((('ap-00','c1'),))),
                    Message('r','ap-00','ap-01',2,Kind.VALUE,Assignment((('ap-02','c1'),))),
                    Message('r','ap-00','ap-01',2,Kind.VALUE,Assignment((('ap-00','c1'),('ap-02','c1')))),
                    Message('r','ap-00','ap-01',2,Kind.VALUE,Assignment((('ap-00','c9'),)))):
            with self.subTest(bad=bad), self.assertRaises(ProtocolError):
                agent.receive(bad)
        self.assertEqual(agent.phase,Phase.UTIL_DONE)
        agent.receive(good)
        self.assertEqual((agent.phase,agent.value),(Phase.ASSIGNED,'c2'))
        self.assertEqual(sent[-1],Message('r','ap-01','ap-02',sent[-1].sequence,Kind.VALUE,
                                          Assignment((('ap-01','c2'),))))
        with self.assertRaises(ProtocolError):
            agent.receive(Message('r','ap-00','ap-01',3,Kind.VALUE,Assignment((('ap-00','c2'),))))
