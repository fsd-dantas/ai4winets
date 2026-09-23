import json
from pathlib import Path
import unittest

try:
    from dcop_channel_assignment.geography import from_geojson
except ModuleNotFoundError as exc:
    if exc.name not in ('shapely', 'networkx'):
        raise
    from_geojson = None

from dcop_channel_assignment.translation import to_dcop
from dcop_channel_assignment.agents import build_pseudotree


def feature(code, polygons):
    return {'type':'Feature','properties':{'codarea':str(code),'name':f'Region {code}'},
            'geometry':{'type':'MultiPolygon','coordinates':polygons}}


def rectangle(x,y,width=1):
    return [[[x,y],[x+width,y],[x+width,y+1],[x,y+1],[x,y]]]


@unittest.skipIf(from_geojson is None, 'Install the maps extra to validate geographic inputs')
class GeographicTests(unittest.TestCase):
    def scenario(self, features):
        return from_geojson({'type':'FeatureCollection','features':features},scenario_id='test')

    def test_shared_segment_not_corner_contact(self):
        scenario = self.scenario([feature(1,[rectangle(0,0)]),feature(2,[rectangle(1,0)]),
                                  feature(3,[rectangle(1,1)])])
        self.assertEqual(scenario.edges,(('ap-1','ap-2'),('ap-2','ap-3')))

    def test_overlap_disconnection_duplicate_and_invalid_geometry_rejected(self):
        cases = [
            [feature(1,[rectangle(0,0,2)]),feature(2,[rectangle(1,0)])],
            [feature(1,[rectangle(0,0)]),feature(2,[rectangle(1,1)])],
            [feature(1,[rectangle(0,0)]),feature(1,[rectangle(1,0)])],
            [feature(1,[[[[0,0],[1,1],[1,0],[0,1],[0,0]]]])],
        ]
        for features in cases:
            with self.subTest(features=features), self.assertRaises(ValueError):
                self.scenario(features)

    def test_disconnected_municipal_pieces_can_form_nonplanar_graph(self):
        # Five multipolygons; dedicate a disjoint touching pair of squares to each edge.
        # This realizes K5 without interior overlap and must fail the planarity check.
        parts = {i:[] for i in range(5)}
        slot = 0
        for i in range(5):
            for j in range(i+1,5):
                parts[i].append(rectangle(slot*4,0))
                parts[j].append(rectangle(slot*4+1,0))
                slot += 1
        with self.assertRaisesRegex(ValueError,'nonplanar'):
            self.scenario([feature(i,p) for i,p in parts.items()])

    def test_real_snapshots_are_connected_planar_and_translatable(self):
        root = Path(__file__).resolve().parents[1]/'data/geography/curitiba-metropolitan'
        for slug,n,m in [('metropolitan-29',29,66),('central-core-14',14,29)]:
            with self.subTest(slug=slug):
                document = json.loads((root/f'{slug}.geojson').read_text(encoding='utf-8'))
                scenario = from_geojson(document,scenario_id=slug)
                self.assertEqual(len(scenario.regions),n)
                self.assertEqual(len(scenario.edges),m)
                self.assertIn('4106902',{r.id for r in scenario.regions})
                instance = to_dcop(scenario)
                self.assertEqual(len(instance.factors),n+m)
                self.assertTrue(all(len(f.scope)==1 or f.at(('c1','c1')).value is None
                                    for f in instance.factors))
                result = build_pseudotree(instance,root='ap-4106902')
                self.assertEqual(len(result.positions),n)
                self.assertEqual(len(result.messages),2*m)
                self.assertEqual(sum(len(p.owned_factors) for p in result.positions),n+m)

    def test_order_independence(self):
        features = [feature(1,[rectangle(0,0)]),feature(2,[rectangle(1,0)])]
        self.assertEqual(self.scenario(features),self.scenario(list(reversed(features))))
