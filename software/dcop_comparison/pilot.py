"""Execute the predeclared 24-run DPOP comparison pilot on Windows."""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import sys

from .design import canonical, digest, pilot_cases
from .resources import Limits, supervise


DEFAULT_LIMITS = Limits(wall_seconds=30.0, memory_bytes=512 * 1024 * 1024,
                        table_entries=1_000_000)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True).encode('ascii') + b'\n')


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def execute(output, *, limits=DEFAULT_LIMITS):
    output = Path(output)
    config, results = output / 'configuration', output / 'results'
    cases = pilot_cases()
    protocol = {
        'format': 'dcop-comparison-pilot-v1', 'phase': 'pilot',
        'main_matrix': {'sizes': [10, 12, 16, 20], 'densities': ['sparse', 'dense'],
                        'maps_per_stratum': 3, 'profiles': ['shared', 'independent'],
                        'cost_seeds_per_map': 10, 'arms': ['dpop', 'independent'],
                        'scheduled_runs': 960, 'status': 'not_frozen_or_executed'},
        'pilot_matrix': {'sizes': [10, 16, 20], 'densities': ['sparse', 'dense'],
                         'maps_per_stratum': 1, 'profiles': ['shared', 'independent'],
                         'cost_seeds_per_map': 1, 'arms': ['dpop', 'independent'],
                         'scheduled_runs': 24},
        'generator': 'random tree plus shuffled candidate edges admitted by NetworkX planarity; non-uniform',
        'streams': 'SHA-256-derived topology and cost Python MT streams; separated',
        'root': 'lowest agent ID', 'neighbor_order': 'ascending',
        'limits': {'wall_seconds': limits.wall_seconds,
                   'memory_bytes': limits.memory_bytes,
                   'table_entries': limits.table_entries,
                   'memory_metric': 'Windows Job Object peak process committed bytes',
                   'wall_window': 'before Popen until worker termination, includes Python startup',
                   'bootstrap_memory': 'Python interpreter starts suspended inside the job; all child processes inherit it'},
        'payload_bytes': 'sum of compact sorted ASCII JSON encodings of delivered message payloads, without envelopes',
        'comparison': 'paired on identical map, costs, root and budgets; independent choice may be infeasible',
        'failure_rule': 'time_exceeded, memory_exceeded, table_budget_exceeded, execution_error distinct; no objective assigned to failures',
        'pilot_exclusion': 'pilot seeds excluded from the subsequent main study',
        'analysis': 'descriptive only; no intervals, ranking or population generalization from pilot',
        'hypothesis': 'larger separators increase UTIL burden; independent local choice can conflict',
        'simulation_declaration': 'docs/dcop-channel-assignment/simulation-declaration.md',
        'network': 'synthetic planar dual graph; no RF, PHY, traffic or service metrics',
    }
    write_json(config / 'pilot-protocol.json', protocol)
    protocol_hash = file_hash(config / 'pilot-protocol.json')
    schedule = []
    for case in cases:
        name = case['key']
        write_json(config / f'{name}.json', case)
        for arm in ('dpop', 'independent'):
            schedule.append({'key': name, 'arm': arm, 'case_hash': file_hash(config / f'{name}.json'),
                             'map_hash': digest(case['map'])})
    # Randomized *pair* order for timing, with randomized arm order within each pair.
    rng = random.Random(20260923)
    pairs = [schedule[i:i + 2] for i in range(0, len(schedule), 2)]
    for pair in pairs:
        rng.shuffle(pair)
    rng.shuffle(pairs)
    schedule = [item for pair in pairs for item in pair]
    write_json(config / 'schedule.json', {'protocol_hash': protocol_hash,
                                           'order_seed': 20260923, 'runs': schedule})
    ledger = []
    software = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env['PYTHONPATH'] = str(software)
    for item in schedule:
        case = next(c for c in cases if c['key'] == item['key'])
        key = item['key'] + '-' + item['arm']
        request = {'map': case['map'], 'arm': item['arm'], 'root': min(case['map']['regions']),
                   'table_entries': limits.table_entries}
        request_path = config / 'requests' / f'{key}.json'
        run_path = results / 'runs' / f'{key}.json.gz'
        log_path = results / 'logs' / f'{key}.txt'
        write_json(request_path, request)
        observation = supervise([sys.executable, '-m', 'dcop_comparison.worker',
                                  str(request_path), str(run_path)], limits,
                                 log_path=log_path, env=env)
        status = observation['status']
        record = None
        if status == 'exited':
            if observation['returncode'] == 73:
                status = 'memory_exceeded'
            elif observation['returncode'] == 0 and run_path.exists():
                import gzip
                record = json.loads(gzip.decompress(run_path.read_bytes()))
                status = ('table_budget_exceeded' if record['status'] == 'budget_exceeded'
                          else record['status'])
            else:
                status = 'execution_error'
        if status != 'execution_error' and log_path.exists() and log_path.stat().st_size == 0:
            log_path.unlink()
        ledger.append({'key': key, 'arm': item['arm'], 'case_hash': item['case_hash'],
                       'map_hash': item['map_hash'], 'protocol_hash': protocol_hash,
                       'outcome': status, 'record_hash': file_hash(run_path) if record else None,
                       'evaluation': record['evaluation'] if record else None,
                       'metrics': record['metrics'] if record else None,
                       'arm_call_seconds': record['arm_call_seconds'] if record else None,
                       'resource': observation})
        print(f'{len(ledger):02d}/24 {key}: {status}', flush=True)
    results.mkdir(parents=True, exist_ok=True)
    write_json(results / 'ledger.json', {'protocol_hash': protocol_hash, 'runs': ledger,
                                         'environment': {'python': platform.python_version(),
                                                         'system': platform.system(),
                                                         'release': platform.release()},
                                         'status_counts': dict(sorted(Counter(r['outcome'] for r in ledger).items()))})
    entries = {str(p.relative_to(output)).replace('\\', '/'): file_hash(p)
               for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'manifest.json'}
    write_json(output / 'manifest.json', {'files': entries, 'protocol_hash': protocol_hash})
    return ledger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    execute(args.output)


if __name__ == '__main__':
    main()
