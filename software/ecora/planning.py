"""Three planners over one symbolic representation: forward search, GPS and A*.

docs/ECoRA/decision-methods.md gives each a distinct role. STRIPS is the operator and
state representation, searched here by forward uniform cost, which is the baseline A* is
measured against on the same graph and the same costs. GPS is means-ends analysis. A* is a
search algorithm ranking states by `f(n) = g(n) + h(n)`.

They share the catalog, the costs, the projected initial state and the plan validator, so
a difference between their traces is a difference in search procedure. Every plan they
emit is replayed through the validator before it leaves, and only the validator may say a
goal was achieved.

A* starts from `h = 0`, which makes it a correctness reference against uniform cost rather
than a claim about heuristics. A non-zero heuristic is admitted only once its lower-bound
property has been checked on enumerable problems, and a weighted or cut-off variant would
be a separately labelled treatment that does not inherit the optimality claim.

A bounded search that finds nothing reports that it found nothing within its declared
budget. That is not a proof that the problem is infeasible, and the outcome says so.
"""

import heapq
from functools import partial

from .contracts import Record, digest, require
from .registry import ProviderResult
from .schema import INPUT_TYPES, OUTPUT_TYPES
from .symbolic import Operator, catalog, certificate, successors, validate_plan

VERSION = "planner-v1"


def _ordered(state):
    return tuple(sorted(state))


def uniform_cost(initial, unknown, operators, goals, budget):
    """Forward uniform-cost search: the declared STRIPS baseline."""
    start = frozenset(initial)
    frontier = [(0.0, 0, _ordered(start), ())]
    best = {start: 0.0}
    expansions, tie = 0, 0
    while frontier:
        cost, _, ordered, plan = heapq.heappop(frontier)
        state = frozenset(ordered)
        if set(goals) <= state:
            return plan, cost, {"expansions": expansions, "frontier": len(frontier)}
        if cost > best.get(state, float("inf")):
            continue
        expansions += 1
        if expansions > budget:
            return None, None, {"expansions": expansions, "exhausted": True}
        for operator, following in successors(state, unknown, operators):
            reached = cost + operator.cost
            if reached < best.get(following, float("inf")):
                best[following] = reached
                tie += 1
                heapq.heappush(frontier, (reached, tie, _ordered(following),
                                          plan + (operator.operator_id,)))
    return None, None, {"expansions": expansions, "exhausted": False}


def astar(initial, unknown, operators, goals, budget, heuristic=None):
    """A* on the same graph and costs. With h = 0 it must match uniform cost exactly."""
    estimate = heuristic or (lambda state: 0.0)
    start = frozenset(initial)
    frontier = [(estimate(start), 0.0, 0, _ordered(start), ())]
    best = {start: 0.0}
    expansions, tie = 0, 0
    while frontier:
        _, cost, _, ordered, plan = heapq.heappop(frontier)
        state = frozenset(ordered)
        if set(goals) <= state:
            return plan, cost, {"expansions": expansions, "frontier": len(frontier)}
        if cost > best.get(state, float("inf")):
            continue
        expansions += 1
        if expansions > budget:
            return None, None, {"expansions": expansions, "exhausted": True}
        for operator, following in successors(state, unknown, operators):
            reached = cost + operator.cost
            # An improved path to a known state must be reopened, or optimality is lost.
            if reached < best.get(following, float("inf")):
                best[following] = reached
                tie += 1
                heapq.heappush(frontier, (reached + estimate(following), reached, tie,
                                          _ordered(following), plan + (operator.operator_id,)))
    return None, None, {"expansions": expansions, "exhausted": False}


