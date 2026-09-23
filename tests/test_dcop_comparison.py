from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from dcop_comparison.limited import INTERRUPTED, classify, ledger_entry, limited_run
from dcop_comparison.resources import Limits, supervise


def grid(n):
    names = [f'r{i:03d}' for i in range(n * n)]
    borders = [[names[i], names[i + 1]] for i in range(n * n) if (i + 1) % n]
    borders += [[names[i], names[i + n]] for i in range(n * n - n)]
    return {'id': f'grid-{n}', 'regions': names, 'borders': borders}


def exited(returncode, peak=10 * 2**20):
    return {'status': 'exited', 'returncode': returncode, 'wall_seconds': 0.1,
            'peak_process_commit_bytes': peak, 'memory_backend': 'test'}


class ClassificationTests(unittest.TestCase):
    def test_limits_reject_nonpositive_and_nonfinite_values(self):
        for bad in ({'wall_seconds': 0}, {'wall_seconds': float('inf')}, {'memory_bytes': 0},
                    {'table_entries': -1}, {'table_entries': 1.5}):
            with self.assertRaises(ValueError):
                Limits(**bad)

    def test_every_stop_is_interrupted_and_never_scored(self):
        limits = Limits(memory_bytes=100 * 2**20)
        cases = [({'status': 'time_exceeded', 'returncode': 1, 'wall_seconds': 1,
                   'peak_process_commit_bytes': 1, 'memory_backend': 'test'}, 'time_exceeded'),
                 ({'status': 'execution_error', 'returncode': None, 'wall_seconds': 0,
                   'peak_process_commit_bytes': None, 'memory_backend': 'test'}, 'execution_error'),
                 (exited(73), 'memory_exceeded'),
                 (exited(1, peak=99 * 2**20), 'memory_exceeded'),
                 (exited(1), 'execution_error'),
                 (exited(74), 'execution_error'),
                 # A clean exit with no trustworthy output is still an error, not a result.
                 (exited(0), 'execution_error')]
        with TemporaryDirectory() as d:
            for supervision, expected in cases:
                outcome, record = classify('dpop', supervision, Path(d) / 'missing.json', limits)
                self.assertEqual(outcome, expected)
                self.assertIsNone(record)
                entry = ledger_entry('dpop', outcome, record, supervision, limits)
                self.assertTrue(entry['interrupted'])
                self.assertIsNone(entry['assignment'])
                self.assertIsNone(entry['feasible'])
                self.assertIsNone(entry['objective'])

    def test_budget_stop_is_interrupted_even_with_a_record(self):
        entry = ledger_entry('dpop', 'budget_exceeded', {'evaluation': {'feasible': False}, 'assignment': None,
                                                         'metrics': {}}, exited(0), Limits())
        self.assertIn('budget_exceeded', INTERRUPTED)
        self.assertTrue(entry['interrupted'])
        self.assertIsNone(entry['feasible'])


@unittest.skipUnless(sys.platform == 'win32', 'Enforced limits use Windows job objects')
class EnforcementTests(unittest.TestCase):
    def test_wall_time_is_enforced(self):
        with TemporaryDirectory() as d:
            result = supervise([sys.executable, '-c', 'import sys,time; sys.stdin.readline(); time.sleep(30)'],
                               Limits(wall_seconds=0.5), log_path=Path(d) / 'log')
        self.assertEqual(result['status'], 'time_exceeded')
        self.assertLess(result['wall_seconds'], 5)

    def test_the_interpreter_itself_runs_inside_the_job(self):
        # A venv's python.exe is a launcher; the process that executes this code is its child.
        check = ('import ctypes, sys; sys.stdin.readline(); k = ctypes.windll.kernel32; r = ctypes.c_int(); '
                 'k.IsProcessInJob(ctypes.c_void_p(k.GetCurrentProcess()), None, ctypes.byref(r)); '
                 'sys.exit(0 if r.value else 9)')
        with TemporaryDirectory() as d:
            result = supervise([sys.executable, '-c', check], Limits(), log_path=Path(d) / 'log')
        self.assertEqual((result['status'], result['returncode']), ('exited', 0))

    def test_memory_is_enforced(self):
        with TemporaryDirectory() as d:
            result = supervise([sys.executable, '-c', 'import sys; sys.stdin.readline(); b = bytearray(400 * 2**20)'],
                               Limits(memory_bytes=128 * 2**20), log_path=Path(d) / 'log')
            self.assertIn('MemoryError', (Path(d) / 'log').read_text())
        self.assertNotEqual(result['returncode'], 0)

    def test_completed_arms_are_verified_and_scored(self):
        with TemporaryDirectory() as d:
            dpop = limited_run('dpop', grid(3), Path(d) / 'dpop')
            independent = limited_run('independent', grid(3), Path(d) / 'independent')
        self.assertEqual((dpop['outcome'], dpop['feasible'], dpop['objective']), ('optimal_cost', True, 0))
        self.assertFalse(dpop['interrupted'])
        # Every region takes its cheapest channel; neighbors then collide.
        self.assertEqual(independent['outcome'], 'completed')
        self.assertFalse(independent['feasible'])
        self.assertGreater(independent['conflict_count'], 0)

    def test_tampered_output_is_an_execution_error(self):
        with TemporaryDirectory() as d:
            limited_run('dpop', grid(3), Path(d))
            record = Path(d) / 'record.json'
            record.write_text(record.read_text().replace('"optimal_cost"', '"infeasible"'))
            outcome, _ = classify('dpop', exited(0), record, Limits())
        self.assertEqual(outcome, 'execution_error')

    def test_each_limit_stops_a_wide_map_without_a_verdict(self):
        cases = [('budget_exceeded', Limits(table_entries=1000)),
                 ('memory_exceeded', Limits(memory_bytes=96 * 2**20, table_entries=10**9, wall_seconds=120)),
                 ('time_exceeded', Limits(wall_seconds=1.0, table_entries=10**9, memory_bytes=4 * 2**30))]
        for expected, limits in cases:
            with self.subTest(expected), TemporaryDirectory() as d:
                entry = limited_run('dpop', grid(10), Path(d), limits=limits)
                self.assertEqual(entry['outcome'], expected)
                self.assertTrue(entry['interrupted'])
                self.assertIsNone(entry['assignment'])
                self.assertIsNone(entry['feasible'])


if __name__ == '__main__':
    unittest.main()
