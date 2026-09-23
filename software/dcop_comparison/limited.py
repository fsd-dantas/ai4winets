"""One arm on one map under wall-time, process-memory and table-entry limits.

The ledger entry is terminal whatever happens. Only a verified completed record carries an
assignment or a feasibility verdict; a time, memory, table-budget or execution stop never
does, so it can be scored neither as feasible nor as infeasible.
"""

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys

from .resources import Limits, supervise

ARMS = ('dpop', 'independent')
# Exit codes the worker reserves; any other failure is an execution error.
MEMORY_EXIT = 73
# Native allocators (numpy's OpenBLAS among them) exit on their own when refused memory, so a
# nonzero exit whose peak commit reached this share of the limit is also a memory stop.
MEMORY_CEILING = 0.95
# One BLAS thread: per-thread buffers otherwise dominate the measured commit of a small run.
WORKER_ENV = {'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1'}
INTERRUPTED = ('time_exceeded', 'memory_exceeded', 'budget_exceeded', 'execution_error')


def _verified(arm, path):
    """Reload the worker's output and re-check it; None when it cannot be trusted."""
    from dcop_channel_assignment.evaluation import evaluate
    from dcop_channel_assignment.execution import load_run
    try:
        if arm == 'dpop':
            return load_run(path)
        path = Path(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != path.with_suffix(path.suffix + '.sha256').read_text().strip():
            return None
        record = json.loads(path.read_bytes())
        if record.get('status') != 'completed' or evaluate(record['problem'], record['assignment']) != record['evaluation']:
            return None
        return record
    except (OSError, ValueError, KeyError, TypeError):
        return None


def classify(arm, supervision, output, limits):
    """Map a supervised exit and the worker's output to exactly one terminal outcome."""
    if supervision['status'] == 'time_exceeded':
        return 'time_exceeded', None
    if supervision['status'] != 'exited':
        return 'execution_error', None
    peak = supervision['peak_process_commit_bytes'] or 0
    if supervision['returncode'] == MEMORY_EXIT or (
            supervision['returncode'] != 0 and peak >= MEMORY_CEILING * limits.memory_bytes):
        return 'memory_exceeded', None
    if supervision['returncode'] != 0:
        return 'execution_error', None
    record = _verified(arm, output)
    if record is None:
        return 'execution_error', None
    return record['status'], record


def ledger_entry(arm, outcome, record, supervision, limits):
    scored = record is not None and outcome not in INTERRUPTED
    verdict = record['evaluation'] if scored else None
    return {'arm': arm, 'outcome': outcome, 'interrupted': outcome in INTERRUPTED,
            'assignment': record['assignment'] if scored else None,
            'feasible': verdict['feasible'] if scored else None,
            'objective': verdict['objective'] if scored else None,
            'conflict_count': verdict['conflict_count'] if scored else None,
            'metrics': record['metrics'] if record is not None else None,
            'limits': asdict(limits),
            'supervision': {k: supervision[k] for k in ('status', 'returncode', 'wall_seconds',
                                                        'peak_process_commit_bytes', 'memory_backend')}}


def limited_run(arm, border_map, directory, *, limits=Limits(), root=None):
    """Run one arm in a gated worker and return its terminal ledger entry."""
    if arm not in ARMS:
        raise ValueError('Unknown arm')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    request, output = directory / 'request.json', directory / 'record.json'
    request.write_text(json.dumps({'arm': arm, 'map': border_map, 'root': root,
                                   'table_entries': limits.table_entries}, sort_keys=True) + '\n',
                       encoding='utf-8', newline='\n')
    env = {**os.environ, **WORKER_ENV}
    software = str(Path(__file__).resolve().parents[1])
    env['PYTHONPATH'] = os.pathsep.join(p for p in (software, env.get('PYTHONPATH')) if p)
    supervision = supervise([sys.executable, '-m', 'dcop_comparison.worker', str(request), str(output)],
                            limits, log_path=directory / 'worker.log', env=env)
    outcome, record = classify(arm, supervision, output, limits)
    return ledger_entry(arm, outcome, record, supervision, limits)
