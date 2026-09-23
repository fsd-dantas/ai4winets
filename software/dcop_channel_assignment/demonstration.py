"""Reproduce the deterministic core demonstration; no deferred factorial study."""

import argparse
from dataclasses import replace
from itertools import product
import json
from pathlib import Path
import shutil
import time

from .evaluation import exact_reference
from .execution import load_run,run,save_run
from .fixtures import grid_map
from .geography import from_geojson
from .inputs import border_map,snapshot
from .mobility import MobileCellSequence,mobile_sequence,run_epochs
from .visualize import colored_svg,replay
from .wireless import ChannelPlanningScenario,Region


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=True,sort_keys=True,indent=2)+'\n',encoding='utf-8',newline='\n')


def initialize_inputs(directory):
    directory.mkdir(parents=True,exist_ok=True)
    for name in ('central-core-14','metropolitan-29'):
        shutil.copyfile(Path('data/geography/curitiba-metropolitan')/(name+'.geojson'),directory/(name+'.geojson'))
    names = [f'r{i:02d}' for i in range(10)]
    edges = [[names[i],names[(i+1)%10]] for i in range(10)]
    edges += [[names[0],names[i]] for i in (2,4,6,8)]
    write_json(directory/'hand-map.json',{'id':'hand-map-10','regions':names,'borders':edges})
    write_json(directory/'mobile-epochs.json',{'mobile_id':'mobile','epochs':[
        {'id':e.id,'regions':[{'id':r.id,'ap_id':r.ap_id,'bounds':r.bounds} for r in e.regions],
         'scores':dict(e.scores),'channels':e.channels} for e in mobile_sequence().epochs]})
    write_json(directory/'protocol.json',{'table_budget':1_000_000,'modes':['zero','shared'],
                                        'shared_scores':[0,10,20,30],
                                        'roots':'lowest plus highest for synthetic; lowest plus Curitiba for geography',
                                        'stability':'0 versus 101 times epoch region count; fixed APs only'})


def trace_map():
    regions = tuple(Region(n,n,b) for n,b in [('a',(0,0,1,1)),('b',(1,0,2,1)),
                                             ('c',(0,1,1,2)),('d',(1,1,2,2)),('e',(2,0,3,1))])
    return ChannelPlanningScenario('trace-five',regions,('c1','c2','c3','c4'),tuple((r.ap_id,(0,0,0,0)) for r in regions))


def trace_explanation(record,path):
    lines = ['# Five-region hand-checkable trace','',
             'Map: a-b-d-c-a is the single cycle, and e is attached to b. All unary costs are zero.',
             'Root a explores b, then d, then c; b subsequently explores e. The non-tree edge is a-c.',
             '', 'Let I(x,y) be forbidden if x=y, otherwise zero. The local derivations are:', '',
             '- U_c(a,d) = min_c [I(c,a) + I(c,d)] = 0 for every context: at most two of four colors are excluded.',
             '- U_d(a,b) = min_d [I(d,b) + U_c(a,d)] = 0 for every context.',
             '- U_e(b) = min_e I(e,b) = 0 for every context.',
             '- U_b(a) = min_b [I(b,a) + U_d(a,b) + U_e(b)] = 0 for every context.',
             '- U_a() = min_a U_b(a) = 0. Ties choose the lowest available color.',
             '', 'VALUE chooses a=c1, b=c2, d=c1, c=c2, e=c1. Every border has different endpoints.',
             'The following complete transcript is generated from the saved run. It can be checked against those derivations.', '']
    for i,m in enumerate(record['messages'],1):
        lines += [f'## {i}: {m["kind"]} {m["sender"]} -> {m["recipient"]}','']
        if m['kind']=='util':
            p=m['payload']; lines += [f'Scope: {p["scope"]}', '', '| Context | Minimum cost |','| --- | --- |']
            for values,cost in zip(product(*p['domains']),p['costs']):lines.append(f'| {values} | {cost} |')
        else:lines += ['```json',json.dumps(m['payload'],sort_keys=True),'```']
        lines += ['']
    lines += ['## Independent verdict','',json.dumps(record['evaluation'],sort_keys=True),'']
    path.write_text('\n'.join(lines),encoding='utf-8',newline='\n')


