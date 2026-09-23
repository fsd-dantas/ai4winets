"""Eco-problem solving: local satisfaction, differentiated interpretation, marks.

docs/ECoRA/decision-methods.md places the agent boundary at one service-class queue on one
site. An agent owns its own state, the signals it can see, how it reads them, what
satisfies it, and the actions it may take. It cannot read global queue state, another
site, future disturbances or the evaluator's labels, and nothing here is permitted to hand
it any of those.

Two services facing the same signal want different things, and that difference is the
point rather than an inconvenience. Occupied capacity reads as immediate contention to a
SCADA agent and as a reason to defer a reading to an AMI agent. The interpretation is
declared per service, so the asymmetry is visible in configuration instead of buried in a
branch.

Satisfaction is a vector of predicates before it is any kind of score. Collapsing it into
one number needs declared weights and a sensitivity analysis, so nothing here collapses it.

The substrate stores and exposes marks. It does not choose an allocation. A central
process hosts it for convenience, and the read API enforces local scope anyway, because a
coordination mechanism that can secretly see everything is not the mechanism being
studied. Marks here are ideal local shared memory: reads, writes and serialised bytes are
counted, and none of those counts is network overhead.
"""

from dataclasses import dataclass, field
from functools import partial

from .contracts import observed_version, Record, canonical, digest, require
from .registry import ProviderResult
from .schema import INPUT_TYPES, OUTPUT_TYPES

VERSION = "eco-v1"

MECHANISMS = ("expiring_marks", "backoff", "reservation", "yield_aging")

_TESTS = {"ge": lambda a, b: a >= b, "le": lambda a, b: a <= b,
          "gt": lambda a, b: a > b, "lt": lambda a, b: a < b,
          "eq": lambda a, b: a == b, "ne": lambda a, b: a != b}


@dataclass(frozen=True)
class Mark:
    """An advisory local intention. It reserves nothing and compels no one."""

    issuer: str
    resource: str
    intent: str
    neighbourhood: str
    created_s: float
    expires_s: float
    version: int

    def live(self, at):
        return self.created_s <= at < self.expires_s

    def serialised(self):
        return len(canonical({"issuer": self.issuer, "resource": self.resource,
                              "intent": self.intent, "neighbourhood": self.neighbourhood,
                              "created_s": self.created_s, "expires_s": self.expires_s,
                              "version": self.version}))


@dataclass
class MarkSubstrate:
    """Stores marks and exposes them within a neighbourhood. It decides nothing."""

    transport: str = "ideal_local"
    marks: list = field(default_factory=list)
    writes: int = 0
    reads: int = 0
    bytes_written: int = 0

    def publish(self, mark):
        self.writes += 1
        self.bytes_written += mark.serialised()
        self.marks.append(mark)
        return mark

    def visible(self, neighbourhood, at):
        """Only this neighbourhood's unexpired marks. Expiry is applied on read."""
        self.reads += 1
        return [mark for mark in self.marks
                if mark.neighbourhood == neighbourhood and mark.live(at)]

    def release(self, issuer, resource):
        self.marks = [mark for mark in self.marks
                      if not (mark.issuer == issuer and mark.resource == resource)]

    def accounting(self):
        return {"transport": self.transport, "writes": self.writes, "reads": self.reads,
                "bytes": self.bytes_written, "live": len(self.marks),
                "note": "ideal local shared memory; not network overhead"}


def agent_draw(agent_id, resolution_id, attempt):
    """An agent-specific draw in [0, 1), reproducible from its own identity.

    Each agent's backoff must be its own, and a run must reproduce. Deriving the draw from
    the agent's identity and the contention it is in gives both without a shared generator
    whose position would depend on how often other agents happened to consult it.
    """
    value = digest({"agent": agent_id, "resolution": resolution_id, "attempt": attempt})
    return int(value[:8], 16) / 0x100000000


def _resources(proposal):
    """What a proposal would write. Two proposals conflict when these intersect."""
    fluent = {"select_path": "selected_path", "set_ami_pacing": "pacing_profile",
              "defer_eligible_message": "release_at_s"}
    touched = set()
    for step in proposal["steps"]:
        name = fluent.get(step["operator"])
        if name:
            touched.add(f"{step['target']}/{name}")
    return touched


