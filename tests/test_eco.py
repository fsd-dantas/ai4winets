import unittest

from ecora.contracts import ContractError, Record
from ecora.eco import (EcoResolutionProvider, Mark, MarkSubstrate, agent_draw, eco_binding)
from ecora.registry import Registry

SCADA = "agent:site-1:scada"
AMI = "agent:site-1:ami"

CONFIG = {"mark_ttl_s": 0.3, "backoff_min_s": 0.1, "backoff_max_s": 0.3, "validity_s": 1,
          "authority": {"select_path": "actuate.shared.path",
                        "set_ami_pacing": "actuate.ami.pacing"}}


def proposal(agent_id, proposal_id, operator="select_path", target="site-1",
             arguments=None, preconditions=("observation:ami:0",)):
    step = {"operator": operator, "target": target,
            "arguments": arguments or {"path": "alternative"},
            "preconditions": list(preconditions), "add_effects": [], "delete_effects": [],
            "cost": 2}
    return {"proposal_id": proposal_id, "agent_id": agent_id, "site_id": "site-1",
            "service": "ami", "steps": [step], "assumptions": [], "estimated_cost": 2,
            "valid_until_s": 1, "goal_status": "unmet", "certificate_ref": None,
            "state_versions": {"site-1/selected_path": 0, "site-1/pacing_profile": 0}}


class Message:
    """A minimal stand-in for the boundary's Message wrapper around a payload."""

    def __init__(self, payload):
        self.data = {"payload": Record("PlanProposal", payload).to_dict()}


class Snapshot:
    def __init__(self, state=None):
        self.data = {"state": state or {}}


class Context:
    def __init__(self, configuration, watermark=0.0):
        self.data = {"configuration": configuration, "decision_watermark_s": watermark}


def resolve(mechanism, proposals, *, config=None, state=None, watermark=0.0):
    provider = EcoResolutionProvider(mechanism)
    result = provider.invoke([Message(p) for p in proposals], Snapshot(state),
                             Context({**CONFIG, **(config or {})}, watermark))
    record = next(r for r in result.outputs if r.kind == "ResolutionRecord")
    commands = [r for r in result.outputs if r.kind == "ActionCommand"]
    return record.data, commands, result.trace, result.next_state


class SubstrateTests(unittest.TestCase):
    def test_a_mark_is_visible_only_in_its_own_neighbourhood(self):
        substrate = MarkSubstrate()
        here = Mark(SCADA, "site-1/selected_path", "transmit", "site-1", 0.0, 1.0, 1)
        elsewhere = Mark("agent:site-2:ami", "site-2/selected_path", "transmit", "site-2", 0.0, 1.0, 1)
        substrate.publish(here)
        substrate.publish(elsewhere)
        self.assertEqual(substrate.visible("site-1", 0.0), [here])
        self.assertEqual(substrate.visible("site-2", 0.0), [elsewhere])

    def test_expiry_is_applied_on_read(self):
        substrate = MarkSubstrate()
        substrate.publish(Mark(SCADA, "site-1/selected_path", "transmit", "site-1", 0.0, 0.3, 1))
        self.assertEqual(len(substrate.visible("site-1", 0.2)), 1)
        self.assertEqual(substrate.visible("site-1", 0.3), [], "a mark expires at its expiry")

    def test_the_substrate_reports_its_cost_without_calling_it_network_overhead(self):
        substrate = MarkSubstrate()
        substrate.publish(Mark(SCADA, "site-1/selected_path", "transmit", "site-1", 0.0, 1.0, 1))
        substrate.visible("site-1", 0.0)
        accounting = substrate.accounting()
        self.assertEqual((accounting["writes"], accounting["reads"]), (1, 1))
        self.assertGreater(accounting["bytes"], 0)
        self.assertEqual(accounting["transport"], "ideal_local")
        self.assertIn("not network overhead", accounting["note"])

    def test_an_agent_draw_is_its_own_and_reproducible(self):
        self.assertEqual(agent_draw(SCADA, "r", 0), agent_draw(SCADA, "r", 0))
        self.assertNotEqual(agent_draw(SCADA, "r", 0), agent_draw(AMI, "r", 0))
        self.assertNotEqual(agent_draw(SCADA, "r", 0), agent_draw(SCADA, "r", 1))
        for agent in (SCADA, AMI):
            self.assertTrue(0.0 <= agent_draw(agent, "r", 0) < 1.0)