def gps(initial, unknown, operators, goals, budget, depth_bound=8):
    """Means-ends analysis: pick an unmet goal, choose an operator that reduces it.

    Every goal is rechecked once the plan is built, because achieving a later subgoal can
    undo an earlier one. The difference selected at each step and each failed branch are
    recorded, so a failure can be read rather than guessed at.
    """
    trace, effort = [], {"differences": 0, "backtracks": 0, "expansions": 0}

    def reduce_goal(state, remaining, plan, depth, visited):
        if effort["expansions"] > budget:
            return None
        if not remaining:
            # Recheck every goal, not just the ones still outstanding. Achieving a later
            # subgoal can delete an earlier one, and a plan that undid its own work would
            # otherwise be returned as a solution.
            undone = sorted(set(goals) - state)
            if not undone:
                return plan
            trace.append({"event": "undone_by_later_subgoal", "goals": undone})
            return None
        if depth > depth_bound:
            trace.append({"event": "depth_bound", "depth": depth})
            return None
        difference = remaining[0]
        effort["differences"] += 1
        trace.append({"event": "difference", "goal": difference, "depth": depth})
        for operator in operators:
            if difference not in operator.add:
                continue
            effort["expansions"] += 1
            if not operator.applicable(state, unknown):
                trace.append({"event": "inapplicable", "operator": operator.operator_id,
                              "goal": difference})
                continue
            following = operator.apply(state)
            if _ordered(following) in visited:
                trace.append({"event": "cycle", "operator": operator.operator_id})
                continue
            extended = reduce_goal(following, [goal for goal in remaining[1:]
                                               if goal not in following],
                                   plan + (operator.operator_id,), depth + 1,
                                   visited | {_ordered(following)})
            if extended is not None:
                return extended
            effort["backtracks"] += 1
            trace.append({"event": "backtrack", "operator": operator.operator_id,
                          "goal": difference})
        return None

    start = frozenset(initial)
    outstanding = [goal for goal in goals if goal not in start]
    plan = reduce_goal(start, outstanding, (), 0, {_ordered(start)})
    if plan is None:
        return None, None, {**effort, "trace": trace[:40],
                            "exhausted": effort["expansions"] > budget}
    by_id = {operator.operator_id: operator for operator in operators}
    return plan, sum(by_id[step].cost for step in plan), {**effort, "trace": trace[:40]}


SEARCHES = {"uniform_cost": uniform_cost, "astar": astar, "gps": gps}


