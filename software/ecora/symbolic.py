"""The shared symbolic core: state projection, operator catalog and plan validator.

One representation, used by every planner, so that a difference between STRIPS forward
search, GPS and A* is a difference in search and not in what they were searching over.
docs/ECoRA/decision-methods.md fixes the semantics: a state is a set of known ground
predicates, an operator carries preconditions, add effects, delete effects and a declared
cost, and for an applicable action the successor is `(S - delete) union add`.

Two boundaries are enforced here rather than left to each planner's good manners.

An unknown precondition prohibits an edge. Closed-world reasoning is permitted only over
an explicitly enumerated, sufficiently observed subdomain; a physical condition nobody
observed must not become false because no one wrote it down. In practice that is what
stops a planner from switching to a leg it has no evidence it can reach.

Effects are configuration, never predicted service. Selecting a path can establish that
the path is selected; it cannot establish that a deadline will be met. A performance goal
would need a documented predictive abstraction and its own empirical evaluation, so the
planners target configuration subgoals and assurance tests the service that follows.
"""

from dataclasses import dataclass
from itertools import product

from .contracts import digest, require

PATHS = ("lte", "alternative")
PACING = ("normal", "restricted", "minimum")


def predicate(fluent, site, value):
    return f"{fluent}:{site}:{value}"


@dataclass(frozen=True)
class Operator:
    """A configuration change with a declared cost. It asserts nothing about service."""

    operator_id: str
    action: str
    target: str
    arguments: tuple
    preconditions: frozenset
    add: frozenset
    delete: frozenset
    cost: float

    def applicable(self, state, unknown):
        """Applicable only when every precondition is known to hold."""
        if self.preconditions & unknown:
            return False
        return self.preconditions <= state

    def apply(self, state):
        return frozenset((state - self.delete) | self.add)


def catalog(sites, costs):
    """Every configuration edge the action catalog permits, as ground operators.

    A state-preserving edge is excluded: selecting the path already selected changes
    nothing and would only pad a search with zero-progress successors.
    """
    operators = []
    for site in sites:
        for chosen in PATHS:
            operators.append(Operator(
                operator_id=f"select_path:{site}:{chosen}", action="select_path", target=site,
                arguments=(("path", chosen),),
                preconditions=frozenset({predicate("reachable", site, chosen)}),
                add=frozenset({predicate("selected_path", site, chosen)}),
                delete=frozenset(predicate("selected_path", site, other)
                                 for other in PATHS if other != chosen),
                cost=costs["select_path"]))
        # One edge per ordered pair of profiles, each requiring the profile it moves from.
        # A pacing operator carrying no precondition at all could be planned without
        # knowing the current profile, and its delete effect would then remove a predicate
        # nobody had established. It also made the lever unreachable in practice: the
        # resolver refuses to issue a mutation with no precondition to cite, so a plan
        # that changed pacing was admitted and then never became a command.
        for profile in PACING:
            for current in PACING:
                if current == profile:
                    continue
                operators.append(Operator(
                    operator_id=f"set_ami_pacing:{site}:{current}:{profile}",
                    action="set_ami_pacing", target=site, arguments=(("profile", profile),),
                    preconditions=frozenset({predicate("pacing", site, current)}),
                    add=frozenset({predicate("pacing", site, profile)}),
                    delete=frozenset({predicate("pacing", site, current)}),
                    cost=costs["set_ami_pacing"]))
    # An operator with no precondition has nothing to cite, and the resolver refuses to
    # issue a mutation with no precondition evidence. Such an operator is planned, admitted
    # and then silently never becomes a command. Refuse it where it is declared instead of
    # discovering it as a command that was never built.
    for operator in operators:
        require(operator.preconditions,
                f"{operator.operator_id} declares no precondition, so no command could "
                "cite evidence for it and the action could never be issued")
    return tuple(operators)


def successors(state, unknown, operators):
    for operator in operators:
        if not operator.applicable(state, unknown):
            continue
        following = operator.apply(state)
        if following == state:
            continue
        yield operator, following


def validate_plan(initial, unknown, operators, goals, plan):
    """Replay a plan and report whether it is executable and whether it met its goals.

    A planner may only claim a goal is achieved when this says so. Structural validity and
    goal achievement are separate: a one-step or empty plan can be perfectly well formed
    while leaving every goal unmet, and it records that rather than claiming a solution.
    """
    by_id = {operator.operator_id: operator for operator in operators}
    state = frozenset(initial)
    for index, step in enumerate(plan):
        operator = by_id.get(step)
        if operator is None:
            return False, state, f"step {index} names an operator outside the catalog"
        if not operator.applicable(state, unknown):
            return False, state, f"step {index} ({step}) is not applicable in its state"
        state = operator.apply(state)
    unmet = sorted(set(goals) - state)
    return not unmet, state, None if not unmet else f"unmet goals: {', '.join(unmet)}"


def enumerate_space(initial, unknown, operators, limit):
    """The reachable configuration space, with the optimal cost to each state.

    This is the planning certificate: an exact cost table over a bounded, finite graph.
    It certifies optimality for this symbolic problem only, and says nothing about the
    packet service that configuration eventually produces.
    """
    import heapq
    start = frozenset(initial)
    best = {start: 0.0}
    frontier = [(0.0, sorted(start))]
    while frontier:
        cost, ordered = heapq.heappop(frontier)
        state = frozenset(ordered)
        if cost > best.get(state, float("inf")):
            continue
        for operator, following in successors(state, unknown, operators):
            reached = cost + operator.cost
            if reached < best.get(following, float("inf")):
                best[following] = reached
                require(len(best) <= limit, "the configuration space exceeded its declared bound")
                heapq.heappush(frontier, (reached, sorted(following)))
    return best


def certificate(initial, unknown, operators, limit):
    table = enumerate_space(initial, unknown, operators, limit)
    return {"states": len(table),
            "graph_digest": digest(sorted([sorted(state), cost] for state, cost in table.items())),
            "optimal_costs": {" ".join(sorted(state)): cost for state, cost in sorted(
                table.items(), key=lambda item: sorted(item[0]))}}