AGENTS = {
    "agents": [
        {"agent_id": SCADA, "service": "scada", "site": "site-1",
         "satisfaction": [{"metric": "queue_occupancy", "op": "lt", "value": 4096}]},
        {"agent_id": AMI, "service": "ami", "site": "site-1",
         "satisfaction": [{"metric": "queue_occupancy", "op": "lt", "value": 49152}]},
    ],
    # The same occupied resource, read through each service's own concerns.
    "interpretation": {
        "scada": [{"metric": "queue_occupancy", "op": "ge", "value": 4096,
                   "concludes": "immediate_contention"}],
        "ami": [{"metric": "queue_occupancy", "op": "ge", "value": 4096,
                 "concludes": "defer_eligible"}],
    },
}


class TelemetryMessage:
    def __init__(self, observations):
        payload = Record("TelemetryBatch", {
            "observations": observations, "watermark_s": 0,
            "window": {"start_s": 0, "end_s": 0}, "sequence": 0,
            "completeness": 1 if all(o["quality"] != "missing" for o in observations) else 0,
            "omitted_metrics": sorted({o["metric"] for o in observations
                                       if o["quality"] == "missing"})})
        self.data = {"payload": payload.to_dict()}


def assess(observations, config=None):
    from ecora.eco import EcoAssessmentProvider
    result = EcoAssessmentProvider().invoke([TelemetryMessage(observations)], Snapshot(),
                                            Context(config or AGENTS))
    return result.outputs[0].data, result.trace


def queue(value, **changes):
    from ecora.fixtures import observation
    return observation(observation_id="observation:queue", metric="queue_occupancy",
                       unit="byte", value=value, capability_id="observe.ami.queue", **changes)


class AssessmentTests(unittest.TestCase):
    def test_two_services_read_the_same_signal_differently(self):
        """The asymmetry is the point: one sees contention, the other sees room to defer."""
        record, _ = assess([queue(8192)])
        labels = {h["label"] for h in record["hypotheses"]}
        self.assertIn(f"{SCADA}/immediate_contention", labels)
        self.assertIn(f"{AMI}/defer_eligible", labels)
        # And the same occupancy satisfies one agent while dissatisfying the other.
        status = {h["label"]: h["status"] for h in record["hypotheses"]}
        self.assertEqual(status[f"{SCADA}/satisfied"], "contradicted")
        self.assertEqual(status[f"{AMI}/satisfied"], "supported")

    def test_satisfaction_is_a_vector_of_predicates_with_its_evidence(self):
        record, _ = assess([queue(1024)])
        satisfied = next(h for h in record["hypotheses"] if h["label"] == f"{AMI}/satisfied")
        self.assertEqual(satisfied["status"], "supported")
        self.assertEqual(satisfied["support_ids"], ["observation:queue"])

    def test_an_unobservable_signal_leaves_satisfaction_unknown_not_false(self):
        record, trace = assess([queue(None, quality="missing", valid_min=None, valid_max=None,
                                      missing_reason={"code": "absent", "detail": "None."})])
        for hypothesis in record["hypotheses"]:
            if hypothesis["label"].endswith("/satisfied"):
                self.assertEqual(hypothesis["status"], "unknown")
        self.assertEqual(trace["unobservable"], ["queue_occupancy"])
        agents = record["rule_trace"][0]["agents"]
        self.assertTrue(all(entry["unobservable"] == ["queue_occupancy"] for entry in agents))

    def test_it_reports_only_the_agents_it_declares(self):
        record, _ = assess([queue(1024)])
        owners = {h["label"].split("/")[0] for h in record["hypotheses"]}
        self.assertEqual(owners, {SCADA, AMI})


