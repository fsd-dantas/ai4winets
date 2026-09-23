"""Gated worker. Resource enforcement belongs to the parent application service."""

import sys


def main():
    if sys.stdin.buffer.readline() != b'go\n':
        return 4
    try:
        import json
        from pathlib import Path
        import time
        from dcop_channel_assignment.evaluation import evaluate, independent_choice
        from dcop_channel_assignment.execution import run, save_run
        from dcop_channel_assignment.inputs import border_map, snapshot

        request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
        scenario = border_map(request['map'])
        problem = snapshot(scenario)
        start = time.perf_counter()
        if request['arm'] == 'dpop':
            record = run(scenario, root=request['root'], max_entries=request['table_entries'])
        elif request['arm'] == 'independent':
            assignment = independent_choice(problem)
            record = {'status': 'completed', 'problem': problem, 'assignment': assignment,
                      'evaluation': evaluate(problem, assignment), 'messages': [],
                      'metrics': {'messages': {}, 'max_separator': None,
                                  'max_join_entries': None, 'max_outgoing_entries': None,
                                  'transmitted_entries': 0}}
        else:
            raise ValueError('Unknown arm')
        record['arm_call_seconds'] = time.perf_counter() - start
        # Canonical compact ASCII JSON payload only, excluding message envelopes.
        record['metrics']['delivered_payload_bytes'] = sum(
            len(json.dumps(m['payload'], sort_keys=True, separators=(',', ':'),
                           ensure_ascii=True).encode('ascii')) for m in record['messages'])
        record['metrics']['delivered_entries'] = record['metrics']['transmitted_entries']
        save_run(record, Path(sys.argv[2]))
        return 0
    except MemoryError:
        # Exit code is the fallback if there is insufficient memory to write JSON.
        return 73
    except Exception as exc:
        # No traceback or host path enters the published run ledger.
        print(type(exc).__name__, flush=True)
        return 74


if __name__ == '__main__':
    sys.exit(main())
