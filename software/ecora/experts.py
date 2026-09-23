"""Rule-based diagnosis in two organisations over one shared rule inventory.

docs/ECoRA/decision-methods.md specifies both: a single engine evaluating a versioned
collection of production rules over an admissible evidence snapshot, and one expert per
rule scheduled by a blackboard controller that manages revisions, dependencies and
termination. They exist to be compared, so they share the rule inventory, the conflict
policy and the evidence snapshot, and differ only in how the work is organised.

The hypothesis under test (RQ-E) is that the two agree and that their orchestration cost
does not. Nothing here presumes that: agreement is asserted by a test that can fail, and
both providers record what they did so the cost can be read rather than assumed.

Support is categorical. A rule either has its inputs or does not, and a conclusion is
either supported, contradicted or unknown. No numeric confidence is attached, because a
score without a calibration procedure would be a probability in costume.
"""

from functools import partial

from .contracts import Record, digest, require
from .registry import ProviderResult
from .schema import INPUT_TYPES, OUTPUT_TYPES

VERSION = "expert-v1"

_TESTS = {"ge": lambda a, b: a >= b, "le": lambda a, b: a <= b,
          "gt": lambda a, b: a > b, "lt": lambda a, b: a < b,
          "eq": lambda a, b: a == b, "ne": lambda a, b: a != b}

UNKNOWN = object()


def signal(observation):
    """The name a rule refers to a signal by.

    A site-level signal is named by its metric. One belonging to something under the site,
    such as a per-leg probe, is qualified by its subject, because two legs reporting the
    same metric would otherwise collide and a rule could not say which leg it meant.
    """
    subject, metric = observation["subject"], observation["metric"]
    return metric if "/" not in subject else f"{subject}/{metric}"


def snapshot_from(observations):
    """The admissible evidence: a signal is present only if it was actually observed.

    An observation marked missing is not evidence of anything, so it is absent here rather
    than carrying a null that a comparison might silently accept. Privileged and ordinary
    evidence are read the same way, so an Oracle and a contract-limited arm differ in what
    they were given and not in how it was interpreted.
    """
    observed, unknown = {}, set()
    for observation in observations:
        name = signal(observation)
        if observation["quality"] == "missing":
            unknown.add(name)
        else:
            observed[name] = (observation["value"], observation["observation_id"])
    return observed, unknown


def _snapshot(inputs):
    relayed = []
    for message in inputs:
        payload = Record.from_dict(message.data["payload"])
        if payload.kind == "TelemetryBatch":
            relayed.extend(payload.data["observations"])
    return snapshot_from(relayed)


def evaluate(rule, observed, unknown, concluded):
    """Return (True, support) if the rule fires, (False, support), or (UNKNOWN, reason).

    A rule whose inputs are not all present is unknown, never false. Treating absent
    evidence as a negative is how a diagnosis comes to assert something it never saw.
    """
    support = []
    for metric in rule["requires"]:
        if metric in unknown:
            return UNKNOWN, f"{metric} is unknown"
        if metric not in observed:
            return UNKNOWN, f"{metric} was not supplied"
        support.append(observed[metric][1])
    for predicate in rule.get("requires_predicates", []):
        if predicate not in concluded:
            return UNKNOWN, f"{predicate} is not concluded"
        support.extend(concluded[predicate])
    condition = rule["condition"]
    if condition is None:
        return True, support
    value = observed[condition["metric"]][0]
    return _TESTS[condition["op"]](value, condition["value"]), support


