"""GeoJSON adapter. Geometry and graph libraries never make allocation decisions."""

from dataclasses import dataclass, field
from itertools import combinations
import json

import networkx as nx
from shapely.geometry import shape

from .dcop import identifier


@dataclass(frozen=True)
class GeographicRegion:
    id: str
    name: str
    ap_id: str
    geometry_json: str


@dataclass(frozen=True)
class GeographicScenario:
    id: str
    regions: tuple[GeographicRegion, ...]
    channels: tuple[str, ...]
    scores: tuple[tuple[str, tuple[int, ...]], ...]
    edges: tuple[tuple[str, str], ...] = field(init=False)

    def __post_init__(self):
        identifier(self.id)
        object.__setattr__(self, 'regions', tuple(self.regions))
        object.__setattr__(self, 'channels', tuple(self.channels))
        object.__setattr__(self, 'scores', tuple((a, tuple(c)) for a, c in self.scores))
        if not self.regions or len({r.id for r in self.regions}) != len(self.regions):
            raise ValueError('Regions must have unique IDs and be nonempty')
        aps = {r.ap_id for r in self.regions}
        if len(aps) != len(self.regions):
            raise ValueError('AP identities must be unique')
        for r in self.regions:
            identifier(r.id)
            identifier(r.name)
            identifier(r.ap_id)
        if len(self.channels) != 4 or len(set(self.channels)) != 4:
            raise ValueError('Four unique channels required')
        for c in self.channels:
            identifier(c)
        if len(self.scores) != len(aps) or {a for a, _ in self.scores} != aps:
            raise ValueError('Scores must cover every AP exactly once')
        for _, costs in self.scores:
            if len(costs) != 4 or any(type(c) is not int or c < 0 for c in costs):
                raise ValueError('Four nonnegative integer channel costs required')
        geometries = [shape(json.loads(r.geometry_json)) for r in self.regions]
        for g in geometries:
            if g.geom_type not in ('Polygon', 'MultiPolygon') or g.is_empty or not g.is_valid:
                raise ValueError('Valid nonempty Polygon/MultiPolygon required')
        edges = []
        for i, j in combinations(range(len(geometries)), 2):
            a, b = geometries[i], geometries[j]
            if a.intersection(b).area > 0:
                raise ValueError('Municipal interiors overlap; no automatic geometry repair')
            if a.boundary.intersection(b.boundary).length > 0:
                edges.append(tuple(sorted((self.regions[i].ap_id, self.regions[j].ap_id))))
        graph = nx.Graph()
        graph.add_nodes_from(aps)
        graph.add_edges_from(edges)
        if not nx.is_connected(graph):
            raise ValueError('Boundary-adjacency graph is disconnected')
        if not nx.check_planarity(graph)[0]:
            raise ValueError('Boundary-adjacency graph is nonplanar')
        object.__setattr__(self, 'edges', tuple(sorted(edges)))


def from_geojson(document: dict, *, scenario_id: str, preferences: bool = False):
    if document.get('type') != 'FeatureCollection' or not document.get('features'):
        raise ValueError('Nonempty GeoJSON FeatureCollection required')
    regions = []
    for feature in document['features']:
        if feature.get('type') != 'Feature':
            raise ValueError('Expected GeoJSON Feature')
        properties = feature['properties']
        code = str(properties['codarea'])
        regions.append(GeographicRegion(code, properties['name'], f'ap-{code}',
                                       json.dumps(feature['geometry'], sort_keys=True)))
    regions.sort(key=lambda r: r.id)
    costs = (0, 10, 20, 30) if preferences else (0, 0, 0, 0)
    return GeographicScenario(scenario_id, tuple(regions), ('c1', 'c2', 'c3', 'c4'),
                              tuple((r.ap_id, costs) for r in regions))
