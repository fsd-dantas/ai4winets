"""Exact min-sum table algebra for DPOP, independent of agents and transport."""

from dataclasses import dataclass
from itertools import product
from math import prod

from .dcop import Assignment, Cost, Factor, Variable, identifier


class TableBudgetExceeded(RuntimeError):
    """Resource exhaustion is not evidence of infeasibility."""

    def __init__(self, required: int, limit: int):
        self.required, self.limit = required, limit
        super().__init__(f'Table needs {required} entries; limit is {limit}')


def check_size(domains, max_entries: int) -> int:
    if type(max_entries) is not int or max_entries < 1:
        raise ValueError('Table entry budget must be a positive integer')
    size = prod(len(d) for d in domains)
    if size > max_entries:
        raise TableBudgetExceeded(size, max_entries)
    return size


def join(factors, *, table_id: str, max_entries: int) -> Factor:
    """Sum factors on their union scope; empty input yields the scalar zero.

    Variable and domain value IDs use lexicographic ordering. A repeated factor ID is
    rejected to catch accidental double counting. Domain order may differ across inputs,
    but the actual allowed values for a shared variable must agree.
    """
    identifier(table_id)
    factors = tuple(factors)
    if len({f.id for f in factors}) != len(factors):
        raise ValueError('A factor may contribute only once to a join')
    domain_by_name = {}
    for factor in factors:
        for name, domain in zip(factor.scope, factor.domains):
            canonical = tuple(sorted(domain))
            if name in domain_by_name and domain_by_name[name] != canonical:
                raise ValueError(f'Inconsistent domain for {name}')
            domain_by_name[name] = canonical
    scope = tuple(sorted(domain_by_name))
    domains = tuple(domain_by_name[n] for n in scope)
    check_size(domains, max_entries)  # Before enumerating or allocating output cells.
    axes = [tuple(scope.index(n) for n in f.scope) for f in factors]
    costs = []
    for values in product(*domains):
        total = Cost(0)
        for factor, indices in zip(factors, axes):
            total += factor.at(tuple(values[i] for i in indices))
        costs.append(total)
    return Factor(table_id, scope, domains, tuple(costs))


@dataclass(frozen=True)
class Projection:
    """One minimizing choice per residual context; None means no feasible choice."""

    variable: Variable
    table: Factor
    choices: tuple[str | None, ...]

    def __post_init__(self):
        object.__setattr__(self, 'choices', tuple(self.choices))
        if self.variable.id in self.table.scope:
            raise ValueError('Eliminated variable remains in projected table')
        if len(self.choices) != len(self.table.costs):
            raise ValueError('Choice table must match projected table cardinality')
        for choice, cost in zip(self.choices, self.table.costs):
            if (choice is None) != (cost.value is None):
                raise ValueError('Only forbidden contexts may omit a choice')
            if choice is not None and choice not in self.variable.domain:
                raise ValueError('Choice is outside eliminated variable domain')

    def choice_for(self, context: Assignment) -> str | None:
        values = dict(context.values)
        if set(values) != set(self.table.scope):
            raise ValueError('Context must cover exactly the projected scope')
        index = 0
        for name, domain in zip(self.table.scope, self.table.domains):
            index = index * len(domain) + domain.index(values[name])
        return self.choices[index]


def minimize(factor: Factor, variable_id: str, *, table_id: str,
             max_entries: int) -> Projection:
    """Eliminate one variable and retain conditional argmin choices.

    Ties choose the lexicographically smallest value ID, even if the input axis is
    ordered differently. All-forbidden slices stay forbidden and have no choice.
    """
    identifier(table_id)
    if variable_id not in factor.scope:
        raise ValueError('Cannot eliminate an absent variable')
    check_size(factor.domains, max_entries)
    domain_by_name = dict(zip(factor.scope, factor.domains))
    variable = Variable(variable_id, tuple(sorted(domain_by_name[variable_id])))
    scope = tuple(sorted(set(factor.scope) - {variable_id}))
    domains = tuple(tuple(sorted(domain_by_name[n])) for n in scope)
    check_size(domains, max_entries)
    costs, choices = [], []
    for context in product(*domains):
        values = dict(zip(scope, context))
        best, choice = Cost(None), None
        for candidate in variable.domain:
            values[variable_id] = candidate
            cost = factor.at(tuple(values[n] for n in factor.scope))
            if cost < best:
                best, choice = cost, candidate
        costs.append(best)
        choices.append(choice)
    return Projection(variable, Factor(table_id, scope, domains, tuple(costs)), tuple(choices))
