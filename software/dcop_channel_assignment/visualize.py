"""Render channel assignments and protocol replay from checked run records."""

import argparse
import html
import json
from pathlib import Path
from shapely.geometry import shape
from .execution import load_run,run,save_run
from .geography import from_geojson

PALETTE = {'c1':'#38bdf8','c2':'#fb923c','c3':'#a78bfa','c4':'#4ade80'}


def display_regions(problem):
    features = problem['regions']
    if problem['geometry_kind']=='border_graph':
        xs = [r['point'][0] for r in features]; ys = [r['point'][1] for r in features]
        out = []
        for r in features:
            x = 60+(r['point'][0]-min(xs))*680/max(max(xs)-min(xs),1)
            y = 60+(max(ys)-r['point'][1])*570/max(max(ys)-min(ys),1)
            out.append({'id':r['ap_id'],'name':r['name'],'point':[x,y],
                        'path':f'M{x-10},{y-10} h20 v20 h-20 Z'})
        return out
    geometries = [shape(r['geometry']) for r in features]
    minx = min(g.bounds[0] for g in geometries); maxy = max(g.bounds[3] for g in geometries)
    width = max(g.bounds[2] for g in geometries)-minx
    height = maxy-min(g.bounds[1] for g in geometries)
    aspect = .91 if '4106902' in {r['id'] for r in features} else 1
    scale = min(730/(width*aspect),620/height)
    def xy(x,y):return [round(40+(x-minx)*scale*aspect,2),round(40+(maxy-y)*scale,2)]
    regions = []
    for r,g in zip(features,geometries):
        polygons = [g] if g.geom_type=='Polygon' else g.geoms
        paths = []
        for polygon in polygons:
            for ring in [polygon.exterior,*polygon.interiors]:
                paths.append('M'+' L'.join(','.join(map(str,xy(x,y))) for x,y in ring.coords)+' Z')
        p = g.representative_point()
        regions.append({'id':r['ap_id'],'name':r['name'],'path':' '.join(paths),'point':xy(p.x,p.y)})
    return regions


def replay(record, output):
    data = {'regions':display_regions(record['problem']),'messages':record['messages'],
            'positions':record['positions'],'root':record['root'],'status':record['status'],'cost':record['cost'],
            'source_sha256':record['problem_hash'],'source_file':record['problem']['id'],
            'assignment':dict(record['assignment'] or []),'evaluation':record['evaluation'],
            'edges':record['problem']['edges'],'palette':PALETTE,'max_table_entries':record['max_entries'],
            'required_entries':record['required_entries'],'run_id':record['run_id']}
    template = Path(__file__).with_name('visualization.html').read_text(encoding='utf-8')
    output = Path(output); output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(template.replace('__TRACE_DATA__',json.dumps(data,ensure_ascii=True).replace('<','\\u003c')),
                      encoding='utf-8',newline='\n')


def colored_svg(record, output, *, dark=False):
    regions = display_regions(record['problem']); by_id = {r['id']:r for r in regions}
    channels = dict(record['assignment'] or [])
    ink,bg = ('#e2e8f0','#101827') if dark else ('#172033','#ffffff')
    elements = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 820 780"><rect width="820" height="780" fill="{bg}"/>',
                f'<text x="25" y="23" fill="{ink}" font-size="17" font-family="sans-serif">{html.escape(record["problem"]["id"])}: {record["status"]}</text>']
    for r in regions:
        elements.append(f'<path d="{r["path"]}" fill="{PALETTE.get(channels.get(r["id"]),"#64748b")}" stroke="{ink}" stroke-width=".7" fill-rule="evenodd"/>')
    if record['problem']['geometry_kind']=='border_graph':
        for a,b in record['problem']['edges']:
            p,q = by_id[a]['point'],by_id[b]['point']
            elements.append(f'<line x1="{p[0]}" y1="{p[1]}" x2="{q[0]}" y2="{q[1]}" stroke="{ink}"/>')
    for a,b in record['evaluation']['conflicts']:
        p,q=by_id[a]['point'],by_id[b]['point']
        elements.append(f'<line x1="{p[0]}" y1="{p[1]}" x2="{q[0]}" y2="{q[1]}" stroke="red" stroke-width="4"/>')
    for r in regions:
        x,y=r['point']; label=html.escape(r['name']+' / '+channels.get(r['id'],'unassigned'))
        elements.append(f'<text x="{x}" y="{y}" text-anchor="middle" font-family="sans-serif" font-size="8" fill="#111827" stroke="#ffffff" stroke-width="2" paint-order="stroke">{label}</text>')
    for i,(c,color) in enumerate(PALETTE.items()):
        elements.append(f'<rect x="{30+i*110}" y="704" width="16" height="16" fill="{color}"/><text x="{52+i*110}" y="717" fill="{ink}" font-family="sans-serif">{c}</text>')
    elements.append(f'<text x="25" y="748" fill="{ink}" font-size="12" font-family="sans-serif">Feasible: {record["evaluation"]["feasible"]}; conflicts: {record["evaluation"]["conflict_count"]}; cost: {record["cost"]}</text>')
    elements.append(f'<text x="25" y="769" fill="{ink}" font-size="9" font-family="sans-serif">Recorded run {record["run_id"][:16]}; synthetic channels. Geographic sources: IBGE 2022 / AMEP where applicable.</text></svg>')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text('\n'.join(elements),encoding='utf-8',newline='\n')


def build(source,output):
    scenario = from_geojson(json.loads(Path(source).read_text(encoding='utf-8')),scenario_id=Path(source).stem,preferences=True)
    record = run(scenario,root='ap-4106902')
    path = Path(output).with_suffix('.run.json.gz')
    save_run(record,path)
    replay(load_run(path),output)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path('data/geography/curitiba-metropolitan/central-core-14.geojson'))
    parser.add_argument('--record',type=Path,help='Render a checksummed run without executing the solver')
    parser.add_argument('--output',type=Path,default=Path('docs/dcop-channel-assignment/visualization.html'))
    args=parser.parse_args()
    if args.record:replay(load_run(args.record),args.output)
    else:build(args.source,args.output)
