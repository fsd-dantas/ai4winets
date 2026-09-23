from dataclasses import replace
from itertools import combinations
import unittest

from dcop_channel_assignment.agents import AgentSession, Phase, build_pseudotree, validate_pseudotree
from dcop_channel_assignment.dcop import Assignment, Cost, DcopInstance, Factor, Variable, inequality_factor
from dcop_channel_assignment.fixtures import grid_map
from dcop_channel_assignment.protocol import Explore, Kind, Message, ProtocolError, QueueTransport, Return, Seen, SendPort
from dcop_channel_assignment.translation import to_dcop


class AgentTests(unittest.TestCase):
    def test_single_agent_needs_no_messages(self):
        result = build_pseudotree(to_dcop(grid_map(1,1)))
        self.assertEqual(result.messages,())
        self.assertEqual(result.positions[0].owned_factors,('unary-0',))

    def test_cycle_has_back_edge_and_descendant_factor_owner(self):
        instance = to_dcop(grid_map(2,2))
        result = build_pseudotree(instance)
        positions = {p.agent_id:p for p in result.positions}
        self.assertEqual(positions['ap-02'].ancestors,('ap-00','ap-01','ap-03'))
        self.assertEqual(positions['ap-02'].pseudo_parents,('ap-00',))
        self.assertEqual(positions['ap-02'].separator,('ap-00','ap-03'))
        self.assertEqual(sum(len(p.owned_factors) for p in result.positions),len(instance.factors))
        self.assertTrue(any(m.kind == Kind.SEEN for m in result.messages))

    def test_all_four_node_connected_graphs_and_roots(self):
        variables = tuple(Variable(str(i),('a','b')) for i in range(4))
        edges = list(combinations(range(4),2))
        checked = 0
        for mask in range(1 << len(edges)):
            selected = [e for i,e in enumerate(edges) if mask & (1 << i)]
            reachable = {0}
            for _ in range(4):
                reachable |= {a for a,b in selected if b in reachable} | {b for a,b in selected if a in reachable}
            if len(reachable) != 4:
                continue
            instance = DcopInstance(variables,tuple(inequality_factor(str(i),variables[a],variables[b])
                                                  for i,(a,b) in enumerate(selected)))
            for root in variables:
                result = build_pseudotree(instance,root=root.id)
                self.assertEqual(sum(len(p.children) for p in result.positions),3)
                self.assertEqual(len(result.messages),2*len(selected))
                validate_pseudotree(instance,result)
                checked += 1
        self.assertEqual(checked,152)

    def test_deterministic_under_input_reordering(self):
        instance = to_dcop(grid_map())
        other = DcopInstance(tuple(reversed(instance.variables)),tuple(reversed(instance.factors)))
        self.assertEqual(build_pseudotree(instance),build_pseudotree(other))

    def test_transport_rejects_duplicate_unknown_and_cross_run(self):
        transport = QueueTransport('r')
        received = []
        transport.register('a',received.append)
        transport.register('b',received.append)
        message = Message('r','a','b',0,Kind.EXPLORE,Explore(('a',)))
        transport.send(message)
        for bad in (message,replace(message,run_id='other'),replace(message,recipient='c')):
            with self.assertRaises(ProtocolError):transport.send(bad)
        transport.drain()
        self.assertEqual(received,[message])
        self.assertEqual(transport.trace,(message,))

    def test_envelopes_reject_malformed_payloads(self):
        for kind,payload in [(Kind.RETURN,Seen()),(Kind.EXPLORE,Explore(('b',))),
                             (Kind.VALUE,Cost(0))]:
            with self.assertRaises(ProtocolError):Message('r','a','b',0,kind,payload)
        with self.assertRaises(ProtocolError):Return(('z','a'))

    def test_agent_rejects_wrong_run_peer_phase_and_scope(self):
        instance = to_dcop(grid_map(1,3))
        outgoing = []
        agent = AgentSession('r',instance.local_view('ap-00'),SendPort(outgoing.append))
        base = Message('r','ap-01','ap-00',0,Kind.RETURN,Return(('ap-00',)))
        for bad in (base,replace(base,run_id='other'),replace(base,sender='ap-02'),
                    Message('r','ap-01','ap-00',1,Kind.VALUE,Assignment((('ap-00','c1'),)))):
            with self.assertRaises(ProtocolError):agent.receive(bad)
        self.assertEqual(agent.phase,Phase.NEW)
        agent.start()
        with self.assertRaises(ProtocolError):
            agent.receive(replace(base,payload=Return(('ap-00','unknown'))))
        agent.receive(base)
        with self.assertRaises(ProtocolError):agent.receive(base)
        with self.assertRaises(ProtocolError):agent.start()

    def test_disconnected_and_unsupported_scope_fail(self):
        variables = (Variable('a',('c',)),Variable('b',('c',)))
        with self.assertRaisesRegex(ProtocolError,'disconnected'):
            build_pseudotree(DcopInstance(variables,()))
        with self.assertRaises(ProtocolError):
            build_pseudotree(DcopInstance(variables,(Factor('scalar',(),(),(Cost(0),)),)))

    def test_independent_checker_rejects_corrupted_tree(self):
        instance = to_dcop(grid_map(2,2))
        result = build_pseudotree(instance)
        for corruption in [replace(result.positions[0],children=()),
                           replace(result.positions[0],owned_factors=()),
                           replace(result.positions[0],separator=('ap-01',))]:
            with self.assertRaises(ProtocolError):
                validate_pseudotree(instance,replace(result,positions=(corruption,*result.positions[1:])))