class MechanismTests(unittest.TestCase):
    def contended(self):
        return [proposal(SCADA, "proposal:a"), proposal(AMI, "proposal:b")]

    def test_every_mechanism_admits_one_contender_and_defers_the_rest(self):
        for mechanism in ("expiring_marks", "backoff", "reservation", "yield_aging"):
            with self.subTest(mechanism=mechanism):
                record, commands, trace, _ = resolve(mechanism, self.contended())
                dispositions = sorted(d["disposition"] for d in record["decisions"])
                self.assertEqual(dispositions, ["admit", "defer"])
                self.assertEqual(len(commands), 1)
                self.assertEqual(trace["mechanism"], mechanism)
                # Each decision names what it was contending with.
                for decision in record["decisions"]:
                    self.assertEqual(decision["conflicting_proposal_ids"],
                                     [p for p in record["proposal_ids"]
                                      if p != decision["proposal_id"]])

    def test_uncontended_proposals_on_separate_resources_both_proceed(self):
        proposals = [proposal(SCADA, "proposal:a"),
                     proposal(AMI, "proposal:b", operator="set_ami_pacing",
                              arguments={"profile": "restricted"})]
        record, commands, _, _ = resolve("expiring_marks", proposals)
        self.assertEqual([d["disposition"] for d in record["decisions"]], ["admit", "admit"])
        self.assertEqual(len(commands), 2)

    def test_yield_with_aging_gives_way_to_the_longer_waiting_agent(self):
        waiting = {SCADA: 0.0, AMI: 9.0}
        record, _, trace, _ = resolve("yield_aging", self.contended(),
                                      state={"waiting_since": waiting}, watermark=10.0)
        admitted = [d["proposal_id"] for d in record["decisions"] if d["disposition"] == "admit"]
        self.assertEqual(admitted, ["proposal:a"], "the agent waiting since 0.0 should win")
        # Reverse the wait and the winner reverses with it, so it is aging and not identity.
        record, _, _, _ = resolve("yield_aging", self.contended(),
                                  state={"waiting_since": {SCADA: 9.0, AMI: 0.0}}, watermark=10.0)
        admitted = [d["proposal_id"] for d in record["decisions"] if d["disposition"] == "admit"]
        self.assertEqual(admitted, ["proposal:b"])

    def test_a_conceding_agent_keeps_its_place_in_the_queue(self):
        """Its wait is not reset by losing, or it could be starved indefinitely."""
        _, _, _, state = resolve("yield_aging", self.contended(),
                                 state={"waiting_since": {SCADA: 0.0, AMI: 5.0}}, watermark=10.0)
        self.assertEqual(state["waiting_since"][AMI], 5.0, "the loser keeps waiting from before")
        self.assertEqual(state["waiting_since"][SCADA], 10.0, "the winner's clock restarts")

    def test_a_lost_grant_deadlocks_rather_than_proceeding_anyway(self):
        record, commands, trace, _ = resolve("reservation", self.contended(),
                                             config={"grants": {"site-1/selected_path": []}})
        self.assertEqual([d["disposition"] for d in record["decisions"]], ["defer", "defer"])
        self.assertEqual(commands, [])
        self.assertTrue(any(event.get("event") == "no_grant_deadlock"
                            for event in trace["events"]))

    def test_backoff_draws_are_per_agent_and_reproducible(self):
        first, _, trace_one, _ = resolve("backoff", self.contended())
        second, _, trace_two, _ = resolve("backoff", self.contended())
        self.assertEqual(first["decisions"], second["decisions"])
        delays = next(e for e in trace_one["events"] if e["mechanism"] == "backoff")["delays"]
        self.assertEqual(len(set(delays.values())), 2, "two agents must not share a delay")
        for delay in delays.values():
            self.assertTrue(CONFIG["backoff_min_s"] <= delay <= CONFIG["backoff_max_s"])
        self.assertEqual(trace_one["events"], trace_two["events"])

    def test_no_command_is_issued_without_authority_or_precondition_evidence(self):
        without_evidence = [proposal(SCADA, "proposal:a", preconditions=())]
        record, commands, _, _ = resolve("expiring_marks", without_evidence)
        self.assertEqual(commands, [])
        self.assertEqual(record["decisions"][0]["disposition"], "defer")
        self.assertEqual(record["decisions"][0]["reason"]["code"], "no_authority_or_evidence")
        unauthorised = [proposal(SCADA, "proposal:a")]
        record, commands, _, _ = resolve("expiring_marks", unauthorised, config={"authority": {}})
        self.assertEqual(commands, [])

    def test_the_mechanism_reports_what_the_marks_cost(self):
        _, _, trace, _ = resolve("expiring_marks", self.contended())
        marks = trace["marks"]
        self.assertEqual(marks["writes"], 2)
        self.assertGreater(marks["reads"], 0)
        self.assertGreater(marks["bytes"], 0)

    def test_an_unknown_mechanism_is_refused_when_it_is_bound(self):
        with self.assertRaises(ContractError):
            eco_binding(Registry(), [], CONFIG, mechanism="telepathy")
        with self.assertRaises(ContractError):
            eco_binding(Registry(), [], {"agents": []}, stage="diagnosis")
        with self.assertRaises(ContractError):
            eco_binding(Registry(), [], CONFIG, stage="planning")


if __name__ == "__main__":
    unittest.main()
