"""Declared topological maps and portable snapshots at the application boundary."""

from dataclasses import dataclass
import json

from .dcop import identifier


@dataclass(frozen=True)
class MapRegion:
    id: str
    ap_id: str
    name: str


@dataclass(frozen=True)
class BorderMap:
    id: str
    regions: tuple
    channels: tuple
    scores: tuple
    edges: tuple
    positions: tuple


def border_map(data):
    """An explicit shared-border declaration, not a radio or polygon reconstruction."""
    import networkx as nx
    identifier(data['id'])
    names = data['regions']
    if not names or len(set(names)) != len(names):
        raise ValueError('Unique nonempty region IDs required')
    for n in names:
        identifier(n)
    edges = []
    for edge in data['borders']:
        if len(edge) != 2 or edge[0] == edge[1] or not set(edge) <= set(names):
            raise ValueError('Invalid shared border')
        pair = tuple(sorted(edge))
        if pair in edges:
            raise ValueError('Duplicate shared border')
        edges.append(pair)
    graph = nx.Graph()
    graph.add_nodes_from(sorted(names)); graph.add_edges_from(sorted(edges))
    if not nx.is_connected(graph) or not nx.check_planarity(graph)[0]:
        raise ValueError('Map must be connected and planar')
    channels = ('c1','c2','c3','c4')
    scores = data.get('scores',{n:[0]*4 for n in names})
    if set(scores) != set(names) or any(len(v)!=4 or any(type(c) is not int or c<0 for c in v) for v in scores.values()):
        raise ValueError('Four nonnegative integer scores per region required')
    layout = nx.planar_layout(graph)
    return BorderMap(data['id'],tuple(MapRegion(n,n,n) for n in sorted(names)),channels,
                     tuple((n,tuple(scores[n])) for n in sorted(names)),tuple(sorted(edges)),
                     tuple((n,tuple(float(x) for x in layout[n])) for n in sorted(names)))


def snapshot(scenario):
    regions = []
    positions = dict(getattr(scenario,'positions',()))
    for r in scenario.regions:
        item = {'id':r.id,'ap_id':r.ap_id,'name':getattr(r,'name',r.id)}
        if hasattr(r,'geometry_json'):
            item['geometry'] = json.loads(r.geometry_json)
        elif hasattr(r,'bounds'):
            x,y,X,Y = r.bounds
            item['geometry'] = {'type':'Polygon','coordinates':[[[x,y],[X,y],[X,Y],[x,Y],[x,y]]]}
        else:
            item['point'] = list(positions[r.ap_id])
        regions.append(item)
    return {'id':scenario.id,'regions':regions,'domains':{r.ap_id:list(scenario.channels) for r in scenario.regions},
            'scores':{n:list(c) for n,c in scenario.scores},'edges':[list(e) for e in scenario.edges],
            'geometry_kind':'border_graph' if positions else 'polygon_map'}
