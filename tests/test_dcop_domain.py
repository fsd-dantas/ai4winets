import json
import unittest
from dataclasses import FrozenInstanceError, replace
from itertools import product

from dcop_channel_assignment.dcop import Assignment, Cost, DcopInstance, Factor, Variable
from dcop_channel_assignment.fixtures import grid_map
from dcop_channel_assignment.translation import to_dcop
from dcop_channel_assignment.wireless import ChannelPlanningScenario, Region


class DcopDomainTests(unittest.TestCase):
    def test_forbidden_is_absorbing_and_greater_than_any_finite_cost(self):
        forbidden, huge = Cost(None), Cost(10**100)
        self.assertEqual(forbidden + huge, forbidden)
        self.assertEqual(huge + forbidden, forbidden)
        self.assertLess(huge, forbidden)
        self.assertEqual(Cost(3) + Cost(5), Cost(8))
        for cost in (forbidden, huge, Cost(0)):
            self.assertEqual(Cost.from_wire(json.loads(json.dumps(cost.to_wire()))), cost)
        for invalid in (-1, True, 0.5, float('inf'), 'infinity', None):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                Cost.from_wire(invalid)

    def test_factor_validates_dimensions_and_scope(self):
        with self.assertRaises(ValueError):
            Factor('f', ('a',), (('c1', 'c2'),), (Cost(0),))
        with self.assertRaises(ValueError):
            Factor('f', ('a', 'a'), (('c1',), ('c1',)), (Cost(0),))
        with self.assertRaises(ValueError):
            DcopInstance((Variable('a', ('c1',)),),
                         (Factor('f', ('b',), (('c1',),), (Cost(0),)),))

    def test_inputs_are_defensively_copied(self):
        domain = ['c1', 'c2']
        variable = Variable('a', domain)
        domain.append('c3')
        self.assertEqual(variable.domain, ('c1', 'c2'))
        with self.assertRaises(FrozenInstanceError):
            variable.id = 'b'

    def test_map_has_only_shared_segment_edges(self):
        scenario = grid_map(2, 2)
        self.assertEqual(set(scenario.edges), {
            ('ap-00', 'ap-01'), ('ap-00', 'ap-02'),
            ('ap-01', 'ap-03'), ('ap-02', 'ap-03')})
        self.assertEqual(len(grid_map().regions), 12)
        self.assertEqual(len(grid_map().edges), 17)

    def test_map_rejects_invalid_geometry_identities_and_scores(self):
        valid = grid_map(1, 2)
        cases = [
            {'regions': (valid.regions[0], valid.regions[0])},
            {'regions': (valid.regions[0], Region('r2', 'ap-00', (1, 0, 2, 1)))},
            {'regions': (valid.regions[0], Region('r2', 'ap-01', (3, 0, 4, 1)))},
            {'regions': (valid.regions[0], Region('r2', 'ap-01', (0, 0, 2, 2)))},
            {'channels': ('c1', 'c1', 'c2', 'c3')},
            {'scores': (('ap-00', (0, 0, 0, 0)),)},
            {'scores': (('ap-00', (0, 0, 0, 0)), ('unknown', (0, 0, 0, 0)))},
            {'scores': (('ap-00', (0, 0, 0, 0)), ('ap-01', (0, -1, 0, 0)))},
            {'scores': (('ap-00', (0, 0, 0, 0)), ('ap-01', (True, 0, 0, 0)))},
        ]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(valid, **changes)

    def test_corner_contact_does_not_connect_regions(self):
        with self.assertRaises(ValueError):
            ChannelPlanningScenario('corners',
                (Region('r1', 'a', (0, 0, 1, 1)), Region('r2', 'b', (1, 1, 2, 2))),
                ('c1', 'c2', 'c3', 'c4'), (('a', (0, 0, 0, 0)), ('b', (0, 0, 0, 0))))

    def test_translation_preserves_objective_for_every_small_assignment(self):
        scenario = grid_map(2, 2, preferences=True)
        instance = to_dcop(scenario)
        self.assertEqual(len(instance.factors), len(scenario.regions) + len(scenario.edges))
        for choices in product(scenario.channels, repeat=4):
            values = dict(zip((v.id for v in instance.variables), choices))
            conflict = any(values[a] == values[b] for a, b in scenario.edges)
            expected = None if conflict else sum(
                dict(scenario.scores)[ap][scenario.channels.index(channel)]
                for ap, channel in values.items())
            self.assertEqual(instance.cost(Assignment(tuple(values.items()))), Cost(expected))

    def test_local_view_excludes_remote_costs_and_variables(self):
        view = to_dcop(grid_map(1, 4)).local_view('ap-00')
        self.assertEqual(tuple(v.id for v in view.neighbors), ('ap-01',))
        self.assertTrue(all('ap-00' in f.scope for f in view.factors))
        self.assertFalse(any('ap-02' in f.scope for f in view.factors))
        self.assertEqual(sum(len(f.scope) == 1 for f in view.factors), 1)

    def test_assignments_must_be_complete_unique_and_in_domain(self):
        instance = to_dcop(grid_map(1, 1))
        for pairs in ((), (('ap-00', 'c5'),), (('unknown', 'c1'),),
                      (('ap-00', 'c1'), ('ap-00', 'c2'))):
            with self.subTest(pairs=pairs), self.assertRaises(ValueError):
                instance.cost(Assignment(pairs))

    def test_reordering_scenario_preserves_translated_instance(self):
        scenario = grid_map()
        reordered = replace(scenario, regions=tuple(reversed(scenario.regions)),
                            scores=tuple(reversed(scenario.scores)))
        self.assertEqual(to_dcop(scenario), to_dcop(reordered))


if __name__ == '__main__':
    unittest.main()