class _Inference:
    """The shared inference: accumulate conclusions to a fixed point, resolve conflicts.

    Both organisations use this, so a difference between them is organisation and not a
    second implementation of the same logic drifting from the first.
    """

    def __init__(self, rules, budget):
        self.rules = rules
        self.budget = budget
        self.concluded = {}
        self.fired = {}
        self.inhibited = []
        self.unresolved = []
        self.activations = 0

    def consider(self, rule, observed, unknown):
        """One activation. Returns True when it changed the blackboard."""
        self.activations += 1
        label = rule["concludes"]
        if label in self.concluded or rule["rule_id"] in self.fired:
            return False
        outcome, detail = evaluate(rule, observed, unknown, self.concluded)
        if outcome is UNKNOWN or outcome is False:
            return False
        losing = [other for other in rule.get("contradicts", []) if other in self.concluded]
        for other in losing:
            winner = self.fired.get(self._author(other))
            if winner is None:
                continue
            if winner["priority"] > rule["priority"]:
                self._inhibit(rule["rule_id"], "lower_priority", other)
                return False
            if winner["priority"] == rule["priority"]:
                # Equal authority on contradictory conclusions is not resolvable by policy.
                # Deduped where it is recorded, not only where it is read. The same
                # conflict is reconsidered on every later pass, and a list that grows per
                # pass is one output change away from reporting passes as conflicts.
                for identifier in (rule["rule_id"], winner["rule_id"]):
                    if identifier not in self.unresolved:
                        self.unresolved.append(identifier)
                self.concluded.pop(other, None)
                self._inhibit(rule["rule_id"], "unresolved_conflict", other)
                return True
            self.concluded.pop(other, None)
            self._inhibit(winner["rule_id"], "lower_priority", label)
        self.concluded[label] = detail
        self.fired[rule["rule_id"]] = rule
        return True

    def _inhibit(self, rule_id, reason, against):
        """Record an inhibition once.

        A rule inhibited by a stronger conclusion is reconsidered on every later pass and
        inhibited again each time, so appending unconditionally reported one inhibition as
        many. The trace is evidence: a reader counting entries would have been counting
        passes. The baseline rule inventory never reached this code, because no two of its
        contradicting rules can both hold.
        """
        entry = {"rule_id": rule_id, "reason": reason, "against": against}
        if entry not in self.inhibited:
            self.inhibited.append(entry)

    def _author(self, label):
        return next((r["rule_id"] for r in self.rules if r["concludes"] == label), None)

    def record(self, organisation, passes):
        hypotheses = [{"label": label, "support_ids": sorted(set(support)),
                       "counterevidence_ids": [], "status": "supported"}
                      for label, support in sorted(self.concluded.items())]
        if not hypotheses:
            hypotheses = [{"label": "insufficient_evidence", "support_ids": [],
                           "counterevidence_ids": [], "status": "unknown"}]
        trace = [{"organisation": organisation, "activations": self.activations,
                  "passes": passes, "fired": sorted(self.fired),
                  "inhibited": self.inhibited, "rule_set_version": VERSION}]
        return Record("DiagnosisRecord", {
            "hypotheses": hypotheses, "rule_trace": trace,
            "unresolved_conflicts": sorted(set(self.unresolved)),
            "confidence_semantics": "categorical"})


def infer(rules, observations, budget):
    """The whole rule inventory over one set of observations, to a fixed point.

    The diagnosis Oracle and the ground-truth scorer both reason this way over truth, so
    they share it: a scorer that inferred differently from the Oracle it scores beside
    would report a disagreement between two implementations as a diagnostic error.
    """
    observed, unknown = snapshot_from(observations)
    inference = _Inference(rules, budget)
    passes, changed = 0, True
    while changed:
        changed = False
        passes += 1
        for rule in rules:
            changed |= inference.consider(rule, observed, unknown)
    return inference, passes, unknown


class SingleExpertProvider:
    """One engine evaluating the whole rule collection to a fixed point."""

    organisation = "single_engine"

    def invoke(self, inputs, prior_state, context):
        config = context.data["configuration"]
        rules = config["rules"]
        budget = config.get("activation_budget", 1000)
        observed, unknown = _snapshot(inputs)
        inference = _Inference(rules, budget)
        passes = 0
        changed = True
        while changed:
            changed = False
            passes += 1
            for rule in rules:
                if inference.activations >= budget:
                    return self._exhausted(inference, passes)
                changed |= inference.consider(rule, observed, unknown)
        state = {"evaluations": prior_state.data["state"].get("evaluations", 0) + 1}
        return ProviderResult((inference.record(self.organisation, passes),), state,
                              {"organisation": self.organisation,
                               "activations": inference.activations, "passes": passes})

    def _exhausted(self, inference, passes):
        return ProviderResult((), {}, {"organisation": self.organisation,
                                       "activations": inference.activations}, "rejected",
                              {"code": "activation_budget",
                               "detail": "The declared activation budget was exhausted."})


