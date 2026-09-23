"""Recorded application runs; solver, evaluator and reference remain separate."""

from collections import Counter
from dataclasses import asdict
import hashlib
import json
import gzip
from pathlib import Path

from .agents import solve
from .evaluation import evaluate, independent_choice
from .inputs import snapshot
from .protocol import Kind
from .translation import to_dcop


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()


def source_hashes(directory=None):
    # Line endings are normalized so a Windows and a Linux checkout of the same commit agree.
    directory = Path(directory or Path(__file__).parent)
    return {p.name:hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for p in sorted(directory.iterdir()) if p.suffix in ('.py','.html')}


def run(scenario, *, root=None, max_entries=1_000_000):
    problem = snapshot(scenario)
    config = {'problem':problem,'root':root or min(problem['domains']),'max_entries':max_entries}
    run_id = digest(config)
    result = solve(to_dcop(scenario),root=root,max_entries=max_entries,run_id=run_id)
    assignment = list(result.assignment.values) if result.assignment is not None else None
    verdict = evaluate(problem,assignment)
    if assignment is not None and (not verdict['feasible'] or verdict['objective'] != result.cost.value):
        raise ValueError('Independent evaluator rejected solver assignment or cost')
    messages = []
    for m in result.messages:
        record = asdict(m)
        if m.kind == Kind.UTIL:
            record['payload']['costs'] = [c.to_wire() for c in m.payload.costs]
        messages.append(record)
    counts = Counter(m['kind'] for m in messages)
    tables = [m['payload'] for m in messages if m['kind']=='util']
    baseline = independent_choice(problem)
    return {'format':'dcop-run-v1','run_id':run_id,'problem_hash':digest(problem),'problem':problem,
            'root':result.tree.root,'max_entries':max_entries,'status':result.status,
            'cost':None if result.cost is None else result.cost.to_wire(),'assignment':assignment,
            'evaluation':verdict,'baseline':{'assignment':baseline,'evaluation':evaluate(problem,baseline)},
            'positions':[asdict(p) for p in result.tree.positions],'messages':messages,
            'required_entries':result.required_entries,
            'metrics':{'messages':dict(sorted(counts.items())),
                       'max_separator':max(len(p.separator) for p in result.tree.positions),
                       'max_join_entries':result.max_join_entries,
                       'max_outgoing_entries':max((len(t['costs']) for t in tables),default=0),
                       'transmitted_entries':sum(len(t['costs']) for t in tables)},
            'source_hashes':source_hashes()}


def save_run(record, path):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    raw = (json.dumps(record,ensure_ascii=True,sort_keys=True,indent=2)+'\n').encode()
    path.write_bytes(gzip.compress(raw,mtime=0) if path.suffix=='.gz' else raw)
    path.with_suffix(path.suffix+'.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest()+'\n',
                                                        encoding='ascii',newline='\n')


def load_run(path):
    path = Path(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != path.with_suffix(path.suffix+'.sha256').read_text().strip():
        raise ValueError('Run checksum mismatch')
    raw = path.read_bytes()
    record = json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)
    problem = record['problem']
    if digest(problem) != record['problem_hash']:
        raise ValueError('Problem hash mismatch')
    config = {'problem':problem,'root':record['root'],'max_entries':record['max_entries']}
    if digest(config) != record['run_id'] or evaluate(problem,record['assignment']) != record['evaluation']:
        raise ValueError('Run identity or evaluation mismatch')
    if record['status']=='optimal_cost':
        if not record['evaluation']['feasible'] or record['evaluation']['objective'] != record['cost']:
            raise ValueError('Invalid completed run')
    elif record['assignment'] is not None:
        raise ValueError('Non-optimal run must not carry an assignment')
    return record
