"""Inspect distributed DFS and UTIL costs; final channel reconstruction is not yet implemented."""

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
    args = parser.parse_args()
    if args.geojson:
        from .geography import from_geojson
        scenario = from_geojson(json.loads(args.geojson.read_text(encoding='utf-8')),
                                scenario_id=args.geojson.stem,preferences=args.preferences)
    else:
        scenario = grid_map(preferences=args.preferences)
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