def render_records(directory):
    for path in sorted((directory/'runs').glob('*.json.gz')):
        record=load_run(path);slug=path.name.removesuffix('.json.gz')
        if record['assignment'] is not None:
            for dark in (False,True):
                colored_svg(record,directory/'figures'/f'{slug}-{"dark" if dark else "light"}.svg',dark=dark)
        if slug in ('core14-shared-curitiba','trace-five'):
            replay(record,directory/f'{slug}-replay.html')
        if slug=='trace-five':trace_explanation(record,directory/'trace-five.md')
    rows=['<!doctype html><html lang="en"><meta charset="utf-8"><title>Mobile-cell epochs</title>',
          '<style>body{font:16px system-ui;margin:30px;background:#f1f5f9;color:#172033}section{display:grid;grid-template-columns:1fr 1fr;gap:20px}img{width:100%}article{background:white;padding:15px;border-radius:12px}button{padding:12px}h2{font-size:18px}</style>',
          '<h1>Mobile-cell snapshots</h1><p>Same baseline. Left: free reoptimization. Right: stability penalty for surviving fixed APs. Each image comes from an independently checked run.</p>',
          '<p>Move between epochs with the buttons. The mobile cell replaces a strip of its host region; it never overlaps the fixed partition.</p><nav>']
    epochs=('baseline','arrival','move','departure')
    for epoch in epochs:rows.append(f'<button onclick="show(\'{epoch}\')">{epoch}</button>')
    rows += ['</nav><section>']
    for arm in ('free','stable'):
        rows.append(f'<article><h2>{arm}</h2><picture><source id="{arm}-dark" media="(prefers-color-scheme:dark)"><img id="{arm}" alt="{arm} assignment by epoch"></picture></article>')
    rows += ['</section><p>Channel labels accompany every color. No radio throughput or delay is measured.</p>',
             '<script>function show(e){for(const arm of ["free","stable"]){document.getElementById(arm).src="figures/mobile-"+arm+"-"+e+"-light.svg";document.getElementById(arm+"-dark").srcset="figures/mobile-"+arm+"-"+e+"-dark.svg";}}show("baseline");</script></html>']
    (directory/'mobile-epochs.html').write_text('\n'.join(rows),encoding='utf-8',newline='\n')