class EcoAssessmentProvider:
    """Per-agent local satisfaction and differentiated interpretation of the same signals."""

    def invoke(self, inputs, prior_state, context):
        config = context.data["configuration"]
        watermark = context.data["decision_watermark_s"]
        observed, unknown = {}, set()
        for message in inputs:
            payload = Record.from_dict(message.data["payload"])
            if payload.kind != "TelemetryBatch":
                continue
            for observation in payload.data["observations"]:
                if observation["quality"] == "missing":
                    unknown.add(observation["metric"])
                else:
                    observed[observation["metric"]] = (observation["value"],
                                                       observation["observation_id"])
        hypotheses, trace = [], []
        for agent in config["agents"]:
            satisfied, support, blocked = True, [], []
            for predicate in agent["satisfaction"]:
                metric = predicate["metric"]
                if metric in unknown or metric not in observed:
                    satisfied = None
                    blocked.append(metric)
                    continue
                value, identity = observed[metric]
                support.append(identity)
                if not _TESTS[predicate["op"]](value, predicate["value"]):
                    satisfied = False
            status = {True: "supported", False: "contradicted", None: "unknown"}[satisfied]
            hypotheses.append({"label": f"{agent['agent_id']}/satisfied",
                               "support_ids": sorted(set(support)),
                               "counterevidence_ids": [], "status": status})
            # The same signal, read through each service's own concerns.
            for reading in config["interpretation"].get(agent["service"], []):
                metric = reading["metric"]
                if metric not in observed:
                    continue
                value, identity = observed[metric]
                if _TESTS[reading["op"]](value, reading["value"]):
                    hypotheses.append({"label": f"{agent['agent_id']}/{reading['concludes']}",
                                       "support_ids": [identity], "counterevidence_ids": [],
                                       "status": "supported"})
            trace.append({"agent_id": agent["agent_id"], "service": agent["service"],
                          "satisfied": status, "unobservable": sorted(blocked)})
        record = Record("DiagnosisRecord", {
            "hypotheses": hypotheses,
            "rule_trace": [{"organisation": "eco_local", "agents": trace,
                            "watermark_s": watermark}],
            "unresolved_conflicts": [], "confidence_semantics": "categorical"})
        state = {"assessments": prior_state.data["state"].get("assessments", 0) + 1}
        return ProviderResult((record,), state,
                              {"organisation": "eco_local", "agents": len(config["agents"]),
                               "unobservable": sorted(unknown)})


