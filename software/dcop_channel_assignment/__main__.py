"""Inspect distributed DFS and UTIL costs. agents.solve reconstructs channels; this CLI
prints them once the independent evaluator exists (CA-11, CA-12)."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .agents import build_pseudotree, propagate_util
from .protocol import Kind
from .fixtures import grid_map
from .translation import to_dcop


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geojson',type=Path,help='Use a validated polygon map instead of the synthetic grid')
    parser.add_argument('--root',help='Root agent ID; defaults to lowest ID')
    parser.add_argument('--trace',action='store_true',help='Include every delivered protocol message')
    parser.add_argument('--util',action='store_true',help='Compute the optimal cost by upward UTIL propagation')
    parser.add_argument('--max-table-entries',type=int,default=1_000_000,help='Per-table entry limit for UTIL')
    parser.add_argument('--preferences',action='store_true',help='Use synthetic shared channel preferences')
    parser.add_argument('--solve',action='store_true',help='Solve and independently evaluate a complete assignment')
    parser.add_argument('--map',type=Path,help='Hand-authored JSON region/shared-border map')
    parser.add_argument('--output',type=Path,help='Save a complete checked run with checksum (requires --solve)')
    args = parser.parse_args()
    if args.geojson and args.map:
        parser.error('Choose either --geojson or --map')
    if args.solve and args.util:
        parser.error('Choose either --solve or --util')
    if args.output and not args.solve:
        parser.error('--output requires --solve')
    if args.geojson:
        from .geography import from_geojson
        scenario = from_geojson(json.loads(args.geojson.read_text(encoding='utf-8')),
                                scenario_id=args.geojson.stem,preferences=args.preferences)
    elif args.map:
        from .inputs import border_map
        data = json.loads(args.map.read_text(encoding='utf-8'))
        if args.preferences:
            data['scores'] = {n:[0,10,20,30] for n in data['regions']}
        scenario = border_map(data)
    else:
        scenario = grid_map(preferences=args.preferences)
    if args.solve:
        from .execution import run, save_run
        record = run(scenario,root=args.root,max_entries=args.max_table_entries)
        if args.output:
            save_run(record,args.output)
        report = {k:v for k,v in record.items() if k not in ('messages','source_hashes','problem')}
        if args.trace:
            report['messages'] = record['messages']
        print(json.dumps(report,indent=2))
        return
    util = propagate_util(to_dcop(scenario),root=args.root,max_entries=args.max_table_entries) if args.util else None
    result = util.tree if util else build_pseudotree(to_dcop(scenario),root=args.root)
    report = {'status':'pseudo_tree_validated_not_channel_assignment','scenario':scenario.id,
              'root':result.root,'agents':len(result.positions),'dfs_messages':len(result.messages),
              'max_separator_size':max(len(p.separator) for p in result.positions),
              'positions':[asdict(p) for p in result.positions]}
    if util:
        report.update(status=util.status,channel_assignment_available=False,
                      optimal_cost=util.cost.to_wire() if util.cost is not None else None,
                      util_messages=sum(m.kind == Kind.UTIL for m in util.messages),
                      max_join_entries=util.max_join_entries,
                      table_entry_limit=args.max_table_entries,
                      required_entries=util.required_entries)
    if args.trace:
        report['messages'] = []
        for message in (util.messages if util else result.messages):
            record = asdict(message)
            if message.kind == Kind.UTIL:
                record['payload']['costs'] = [cost.to_wire() for cost in message.payload.costs]
            report['messages'].append(record)
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