def execute(inputs, output):
    protocol=json.loads((inputs/'protocol.json').read_text());budget=protocol['table_budget']
    summary=[]
    scenarios=[('grid12',grid_map()),('hand10',border_map(json.loads((inputs/'hand-map.json').read_text())))]
    for slug,name in [('core14','central-core-14'),('metro29','metropolitan-29')]:
        scenarios.append((slug,from_geojson(json.loads((inputs/(name+'.geojson')).read_text()),scenario_id=name)))
    timings=[]
    for slug,scenario in scenarios:
        ids=sorted(r.ap_id for r in scenario.regions)
        roots=[('lowest',ids[0]),('curitiba','ap-4106902')] if slug in ('core14','metro29') else [('lowest',ids[0]),('highest',ids[-1])]
        for mode in protocol['modes']:
            cs=(0,0,0,0) if mode=='zero' else tuple(protocol['shared_scores'])
            s=replace(scenario,scores=tuple((n,cs) for n,_ in scenario.scores))
            for root_label,root in roots:
                label=f'{slug}-{mode}-{root_label}'
                start=time.perf_counter();record=run(s,root=root,max_entries=budget)
                timings.append({'run':label,'host_elapsed_seconds':round(time.perf_counter()-start,3)})
                save_run(record,output/'runs'/(label+'.json.gz'))
                summary.append({'run':label,'run_id':record['run_id'],'status':record['status'],
                                'cost':record['cost'],'conflicts':record['evaluation']['conflict_count'] if record['assignment'] else None,
                                'baseline_conflicts':record['baseline']['evaluation']['conflict_count'],
                                **record['metrics'],'required_entries':record['required_entries']})
    record=run(trace_map(),max_entries=budget)
    if exact_reference(snapshot(trace_map()))['cost']!=record['cost']:
        raise ValueError('Trace run disagrees with the exact reference')
    save_run(record,output/'runs'/'trace-five.json.gz')
    data=json.loads((inputs/'mobile-epochs.json').read_text())
    sequence=MobileCellSequence(tuple(ChannelPlanningScenario(e['id'],tuple(Region(**r) for r in e['regions']),
                                  tuple(e['channels']),tuple((n,tuple(c)) for n,c in e['scores'].items())) for e in data['epochs']),data['mobile_id'])
    mobility={}
    for stable in (False,True):
        mode='stable' if stable else 'free'
        records,rows=run_epochs(sequence,stable=stable,max_entries=budget)
        for record in records:save_run(record,output/'runs'/f'mobile-{mode}-{record["problem"]["id"]}.json.gz')
        mobility[mode]=rows
    write_json(output/'summary.json',summary);write_json(output/'mobility.json',mobility)
    write_json(output/'host-timings.json',timings)
    render_records(output)
    lines=['# Core demonstration results','',
           'Deterministic software evidence on declared maps. Synthetic scores; no radio-performance claim.',
           'All successful assignments are independently evaluated. Budget stops have no assignment or reported conflict rate.', '',
           '| Run | Outcome | Cost | Conflicts | Baseline conflicts | Separator | Max joined entries | UTIL entries transmitted | DFS / UTIL / VALUE |',
           '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in summary:
        m=r['messages'];dfs=sum(v for k,v in m.items() if k.startswith('dfs_'))
        lines.append(f'| {r["run"]} | {r["status"]} | {r["cost"]} | {r["conflicts"]} | {r["baseline_conflicts"]} | {r["max_separator"]} | {r["max_join_entries"]} | {r["transmitted_entries"]} | {dfs} / {m.get("util",0)} / {m.get("value",0)} |')
    lines += ['', '## Mobile-cell snapshots','','Both arms start from the same baseline plan. Penalties apply to surviving fixed APs only.',
              'The mobile region is excluded even when it persists across epochs. No movement occurs during a solve.', '',
              '| Arm | Epoch | Fixed reassignments | Base cost | Penalized objective | Conflicts |','| --- | --- | --- | --- | --- | --- |']
    for mode,rows in mobility.items():
        for r in rows:lines.append(f'| {mode} | {r["epoch"]} | {r["reassignments"]} | {r.get("base_cost")} | {r.get("objective")} | {r.get("conflicts")} |')
    free=sum(r['reassignments'] or 0 for r in mobility['free']);stable=sum(r['reassignments'] or 0 for r in mobility['stable'])
    lines += ['',f'Total fixed-AP reassignments: free={free}, stability-penalized={stable}. This comparison is specific to this sequence.',
              'A dominant penalty minimizes changes relative to each arm\'s own previous valid plan; it does not guarantee fewer cumulative changes for every possible sequence.',
              '', '## Claim assessment','',
              '- C1: supported for completed demonstration solves; entry-budget stops are explicitly excluded from completeness.',
              '- C2: exact optimality is tested on bounded small instances; enumeration is not used to solve the larger maps.',
              '- C3: independent cheapest-channel choices conflict on these inputs; their local score is not a feasible objective.',
              '- C4: counts and table sizes describe this implementation, including its materialized joins, under the declared roots.',
              '- C5: the table above reports the observed stability effect without assuming strict improvement.',
              '', '## Limits','',
              'The 29-region map exceeds the tested 1,000,000-entry budget. This does not prove that no root, representation or larger budget can solve it.',
              'There is no timing-performance claim. host-timings.json supplies one-host demonstration estimates only.',
              'No throughput, latency, SINR, loss, security, or fault-tolerance conclusions follow. The 960-run comparative study is deferred.', '']
    (output/'report.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
    print(json.dumps({'demonstration_runs':len(summary),'mobile_epochs':sum(len(v) for v in mobility.values()),
                      'trace_runs':1,'reassignments':{'free':free,'stable':stable}}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',type=Path,default=Path('experiments/001-dcop-channel-assignment/configuration'))
    parser.add_argument('--output',type=Path,default=Path('experiments/001-dcop-channel-assignment/results'))
    parser.add_argument('--initialize',action='store_true')
    parser.add_argument('--render-only',action='store_true')
    args=parser.parse_args()
    if args.initialize:initialize_inputs(args.inputs)
    if args.render_only:render_records(args.output)
    else:execute(args.inputs,args.output)
