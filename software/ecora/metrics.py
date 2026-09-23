"""Coordination and reasoning measurement, read from what a run recorded.

These measure how a controller behaved, not how well it served. docs/ECoRA/v1-scope.md is
explicit that stability has no service predicate, so no verdict here consults delivery,
deadlines or any other service outcome. A controller that thrashed while meeting its
requirements is unstable, and one that sat still while failing them is stable and failing;
collapsing the two would hide exactly the distinction this is for.

Everything comes from recorded evidence. Nothing reads model truth, so a measurement can
be recomputed from a stored run by anyone holding the artifacts, and no measurement can
quietly depend on something the controller was never allowed to see.

What cannot be measured from the evidence at hand is reported as unknown. Service
starvation is the standing example: it needs per-reading delivery evidence that the v1
observation contract does not carry, so what is reported here is coordination starvation,
meaning an agent that kept proposing and kept being refused. The two are not the same
thing and are not presented as though they were.
"""

from .contracts import Record, require

STAGES_READ = ("diagnosis", "planning", "resolution", "action")


def _measure(metric, unit, value, *, numerator=0, denominator=0, service="shared"):
    known = value is not None
    # These measure the controller, not a service class, so they are shared by default.
    # A per-service outcome comes from the cohorts, which carry their own service.
    return {"metric": metric, "service": service, "unit": unit, "value": value,
            "quality": "measured" if known else "unknown",
            "numerator": numerator, "denominator": denominator}


def read_run(store, epochs):
    """Collect the per-epoch evidence a recorded run left behind."""
    collected = []
    for index in range(epochs):
        epoch = {"index": index, "decisions": [], "commands": [], "receipts": [],
                 "traces": {}, "proposals": {}}
        for stage in STAGES_READ:
            dataset = f"dataset:{stage}:{index}"
            try:
                messages = store.messages(dataset)
            except Exception:
                continue
            invocation = store.invocation(f"{stage}:{index}")
            epoch["traces"][stage] = store.get(invocation.data["trace_hash"]).data["state"]
            for message in messages:
                payload = Record.from_dict(message.data["payload"])
                if payload.kind == "ResolutionRecord":
                    epoch["decisions"].extend(payload.data["decisions"])
                elif payload.kind == "ActionCommand":
                    epoch["commands"].append(payload.data)
                elif payload.kind == "ActionReceipt":
                    epoch["receipts"].append(payload.data)
                elif payload.kind == "PlanProposal":
                    epoch["plan"] = payload.data
                    # Starvation follows the agent, not the proposal: a fresh proposal id
                    # each epoch would otherwise reset the count of an agent kept waiting.
                    epoch["proposals"][payload.data["proposal_id"]] = payload.data["agent_id"]
        collected.append(epoch)
    return collected


def _applied(epoch):
    return [receipt for receipt in epoch["receipts"] if receipt["disposition"] == "applied"]


def _settings(epochs):
    """The sequence of settings actually applied, as (actuator, value) in order."""
    applied = {receipt["command_id"] for epoch in epochs for receipt in _applied(epoch)}
    sequence = []
    for epoch in epochs:
        for command in epoch["commands"]:
            if command["command_id"] in applied:
                value = next(iter(command["arguments"].values()), None)
                sequence.append((f"{command['target']}/{command['operator']}", value,
                                 epoch["index"]))
    return sequence


def oscillation(epochs):
    """Reversals: a setting returning to a value it had already left."""
    reversals, history = 0, {}
    for actuator, value, _ in _settings(epochs):
        seen = history.setdefault(actuator, [])
        if len(seen) >= 1 and seen[-1] != value and value in seen:
            reversals += 1
        if not seen or seen[-1] != value:
            seen.append(value)
    return reversals


def repeated_actions(epochs):
    """Applications that set a value the actuator already held. Churn without change."""
    repeats, current = 0, {}
    for actuator, value, _ in _settings(epochs):
        if current.get(actuator) == value:
            repeats += 1
        current[actuator] = value
    return repeats


def asked_for_a_mutation(epoch):
    """Whether anything in this epoch actually requested a change.

    A settled controller proposes a no-op: its goal already holds, so there is nothing to
    issue. Refusing a no-op is not a contention anybody lost, and counting it as one would
    report a system that had finished as a system that was stuck.
    """
    plan = epoch.get("plan")
    if plan is None:
        return bool(epoch["commands"])
    return any(step["operator"] != "no_op" for step in plan["steps"])


def deadlock_epochs(epochs):
    """Epochs where a change was asked for, every proposal was refused, and none issued."""
    stalled = []
    for epoch in epochs:
        if not epoch["decisions"] or not asked_for_a_mutation(epoch):
            continue
        if any(decision["disposition"] == "admit" for decision in epoch["decisions"]):
            continue
        stalled.append(epoch["index"])
    return stalled


