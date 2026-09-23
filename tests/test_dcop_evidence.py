from dataclasses import replace
from itertools import combinations
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory
import unittest
import ast
import inspect

from dcop_channel_assignment.agents import solve
from dcop_channel_assignment.dcop import Cost,DcopInstance,Factor,Variable,inequality_factor
from dcop_channel_assignment.evaluation import evaluate,exact_reference,independent_choice
from dcop_channel_assignment.execution import run,save_run,load_run
from dcop_channel_assignment.fixtures import grid_map
from dcop_channel_assignment.inputs import snapshot,border_map
from dcop_channel_assignment.mobility import mobile_sequence,run_epochs,stability_scenario,MobileCellSequence
from dcop_channel_assignment.translation import to_dcop


class EvidenceTests(unittest.TestCase):
    def test_evaluator_has_no_solver_imports(self):
        import dcop_channel_assignment.evaluation as module
        tree=ast.parse(inspect.getsource(module))
        imports=[n for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom))]
        self.assertEqual([n.module for n in imports if isinstance(n,ast.ImportFrom)],['itertools'])
        self.assertFalse(any(isinstance(n,ast.Import) for n in imports))

    def test_mobile_partition_preserves_area_and_excludes_mobile_penalty(self):
        sequence=mobile_sequence()
        for epoch in sequence.epochs:
            self.assertEqual(sum((r.bounds[2]-r.bounds[0])*(r.bounds[3]-r.bounds[1]) for r in epoch.regions),1200)
        arrival=run(sequence.epochs[1])
        moved=stability_scenario(sequence.epochs[2],arrival,penalty=1313,mobile_id='mobile')
        self.assertEqual(dict(moved.scores)['mobile'],(0,100,100,100))

    def test_rendering_uses_checked_record_and_reveals_value(self):
        from dcop_channel_assignment.visualize import replay,colored_svg
        record=run(grid_map(2,2))
        with TemporaryDirectory() as d:
            page=Path(d)/'replay.html'; svg=Path(d)/'map.svg'
            replay(record,page);colored_svg(record,svg)
            text=page.read_text(encoding='utf-8')
            self.assertIn('"kind": "value"',text)
            self.assertIn(record['run_id'],text)
            self.assertIn('c1',svg.read_text())
            self.assertIn('Feasible: True; conflicts: 0',svg.read_text())

    def test_evaluator_rejects_corruption_and_does_not_trust_status(self):
        p = snapshot(grid_map(1,2,preferences=True))
        good = [['ap-00','c1'],['ap-01','c2']]
        self.assertEqual(evaluate(p,good)['objective'],10)
        for bad in (None,[],good[:1],good+[good[0]],[['ap-00','c5'],good[1]],
                    good+[['unknown','c1']],[['ap-00','c1'],['ap-01','c1']]):
            self.assertFalse(evaluate(p,bad)['feasible'])
        baseline = evaluate(p,independent_choice(p))
        self.assertEqual((baseline['conflict_count'],baseline['unary_cost'],baseline['objective']),(1,0,None))

    def test_reference_budget_and_exact_cost(self):
        p = snapshot(grid_map(1,2,preferences=True))
        self.assertEqual(exact_reference(p)['cost'],10)
        self.assertEqual(exact_reference(p,max_assignments=15)['status'],'budget_exceeded')

    def test_two_to_eight_agents_all_roots_and_reordered_inputs(self):
        rng = random.Random(934)
        for n in range(2,9):
            scenario = grid_map(1,n)
            scenario = replace(scenario,scores=tuple((r.ap_id,tuple(rng.randrange(101) for _ in range(4))) for r in scenario.regions))
            expected = exact_reference(snapshot(scenario))
            instance = to_dcop(scenario)
            for root in instance.variables:
                result = solve(instance,root=root.id,max_entries=4096)
                verdict = evaluate(snapshot(scenario),result.assignment.values)
                self.assertTrue(verdict['feasible'])
                self.assertEqual(verdict['objective'],expected['cost'])
            reverse = DcopInstance(tuple(reversed(instance.variables)),tuple(reversed(instance.factors)))
            self.assertEqual(solve(instance,max_entries=4096).assignment,solve(reverse,max_entries=4096).assignment)

    def test_reference_k5_and_feasible_counterpart(self):
        names = [str(i) for i in range(5)]
        edges = list(combinations(names,2))
        p = {'domains':{n:['c1','c2','c3','c4'] for n in names},'scores':{n:[0]*4 for n in names},'edges':edges}
        self.assertEqual(exact_reference(p)['status'],'infeasible')
        p['edges'] = edges[:-1]
        self.assertEqual(exact_reference(p)['cost'],0)

    def test_saved_run_rechecks_hash_and_assignment(self):
        with TemporaryDirectory() as d:
            path = Path(d)/'run.json'
            record = run(grid_map(1,2,preferences=True))
            save_run(record,path)
            self.assertEqual(load_run(path)['evaluation']['objective'],10)
            data = json.loads(path.read_text()); data['cost'] = 999
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):load_run(path)

    def test_source_hashes_ignore_checkout_line_endings(self):
        from dcop_channel_assignment.execution import source_hashes
        with TemporaryDirectory() as lf, TemporaryDirectory() as crlf:
            text = b'"""Module."""\n\nVALUE = 1\n'
            (Path(lf)/'m.py').write_bytes(text)
            (Path(crlf)/'m.py').write_bytes(text.replace(b'\n',b'\r\n'))
            self.assertEqual(source_hashes(lf),source_hashes(crlf))

    def test_saved_text_is_written_with_lf(self):
        from dcop_channel_assignment.visualize import colored_svg
        record = run(grid_map(1,2))
        with TemporaryDirectory() as d:
            save_run(record,Path(d)/'run.json'); colored_svg(record,Path(d)/'map.svg')
            for name in ('run.json','run.json.sha256','map.svg'):
                self.assertNotIn(b'\r\n',(Path(d)/name).read_bytes(),name)

    def test_hand_authored_map_admission(self):
        data = {'id':'chain','regions':[str(i) for i in range(10)],'borders':[[str(i),str(i+1)] for i in range(9)]}
        self.assertTrue(run(border_map(data))['evaluation']['feasible'])
        for edges in (data['borders']+[data['borders'][0]],data['borders']+[['0','0']],data['borders'][:-1]):
            with self.assertRaises(ValueError):border_map({**data,'borders':edges})
        with self.assertRaises(ValueError):
            border_map({'id':'k5','regions':[str(i) for i in range(5)],'borders':list(combinations([str(i) for i in range(5)],2))})

    def test_mobile_epochs_use_only_valid_previous_plans(self):
        sequence = mobile_sequence()
        free,a = run_epochs(sequence,stable=False)
        stable,b = run_epochs(sequence,stable=True)
        self.assertEqual(free[0]['assignment'],stable[0]['assignment'])
        self.assertEqual(len(a),4)
        for records,rows in ((free,a),(stable,b)):
            for record,row in zip(records,rows):
                # The summary must carry the evaluator's count, not a constant.
                self.assertEqual(row['conflicts'],record['evaluation']['conflict_count'])
                self.assertEqual(row['conflicts'],0)
        # A property of this declared fixture, not a guarantee for all sequences.
        self.assertLess(sum(r['reassignments'] for r in b),sum(r['reassignments'] for r in a))
        self.assertGreater(b[1]['base_cost'],a[1]['base_cost'])
        invalid = {**free[0],'assignment':None}
        with self.assertRaises(ValueError):stability_scenario(sequence.epochs[1],invalid,penalty=100,mobile_id='mobile')
        limited,summary = run_epochs(sequence,stable=True,max_entries=1)
        self.assertEqual(len(limited),1)
        self.assertEqual(summary[0]['status'],'budget_exceeded')
