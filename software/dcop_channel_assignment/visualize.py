"""Generate an offline step-through view of a real DFS/UTIL integration trace."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from shapely.geometry import shape

from .agents import propagate_util
from .geography import from_geojson
from .protocol import Kind
from .translation import to_dcop


def build(source: Path, output: Path):
    raw = source.read_bytes()
    document = json.loads(raw)
    scenario = from_geojson(document,scenario_id=source.stem,preferences=True)
    result = propagate_util(to_dcop(scenario),root='ap-4106902',max_entries=1_000_000)
    shapes = [shape(json.loads(r.geometry_json)) for r in scenario.regions]
    minx = min(g.bounds[0] for g in shapes)
    maxy = max(g.bounds[3] for g in shapes)
    width = max(g.bounds[2] for g in shapes)-minx
    height = maxy-min(g.bounds[1] for g in shapes)
    scale = min(730/(width*.91),650/height)
    def xy(x,y):
        return [round(45+(x-minx)*scale*.91,2),round(35+(maxy-y)*scale,2)]
    regions = []
    for r,g in zip(scenario.regions,shapes):
        polygons = [g] if g.geom_type == 'Polygon' else g.geoms
        paths = []
        for p in polygons:
            for ring in [p.exterior,*p.interiors]:
                paths.append('M'+' L'.join(','.join(map(str,xy(x,y))) for x,y in ring.coords)+' Z')
        point = g.representative_point()
        regions.append({'id':r.ap_id,'name':r.name,'path':' '.join(paths),'point':xy(point.x,point.y)})
    messages = []
    for message in result.messages:
        record = asdict(message)
        if message.kind == Kind.UTIL:
            record['payload']['costs'] = [c.to_wire() for c in message.payload.costs]
        messages.append(record)
    data = {'regions':regions,'messages':messages,'positions':[asdict(p) for p in result.tree.positions],
            'root':result.tree.root,'status':result.status,'cost':result.cost.to_wire() if result.cost else None,
            'source_sha256':hashlib.sha256(raw).hexdigest(),'source_file':source.name,
            'synthetic_channel_costs':[0,10,20,30],'max_table_entries':1_000_000,
            'required_entries':result.required_entries}
    # Escaping '<' prevents a source label from closing the embedded JSON script element.
    embedded = json.dumps(data,ensure_ascii=True).replace('<','\\u003c')
    output.parent.mkdir(parents=True,exist_ok=True)
    template = Path(__file__).with_name('visualization.html').read_text(encoding='utf-8')
    output.write_text(template.replace('__TRACE_DATA__',embedded),encoding='utf-8')
    print(f'{output}: {len(regions)} agents, {len(messages)} messages, status={result.status}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path('data/geography/curitiba-metropolitan/central-core-14.geojson'))
    parser.add_argument('--output',type=Path,default=Path('docs/dcop-channel-assignment/visualization.html'))
    args = parser.parse_args()
    build(args.source,args.output)