class PlannerProvider:
    """Plans a configuration change, or records that it could not."""

    def __init__(self, search):
        self.search = search

    def invoke(self, inputs, prior_state, context):
        watermark = context.data["decision_watermark_s"]
        config = context.data["configuration"]
        problem = next((Record.from_dict(message.data["payload"]) for message in inputs
                        if Record.from_dict(message.data["payload"]).kind == "PlanningProblem"), None)
        if problem is None:
            return ProviderResult((), {}, {"search": self.search}, "no_op",
                                  {"code": "no_problem", "detail": "No planning problem was supplied."})
        data = problem.data
        self._versions = dict(data.get("state_versions", {}))
        known = frozenset(data["known_predicates"])
        unknown = frozenset(data["unknown_predicates"])
        operators = catalog(config["sites"], config["costs"])
        # One agent per declared service, each planning for its own objective. Where no
        # agents are declared the provider plans once for the whole frozen goal set, which
        # is the single-agent case and the default.
        agents = config.get("agents") or [{"agent_id": config.get("agent_id", "agent:planner"),
                                           "service": config.get("service", "ami"),
                                           "goals": list(data["goals"])}]
        frozen = set(data["goals"])
        for agent in agents:
            require(set(agent["goals"]) <= frozen,
                    f"{agent['agent_id']} pursues a goal the study did not freeze")
            require(agent["goals"], f"{agent['agent_id']} declares no goal")
        outputs, traces = [], []
        for agent in agents:
            outputs.append(self._plan_for(agent, config, data, known, unknown, operators,
                                          watermark, traces))
        state = {"plans": prior_state.data["state"].get("plans", 0) + len(outputs)}
        if len(outputs) == 1:
            return ProviderResult((outputs[0],), state, traces[0])
        return ProviderResult(tuple(outputs), state,
                              {"search": self.search, "agents": len(outputs),
                               "per_agent": traces})

    def _plan_for(self, agent, config, data, known, unknown, operators, watermark, traces):
        """One agent's proposal over its own goals, and the trace that produced it."""
        goals = list(agent["goals"])
        budget = min(data["expansion_budget"], config.get("expansion_budget", data["expansion_budget"]))
        search = SEARCHES[self.search]
        extra = {"depth_bound": data.get("horizon_steps", 8)} if self.search == "gps" else {}
        plan, cost, effort = search(known, unknown, operators, goals, budget, **extra)

        if plan is None:
            # Nothing found within this method's policy and budget. Not infeasibility.
            traces.append({"search": self.search, "agent_id": agent["agent_id"], **effort,
                           "outcome": "no_plan_within_budget"})
            return self._proposal(agent, config, watermark, (), 0.0, "unknown", None)
        achieved, final, why = validate_plan(known, unknown, operators, goals, plan)
        reference = None
        if config.get("certify"):
            table = certificate(known, unknown, operators, config.get("state_limit", 64))
            reference = f"certificate:{table['graph_digest'][:16]}"
            if achieved:
                require(abs(table["optimal_costs"][" ".join(sorted(final))] - cost) < 1e-9
                        or self.search == "gps",
                        "a plan claimed optimal does not match the enumerated cost table")
        by_id = {operator.operator_id: operator for operator in operators}
        traces.append({"search": self.search, "agent_id": agent["agent_id"], **effort,
                       "validated": achieved, "validator": why})
        return self._proposal(agent, config, watermark, tuple(by_id[step] for step in plan),
                              cost, "achieved_in_model" if achieved else "unmet", reference)

    def _proposal(self, agent, config, watermark, operators, cost, status, reference):
        steps = [{"operator": operator.action, "target": operator.target,
                  "arguments": dict(operator.arguments),
                  "preconditions": sorted(operator.preconditions),
                  "add_effects": sorted(operator.add), "delete_effects": sorted(operator.delete),
                  "cost": operator.cost} for operator in operators]
        if not steps:
            steps = [{"operator": "no_op", "target": config["sites"][0], "arguments": {},
                      "preconditions": [], "add_effects": [], "delete_effects": [], "cost": 0}]
        return Record("PlanProposal", {
            # The agent is part of the identity: two agents planning at one watermark must
            # not collide on a proposal id, or the resolver would see one contender.
            "proposal_id": f"proposal:{VERSION}:{agent['service']}:{config['sites'][0]}:{watermark}",
            "agent_id": agent["agent_id"], "site_id": config["sites"][0],
            "service": agent["service"], "steps": steps, "assumptions": [],
            "estimated_cost": sum(step["cost"] for step in steps),
            "valid_until_s": watermark + config.get("validity_s", 1),
            "goal_status": status, "certificate_ref": reference,
            # The actuator versions the problem was observed at, carried to the command so
            # a write names the state it was decided against.
            "state_versions": dict(getattr(self, "_versions", {}))})


def planner_binding(registry, capability_ids, configuration, search="uniform_cost"):
    """Register one search over the shared representation and return its binding."""
    require(search in SEARCHES, f"unknown search procedure: {search}")
    require(configuration.get("sites"), "a planner must declare the sites it configures")
    for action in ("select_path", "set_ami_pacing"):
        require(configuration["costs"].get(action, 0) >= 0, f"{action} needs a nonnegative cost")
    spec = Record("ProviderSpec", {
        "stage_id": "planning", "provider_id": f"planning.{search}",
        "provider_version": VERSION, "arm": "proposed",
        "input_types": list(INPUT_TYPES["planning"]), "output_types": list(OUTPUT_TYPES["planning"]),
        "state_schema_version": "1", "capability_ids": list(capability_ids),
        "direct_truth_access": False})
    if not registry.registered("planning", spec.data["provider_id"], VERSION):
        registry.register(spec, partial(PlannerProvider, search))
    return {k: v for k, v in spec.data.items() if k != "direct_truth_access"} | {
        "information_regime": "contract_only", "allow_privileged_inputs": False,
        "configuration": configuration, "configuration_hash": digest(configuration)}