class EcoResolutionProvider:
    """Local coordination over competing proposals, by one declared mechanism.

    No global arbiter decides. Each agent publishes an intent, reads only its own
    neighbourhood, and yields when an earlier visible claim wins. The tie-break is
    deterministic on waiting time and then agent identity, so a run reproduces without
    that determinism becoming a hidden central utility.
    """

    def __init__(self, mechanism):
        self.mechanism = mechanism

    def invoke(self, inputs, prior_state, context):
        config = context.data["configuration"]
        watermark = context.data["decision_watermark_s"]
        ttl = config.get("mark_ttl_s", 0.3)
        substrate = MarkSubstrate(transport=config.get("mark_transport_model", "ideal_local"))
        proposals = sorted((Record.from_dict(m.data["payload"]).data for m in inputs
                            if Record.from_dict(m.data["payload"]).kind == "PlanProposal"),
                           key=lambda p: p["proposal_id"])
        waiting = prior_state.data["state"].get("waiting_since", {})
        resolution_id = f"resolution:{VERSION}:{watermark}"

        claims = {}
        for proposal in proposals:
            neighbourhood = proposal["site_id"]
            since = waiting.get(proposal["agent_id"], watermark)
            for resource in _resources(proposal):
                substrate.publish(Mark(issuer=proposal["agent_id"], resource=resource,
                                       intent="transmit", neighbourhood=neighbourhood,
                                       created_s=watermark, expires_s=watermark + ttl,
                                       version=len(substrate.marks)))
                claims.setdefault(resource, []).append((since, proposal["agent_id"], proposal))

        decisions, commands, events = [], [], []
        admitted = set()
        for resource, contenders in sorted(claims.items()):
            neighbourhood = contenders[0][2]["site_id"]
            visible = substrate.visible(neighbourhood, watermark)
            winner = self._settle(resource, contenders, visible, resolution_id, watermark,
                                  config, events)
            if winner is not None:
                admitted.add(winner["proposal_id"])
        for proposal in proposals:
            won = proposal["proposal_id"] in admitted
            decisions.append({
                "proposal_id": proposal["proposal_id"],
                "disposition": "admit" if won else "defer",
                "reason": {"code": self.mechanism,
                           "detail": "Won its contention under the declared mechanism." if won
                           else "Conceded to an earlier visible claim."},
                "conflicting_proposal_ids": sorted(
                    other["proposal_id"] for other in proposals
                    if other["proposal_id"] != proposal["proposal_id"]
                    and _resources(other) & _resources(proposal))})
            if won:
                command = self._command(proposal, config, watermark, resolution_id)
                if command is not None:
                    commands.append(command)
                else:
                    decisions[-1]["disposition"] = "defer"
                    decisions[-1]["reason"] = {"code": "no_authority_or_evidence",
                                               "detail": "The agent may not issue this mutation."}
        record = Record("ResolutionRecord", {
            "resolution_id": resolution_id,
            "proposal_ids": [p["proposal_id"] for p in proposals],
            "decisions": decisions, "claim_versions": {},
            "command_ids": [c.data["command_id"] for c in commands]})
        # An agent that conceded keeps waiting; a winner's clock restarts.
        following = {p["agent_id"]: (watermark if p["proposal_id"] in admitted
                                     else waiting.get(p["agent_id"], watermark))
                     for p in proposals}
        state = {"waiting_since": following,
                 "rounds": prior_state.data["state"].get("rounds", 0) + 1}
        trace = {"mechanism": self.mechanism, "contended_resources": len(claims),
                 "admitted": len(admitted), "conceded": len(proposals) - len(admitted),
                 "events": events, "marks": substrate.accounting()}
        return ProviderResult((record, *commands), state, trace)

    def _settle(self, resource, contenders, visible, resolution_id, watermark, config, events):
        """One resource, one mechanism, one winner or none."""
        ordered = sorted(contenders, key=lambda item: (item[0], item[1]))
        if len(ordered) == 1:
            return ordered[0][2]
        if self.mechanism == "expiring_marks":
            live = {mark.issuer for mark in visible if mark.resource == resource}
            eligible = [item for item in ordered if item[1] in live] or ordered
            events.append({"resource": resource, "mechanism": "expiring_marks",
                           "live_claims": sorted(live)})
            return eligible[0][2]
        if self.mechanism == "backoff":
            delays = {item[1]: config.get("backoff_min_s", 0.1)
                      + agent_draw(item[1], resolution_id, 0)
                      * (config.get("backoff_max_s", 0.3) - config.get("backoff_min_s", 0.1))
                      for item in ordered}
            first = min(ordered, key=lambda item: (delays[item[1]], item[1]))
            events.append({"resource": resource, "mechanism": "backoff",
                           "delays": {agent: round(delay, 6) for agent, delay in delays.items()}})
            return first[2]
        if self.mechanism == "reservation":
            granted = set(config.get("grants", {}).get(resource, [item[1] for item in ordered]))
            holders = [item for item in ordered if item[1] in granted]
            events.append({"resource": resource, "mechanism": "reservation",
                           "granted": sorted(granted)})
            if not holders:
                # Every grant was lost. Nobody proceeds, and nobody pretends otherwise.
                events.append({"resource": resource, "event": "no_grant_deadlock"})
                return None
            return holders[0][2]
        if self.mechanism == "yield_aging":
            aged = sorted(ordered, key=lambda item: (-(watermark - item[0]), item[1]))
            events.append({"resource": resource, "mechanism": "yield_aging",
                           "waiting": {item[1]: round(watermark - item[0], 6) for item in ordered}})
            return aged[0][2]
        return None

    @staticmethod
    def _command(proposal, config, watermark, resolution_id):
        scopes = {"select_path": ("site", "shared", "selected_path"),
                  "set_ami_pacing": ("ami_queue", "ami", "pacing_profile")}
        steps = proposal["steps"]
        step = steps[0] if steps else None
        if step is None or step["operator"] not in scopes:
            return None
        capability = config.get("authority", {}).get(step["operator"])
        if not capability or not step["preconditions"]:
            return None
        scope, service, fluent = scopes[step["operator"]]
        # The version the controller observed; without one there is nothing to check a
        # stale write against, so no command is written.
        version = observed_version(proposal, step["target"], step["operator"])
        if version is None:
            return None
        return Record("ActionCommand", {
            "command_id": f"command:{proposal['proposal_id']}", "operator": step["operator"],
            "catalog_version": "v1", "target": step["target"], "scope": scope, "service": service,
            "issuer": proposal["agent_id"], "arguments": step["arguments"], "argument_units": {},
            "read_set": [f"{step['target']}/{fluent}"], "write_set": [f"{step['target']}/{fluent}"],
            "resource_footprint": [f"{step['target']}/{service}"], "expected_state_version": version,
            "precondition_evidence_ids": step["preconditions"], "resolution_id": resolution_id,
            "authority_capability_id": capability, "not_before_s": watermark,
            "expires_at_s": watermark + config.get("validity_s", 1),
            "idempotency_key": f"idempotency:{proposal['proposal_id']}"})


def eco_binding(registry, capability_ids, configuration, stage="resolution",
                mechanism="expiring_marks"):
    """Register an eco provider for one stage and return its frozen binding."""
    if stage == "resolution":
        require(mechanism in MECHANISMS, f"unknown anti-collision mechanism: {mechanism}")
        provider_id, factory = f"eco.{mechanism}", partial(EcoResolutionProvider, mechanism)
    else:
        require(stage == "diagnosis", f"eco has no provider for stage {stage}")
        require(configuration.get("agents"), "an eco assessment must declare its agents")
        for agent in configuration["agents"]:
            require(agent["satisfaction"], f"{agent['agent_id']} declares no satisfaction predicate")
        provider_id, factory = "eco.local_assessment", EcoAssessmentProvider
    spec = Record("ProviderSpec", {
        "stage_id": stage, "provider_id": provider_id, "provider_version": VERSION,
        "arm": "proposed", "input_types": list(INPUT_TYPES[stage]),
        "output_types": list(OUTPUT_TYPES[stage]), "state_schema_version": "1",
        "capability_ids": list(capability_ids), "direct_truth_access": False})
    if not registry.registered(stage, provider_id, VERSION):
        registry.register(spec, factory)
    return {k: v for k, v in spec.data.items() if k != "direct_truth_access"} | {
        "information_regime": "contract_only", "allow_privileged_inputs": False,
        "configuration": configuration, "configuration_hash": digest(configuration)}