def coordination_starvation(epochs):
    """The longest run of consecutive epochs in which one agent proposed and was refused.

    This is starvation of a coordination mechanism, not of a service. An agent that never
    wins its contention is being starved of the actuator; whether any reading missed its
    deadline is a service question the observation contract cannot answer here.
    """
    longest, running = {}, {}
    for epoch in epochs:
        contended = set()
        if not asked_for_a_mutation(epoch):
            # Nobody was contending, so nobody was kept waiting.
            continue
        for decision in epoch["decisions"]:
            owner = epoch.get("proposals", {}).get(decision["proposal_id"],
                                                   decision["proposal_id"])
            contended.add(owner)
            if decision["disposition"] == "admit":
                running[owner] = 0
            else:
                running[owner] = running.get(owner, 0) + 1
            longest[owner] = max(longest.get(owner, 0), running[owner])
        for owner in set(running) - contended:
            running[owner] = 0
    return max(longest.values(), default=0), longest


def reasoning_effort(epochs):
    """What the decision stages spent, as each stage recorded it."""
    effort = {"activations": 0, "expansions": 0, "passes": 0, "plan_steps": 0, "plan_cost": 0.0}
    for epoch in epochs:
        diagnosis = epoch["traces"].get("diagnosis", {})
        planning = epoch["traces"].get("planning", {})
        effort["activations"] += diagnosis.get("activations", 0)
        effort["passes"] += diagnosis.get("passes", 0)
        effort["expansions"] += planning.get("expansions", 0)
        plan = epoch.get("plan")
        if plan:
            effort["plan_steps"] += len(plan["steps"])
            effort["plan_cost"] += plan["estimated_cost"]
    return effort


def coordination_overhead(epochs):
    """What coordination cost, with the substrate that produced the numbers named."""
    overhead = {"mark_writes": 0, "mark_reads": 0, "mark_bytes": 0, "conflicts": 0,
                "concessions": 0, "transport": None}
    for epoch in epochs:
        trace = epoch["traces"].get("resolution", {})
        marks = trace.get("marks")
        if marks:
            overhead["mark_writes"] += marks["writes"]
            overhead["mark_reads"] += marks["reads"]
            overhead["mark_bytes"] += marks["bytes"]
            overhead["transport"] = marks["transport"]
        overhead["conflicts"] += trace.get("contended_resources", 0)
        overhead["concessions"] += trace.get("conceded", 0)
    return overhead


def claim_churn(epochs):
    """Changed owner, resource or intent. A same-intent refresh is overhead, not churn."""
    churn, held = 0, set()
    for epoch in epochs:
        trace = epoch["traces"].get("resolution", {})
        claims = {(event.get("resource"), owner)
                  for event in trace.get("events", [])
                  for owner in event.get("live_claims", [])}
        if claims and claims != held:
            churn += len(claims ^ held)
        held = claims or held
    return churn


def stability(epochs, limits, period_s):
    """Whether the last full stability window stayed within its declared bounds.

    The verdict consults action churn, claim churn and stale retries. It consults no
    service outcome, by design: stability and service satisfaction are reported beside
    each other and never folded together.
    """
    window_epochs = max(1, int(limits["stability_window_s"] / period_s))
    recent = epochs[-window_epochs:]
    if len(recent) < window_epochs:
        return None, {"reason": "no full stability window was observed",
                      "epochs_seen": len(epochs), "epochs_needed": window_epochs}
    changes = len(_settings(recent)) - repeated_actions(recent)
    claims = claim_churn(recent)
    stale = sum(epoch["traces"].get("resolution", {}).get("stale_retries", 0) for epoch in recent)
    within = (changes <= limits["action_churn_limit"] and claims <= limits["claim_churn_limit"]
              and stale <= limits["stale_retry_limit"])
    return within, {"action_changes": changes, "claim_churn": claims, "stale_retries": stale,
                    "window_epochs": window_epochs}


def measurements(epochs, limits, period_s):
    """The coordination and reasoning measurements, shaped for a ResultRecord."""
    require(limits.get("stability_window_s"), "stability needs a declared window")
    effort = reasoning_effort(epochs)
    overhead = coordination_overhead(epochs)
    worst, _ = coordination_starvation(epochs)
    settled, detail = stability(epochs, limits, period_s)
    stalled = deadlock_epochs(epochs)
    return [
        _measure("action_reversals", "count", oscillation(epochs)),
        _measure("repeated_applications", "count", repeated_actions(epochs)),
        _measure("deadlocked_epochs", "count", len(stalled)),
        _measure("coordination_starvation_epochs", "count", worst),
        # Service starvation needs per-reading delivery evidence the contract lacks.
        _measure("service_starvation_s", "s", None),
        _measure("expert_activations", "count", effort["activations"]),
        _measure("search_expansions", "count", effort["expansions"]),
        _measure("plan_steps", "count", effort["plan_steps"]),
        _measure("coordination_conflicts", "count", overhead["conflicts"]),
        _measure("coordination_concessions", "count", overhead["concessions"]),
        _measure("mark_writes", "count", overhead["mark_writes"]),
        _measure("mark_bytes", "byte", overhead["mark_bytes"]),
        _measure("claim_churn", "count", claim_churn(epochs)),
        _measure("coordination_stable", "count",
                 None if settled is None else int(settled)),
    ], {"stability": detail, "deadlocked_epochs": stalled, "overhead": overhead,
        "effort": effort,
        "note": "behavioural measurement only; no service outcome is consulted here"}
