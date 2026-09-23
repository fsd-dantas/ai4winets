from itertools import product
import random
import unittest
from unittest.mock import patch

from dcop_channel_assignment.dcop import Assignment, Cost, Factor, Variable, inequality_factor
from dcop_channel_assignment.tables import Projection, TableBudgetExceeded, join, minimize


class TableTests(unittest.TestCase):
    def test_join_and_projection_match_independent_enumeration(self):
        rng = random.Random(381)
        for trial in range(100):
            # Both factor scope and value ordering intentionally differ.
            rows_ba = {(b,a):rng.choice([None,0,1,4,9])
                       for b,a in product(('z','x'),('2','1'))}
            rows_cb = {(c,b):rng.choice([None,0,2,7])
                       for c,b in product(('q','p'),('x','z'))}
            f = Factor('f',('b','a'),(('z','x'),('2','1')),tuple(Cost(v) for v in rows_ba.values()))
            g = Factor('g',('c','b'),(('q','p'),('x','z')),tuple(Cost(v) for v in rows_cb.values()))
            table = join((f,g),table_id='sum',max_entries=8)
            self.assertEqual(table,join((g,f),table_id='sum',max_entries=8))
            projected = minimize(table,'b',table_id='util',max_entries=8)
            for a,c in product(('1','2'),('p','q')):
                candidates = []
                for b in ('x','z'):
                    left,right = rows_ba[b,a],rows_cb[c,b]
                    expected = None if left is None or right is None else left+right
                    self.assertEqual(table.at((a,b,c)),Cost(expected))
                    if expected is not None:
                        candidates.append((expected,b))
                expected_cost,expected_choice = min(candidates) if candidates else (None,None)
                self.assertEqual(projected.table.at((a,c)),Cost(expected_cost))
                self.assertEqual(projected.choice_for(Assignment((('c',c),('a',a)))),expected_choice)

    def test_shared_preference_requires_locally_more_expensive_choice(self):
        a,b = Variable('a',('c1','c2')),Variable('b',('c1','c2'))
        local = Factor('local',('b',),(b.domain,),(Cost(0),Cost(10)))
        table = join((local,inequality_factor('edge',a,b)),table_id='joined',max_entries=4)
        projection = minimize(table,'b',table_id='util',max_entries=4)
        self.assertEqual(projection.table.costs,(Cost(10),Cost(0)))
        self.assertEqual(projection.choices,('c2','c1'))

    def test_ties_use_value_id_not_input_order(self):
        table = Factor('f',('x',),(('z','a'),),(Cost(5),Cost(5)))
        result = minimize(table,'x',table_id='root',max_entries=2)
        self.assertEqual(result.table.scope,())
        self.assertEqual(result.choice_for(Assignment(())),'a')

    def test_all_forbidden_context_has_no_assignment(self):
        table = Factor('f',('x',),(('a','b'),),(Cost(None),Cost(None)))
        result = minimize(table,'x',table_id='root',max_entries=2)
        self.assertEqual(result.table.costs,(Cost(None),))
        self.assertIsNone(result.choice_for(Assignment(())))

    def test_scalar_and_empty_join_identities(self):
        zero = join((),table_id='zero',max_entries=1)
        self.assertEqual(zero.costs,(Cost(0),))
        f = Factor('f',('x',),(('a',),),(Cost(3),))
        self.assertEqual(join((f,zero),table_id='j',max_entries=1).costs,f.costs)
        forbidden = Factor('infinity',(),(),(Cost(None),))
        self.assertEqual(join((f,forbidden),table_id='j',max_entries=1).costs,(Cost(None),))

    def test_budget_rejected_before_enumeration(self):
        factors = tuple(Factor(str(i),(str(i),),(('a','b'),),(Cost(0),Cost(0))) for i in range(20))
        with patch('dcop_channel_assignment.tables.product',side_effect=AssertionError('enumerated')):
            with self.assertRaises(TableBudgetExceeded) as caught:
                join(factors,table_id='huge',max_entries=1_000_000)
        self.assertEqual(caught.exception.required,1_048_576)
        self.assertEqual(caught.exception.limit,1_000_000)
        with self.assertRaises(TableBudgetExceeded):
            minimize(factors[0],'0',table_id='small',max_entries=1)

    def test_invalid_budgets_and_double_counting_rejected(self):
        f = Factor('f',('x',),(('a',),),(Cost(0),))
        for budget in (0,-1,True,1.5):
            with self.subTest(budget=budget),self.assertRaises(ValueError):
                join((f,),table_id='j',max_entries=budget)
        with self.assertRaises(ValueError):join((f,f),table_id='j',max_entries=2)
        g = Factor('g',('x',),(('b',),),(Cost(0),))
        with self.assertRaises(ValueError):join((f,g),table_id='j',max_entries=2)
        with self.assertRaises(ValueError):minimize(f,'missing',table_id='p',max_entries=1)

    def test_context_and_choice_invariants(self):
        f = Factor('f',('a','b'),(('0','1'),('0','1')),(Cost(0),)*4)
        projection = minimize(f,'b',table_id='p',max_entries=4)
        for context in ((),(('a','2'),),(('a','0'),('extra','0'))):
            with self.assertRaises(ValueError):projection.choice_for(Assignment(context))
        with self.assertRaises(ValueError):Projection(projection.variable,projection.table,(None,None))
        with self.assertRaises(ValueError):Projection(projection.variable,projection.table,('bad','bad'))
