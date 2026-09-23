from itertools import product
import random
import unittest

from dcop_channel_assignment.agents import AgentSession, Phase, build_pseudotree, propagate_util
from dcop_channel_assignment.dcop import Cost, DcopInstance, Factor, Variable, inequality_factor
from dcop_channel_assignment.fixtures import grid_map
from dcop_channel_assignment.protocol import Kind, Message, ProtocolError, Return, SendPort
from dcop_channel_assignment.translation import to_dcop


def brute_force(instance):
    # Independent enumeration; no join/minimize or DcopInstance.cost calls.
    best = None
    for values in product(*(v.domain for v in instance.variables)):
        assignment = dict(zip((v.id for v in instance.variables),values))
        total = 0
        for f in instance.factors:
            row = list(product(*f.domains)).index(tuple(assignment[n] for n in f.scope))
            cost = f.costs[row].value
            if cost is None:
                break
            total += cost
        else:
            best = total if best is None else min(best,total)
    return Cost(best)


class UtilTests(unittest.TestCase):
    def test_generated_instances_match_exhaustive_reference_for_every_root(self):
        rng = random.Random(72)
        for case in range(30):
            vs = tuple(Variable(str(i),('b','a','c')) for i in range(4))
            edges = {(0,1),(1,2),(2,3)}
            edges.update((a,b) for a,b in ((0,2),(0,3),(1,3)) if rng.choice((False,True)))
            fs = [Factor('unary-'+v.id,(v.id,),(v.domain,),tuple(Cost(rng.randrange(10)) for _ in v.domain)) for v in vs]
            for i,(a,b) in enumerate(sorted(edges)):
                fs.append(Factor('pair-'+str(i),(vs[b].id,vs[a].id),(vs[b].domain,vs[a].domain),
                                 tuple(Cost(rng.choice((None,0,1,4))) for _ in range(9))))
            instance = DcopInstance(vs,tuple(fs))
            expected = brute_force(instance)
            for root in vs:
                with self.subTest(case=case,root=root.id):
                    result = propagate_util(instance,max_entries=81,root=root.id)
                    self.assertEqual(result.cost,expected)
                    self.assertEqual(result.status,'infeasible' if expected.value is None else 'optimal_cost')
                    messages = [m for m in result.messages if m.kind == Kind.UTIL]
                    self.assertEqual(len(messages),3)
                    positions = {p.agent_id:p for p in result.tree.positions}
                    for m in messages:
                        self.assertEqual(m.recipient,positions[m.sender].parent)
                        self.assertEqual(m.payload.scope,positions[m.sender].separator)

    def test_isolated_variable_without_cost_and_forbidden_singleton(self):
        v = Variable('v',('z','a'))
        result = propagate_util(DcopInstance((v,),()),max_entries=2)
        self.assertEqual(result.cost,Cost(0))
        self.assertEqual(result.messages,())
        forbidden = Factor('f',('v',),(v.domain,),(Cost(None),Cost(None)))
        result = propagate_util(DcopInstance((v,),(forbidden,)),max_entries=2)
        self.assertEqual(result.status,'infeasible')

    def test_budget_exhaustion_retains_dfs_and_has_no_cost(self):
        result = propagate_util(to_dcop(grid_map(2,2)),max_entries=4)
        self.assertEqual(result.status,'budget_exceeded')
        self.assertIsNone(result.cost)
        self.assertGreater(result.required_entries,result.entry_limit)
        self.assertGreater(len(result.messages),0)

    def test_color_conflicts_and_nonzero_costs_reach_optimum(self):
        instance = to_dcop(grid_map(2,2,preferences=True))
        result = propagate_util(instance,max_entries=256)
        self.assertEqual(result.cost,Cost(20))
        self.assertEqual(result.cost,brute_force(instance))

    def test_domain_and_scope_validation_precedes_table_acceptance(self):
        instance = to_dcop(grid_map(1,2))
        sent = []
        parent = AgentSession('r',instance.local_view('ap-00'),SendPort(sent.append))
        parent.start()
        parent.receive(Message('r','ap-01','ap-00',0,Kind.RETURN,Return(('ap-00',))))
        good = Factor('util',('ap-00',),(('c1','c2','c3','c4'),),(Cost(0),)*4)
        with self.assertRaises(ProtocolError):
            parent.receive(Message('r','ap-01','ap-00',1,Kind.UTIL,good))
        parent.start_util(max_entries=16)
        for bad in (Factor('bad',(),(),(Cost(0),)),
                    Factor('bad',('ap-00',),(('c1',),),(Cost(0),)),
                    Factor('bad',('ap-00',),(('c4','c3','c2','c1'),),(Cost(0),)*4)):
            with self.assertRaises(ProtocolError):
                parent.receive(Message('r','ap-01','ap-00',1,Kind.UTIL,bad))
        parent.receive(Message('r','ap-01','ap-00',1,Kind.UTIL,good))
        self.assertEqual(parent.phase,Phase.UTIL_DONE)
        with self.assertRaises(ProtocolError):
            parent.receive(Message('r','ap-01','ap-00',2,Kind.UTIL,good))

    def test_child_order_and_factor_order_do_not_change_result(self):
        instance = to_dcop(grid_map(2,3,preferences=True))
        reverse = DcopInstance(tuple(reversed(instance.variables)),tuple(reversed(instance.factors)))
        a = propagate_util(instance,max_entries=4096)
        b = propagate_util(reverse,max_entries=4096)
        self.assertEqual(a,b)
