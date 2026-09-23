"""Generic immutable DCOP inputs; no wireless or execution dependencies."""

from dataclasses import dataclass
from itertools import product


def identifier(value: str) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError("Identifiers must be nonempty strings without outer whitespace")


@dataclass(frozen=True)
class Cost:
    """None is forbidden (+infinity); finite values are exact nonnegative integers.

    The wire representation is an integer or the string 'forbidden', never JSON Infinity.
    """

    value: int | None

    def __post_init__(self):
        if self.value is not None and (type(self.value) is not int or self.value < 0):
            raise ValueError("A cost must be a nonnegative integer or forbidden")

    def __add__(self, other):
        if not isinstance(other, Cost):
            return NotImplemented
        if self.value is None or other.value is None:
            return Cost(None)
        return Cost(self.value + other.value)

    def __lt__(self, other):
        if not isinstance(other, Cost):
            return NotImplemented
        return self.value is not None and (other.value is None or self.value < other.value)

    def to_wire(self) -> int | str:
        return "forbidden" if self.value is None else self.value

    @classmethod
    def from_wire(cls, value):
        if value == "forbidden":
            return cls(None)
        if type(value) is not int:
            raise ValueError("Wire costs must be integers or 'forbidden'")
        return cls(value)


@dataclass(frozen=True)
class Variable:
    id: str
    domain: tuple[str, ...]

    def __post_init__(self):
        identifier(self.id)
        object.__setattr__(self, "domain", tuple(self.domain))
        for value in self.domain:
            identifier(value)
        if not self.domain or len(set(self.domain)) != len(self.domain):
            raise ValueError("Domains must be nonempty and contain unique values")


@dataclass(frozen=True)
class Factor:
    """Dense table in product(*domains) order, with the last axis varying fastest."""

    id: str
    scope: tuple[str, ...]
    domains: tuple[tuple[str, ...], ...]
    costs: tuple[Cost, ...]

    def __post_init__(self):
        identifier(self.id)
        object.__setattr__(self, "scope", tuple(self.scope))
        object.__setattr__(self, "domains", tuple(tuple(d) for d in self.domains))
        object.__setattr__(self, "costs", tuple(self.costs))
        if len(set(self.scope)) != len(self.scope) or len(self.scope) != len(self.domains):
            raise ValueError("Factor axes must match a unique scope")
        size = 1
        for name, domain in zip(self.scope, self.domains):
            Variable(name, domain)
            size *= len(domain)
        if len(self.costs) != size or any(not isinstance(c, Cost) for c in self.costs):
            raise ValueError("Factor table cardinality or cost type is invalid")

    def at(self, values: tuple[str, ...]) -> Cost:
        if len(values) != len(self.scope):
            raise ValueError("Assignment arity does not match factor scope")
        index = 0
        for value, domain in zip(values, self.domains):
            index = index * len(domain) + domain.index(value)
        return self.costs[index]


@dataclass(frozen=True)
class Assignment:
    values: tuple[tuple[str, str], ...]

    def __post_init__(self):
        object.__setattr__(self, "values", tuple(sorted(tuple(p) for p in self.values)))
        for name, value in self.values:
            identifier(name)
            identifier(value)
        if len({name for name, _ in self.values}) != len(self.values):
            raise ValueError("An assignment cannot repeat a variable")


@dataclass(frozen=True)
class LocalView:
    variable: Variable
    neighbors: tuple[Variable, ...]
    factors: tuple[Factor, ...]


@dataclass(frozen=True)
class DcopInstance:
    variables: tuple[Variable, ...]
    factors: tuple[Factor, ...]

    def __post_init__(self):
        object.__setattr__(self, "variables", tuple(self.variables))
        object.__setattr__(self, "factors", tuple(self.factors))
        names = {v.id: v.domain for v in self.variables}
        if not names or len(names) != len(self.variables):
            raise ValueError("Instance requires uniquely identified variables")
        if len({f.id for f in self.factors}) != len(self.factors):
            raise ValueError("Factor identifiers must be unique")
        for factor in self.factors:
            for name, domain in zip(factor.scope, factor.domains):
                if names.get(name) != domain:
                    raise ValueError("Factor scope/domain disagrees with instance")

    def local_view(self, variable_id: str) -> LocalView:
        variables = {v.id: v for v in self.variables}
        if variable_id not in variables:
            raise ValueError("Unknown agent variable")
        factors = tuple(f for f in self.factors if variable_id in f.scope)
        neighbors = sorted({name for f in factors for name in f.scope} - {variable_id})
        return LocalView(variables[variable_id], tuple(variables[n] for n in neighbors), factors)

    def cost(self, assignment: Assignment) -> Cost:
        values = dict(assignment.values)
        if set(values) != {v.id for v in self.variables}:
            raise ValueError("Assignment must cover exactly the instance variables")
        if any(values[v.id] not in v.domain for v in self.variables):
            raise ValueError("Assignment value outside variable domain")
        total = Cost(0)
        for factor in self.factors:
            total += factor.at(tuple(values[name] for name in factor.scope))
        return total


def inequality_factor(name: str, left: Variable, right: Variable) -> Factor:
    return Factor(name, (left.id, right.id), (left.domain, right.domain),
                  tuple(Cost(None if a == b else 0)
                        for a, b in product(left.domain, right.domain)))