class BlackboardProvider(SingleExpertProvider):
    """One expert per rule, scheduled by a controller over a revisioned blackboard.

    Each expert owns exactly one rule and reads the revision current when it is scheduled.
    An expert that could not fire is rescheduled once the revision advances, which is how
    a conclusion reached late becomes available as another expert's premise. Termination
    is a fixed point or the declared activation budget, never an implicit loop bound.

    The controller is a central coordination mechanism for experts. It is not the
    eco-agents' environment, and running rules in separate experts is not by itself
    evidence of distributed problem solving.
    """

    organisation = "blackboard"

    def invoke(self, inputs, prior_state, context):
        config = context.data["configuration"]
        rules = config["rules"]
        budget = config.get("activation_budget", 1000)
        observed, unknown = _snapshot(inputs)
        inference = _Inference(rules, budget)
        experts = {rule["rule_id"]: rule for rule in rules}
        pending = [rule["rule_id"] for rule in rules]
        revision, passes = 0, 0
        while pending:
            passes += 1
            scheduled, pending = pending, []
            for rule_id in scheduled:
                if inference.activations >= budget:
                    return self._exhausted(inference, passes)
                if inference.consider(experts[rule_id], observed, unknown):
                    revision += 1
                elif experts[rule_id]["rule_id"] not in inference.fired:
                    pending.append(rule_id)
            # Stale contributions are re-evaluated only while the revision still moves.
            if not any(rule_id for rule_id in pending) or revision == 0:
                break
            if passes > 1 and revision == passes - 1:
                break
        state = {"evaluations": prior_state.data["state"].get("evaluations", 0) + 1,
                 "revision": revision}
        return ProviderResult((inference.record(self.organisation, passes),), state,
                              {"organisation": self.organisation,
                               "activations": inference.activations, "passes": passes,
                               "revisions": revision})


def expert_binding(registry, capability_ids, configuration, organisation="single_engine"):
    """Register one organisation of the shared rule inventory and return its binding."""
    rules = configuration.get("rules")
    require(rules, "an expert binding must declare its rule inventory")
    seen = set()
    for rule in rules:
        require(rule["rule_id"] not in seen, f"duplicate rule: {rule['rule_id']}")
        seen.add(rule["rule_id"])
        require(rule["condition"] is None or rule["condition"]["op"] in _TESTS,
                f"unknown condition operator in {rule['rule_id']}")
        require(rule["condition"] is None
                or rule["condition"]["metric"] in rule["requires"],
                f"{rule['rule_id']} tests a metric it does not require")
    providers = {"single_engine": SingleExpertProvider, "blackboard": BlackboardProvider}
    require(organisation in providers, f"unknown expert organisation: {organisation}")
    spec = Record("ProviderSpec", {
        "stage_id": "diagnosis", "provider_id": f"experts.{organisation}",
        "provider_version": VERSION, "arm": "proposed",
        "input_types": list(INPUT_TYPES["diagnosis"]), "output_types": list(OUTPUT_TYPES["diagnosis"]),
        "state_schema_version": "1", "capability_ids": list(capability_ids),
        "direct_truth_access": False})
    if not registry.registered("diagnosis", spec.data["provider_id"], VERSION):
        registry.register(spec, providers[organisation])
    return {k: v for k, v in spec.data.items() if k != "direct_truth_access"} | {
        "information_regime": "contract_only", "allow_privileged_inputs": False,
        "configuration": configuration, "configuration_hash": digest(configuration)}
