import copy
import json
import unittest
from pathlib import Path

from ecora.contracts import ContractError, Record
from ecora.eco import eco_binding
from ecora.experts import expert_binding
from ecora.planning import SEARCHES, planner_binding
from ecora.registry import Registry
from ecora.runner import observation_batch
from ecora.scenario import SCENARIOS, build_world, load as load_scenario
from ecora.study import STUDIES, Study, catalogue, load, resolve
from ecora.symbolic import catalog, predicate, validate_plan

CAPABILITIES = {("site-1", "queue_occupancy"): "observe.ami.queue",
                ("site-1", "path_state"): "observe.shared.path",
                ("site-1", "pacing_profile"): "observe.ami.pacing",
                ("site-1/lte", "path_probe"): "observe.probe.lte",
                ("site-1/alternative", "path_probe"): "observe.probe.alternative"}
GRANTS = ["actuate.shared.path", "actuate.ami.pacing"]


class Message:
    def __init__(self, record):
        self.data = {"payload": record.to_dict()}


class Snapshot:
    def __init__(self):
        self.data = {"state": {}}


class Context:
    def __init__(self, configuration, watermark=2.0):
        self.data = {"configuration": configuration, "decision_watermark_s": watermark}


def raw(name="baseline"):
    return json.loads((STUDIES / f"{name}.json").read_text(encoding="utf-8"))


def diagnose(study, scenario="s1-degraded-primary", at=1.5, organisation="blackboard"):
    """Run the blackboard organisation over one study's inventory and real observations."""
    world = build_world(load_scenario(SCENARIOS / f"{scenario}.json")).advance_to(at)
    relayed = Record("TelemetryBatch",
                     observation_batch(world, CAPABILITIES, at, 0.5, 0).data)
    registry = Registry()
    binding = expert_binding(registry, [], study.rules, organisation)
    result = registry.resolve(binding).factory().invoke(
        [Message(relayed)], Snapshot(), Context(binding["configuration"], at))
    return result.outputs[0].data


class ReadingTests(unittest.TestCase):
    def test_every_published_study_loads_and_is_addressed_by_its_content(self):
        found = catalogue()
        self.assertGreaterEqual(len(found), 2)
        for identity, study in found.items():
            with self.subTest(study=identity):
                self.assertEqual(study.content_hash, load(STUDIES / f"{Path(identity.split(':')[1])}.json").content_hash)
                self.assertTrue(study.note)

    def test_a_study_may_be_named_or_given_as_a_path(self):
        self.assertEqual(resolve("baseline").content_hash,
                         resolve(STUDIES / "baseline.json").content_hash)
        with self.assertRaises(ContractError):
            resolve("no-such-study")

    def test_a_missing_or_unknown_section_is_refused_when_the_file_is_read(self):
        """A section silently ignored would leave the default in place."""
        for dropped in ("rules", "assembly", "predicate_map"):
            with self.subTest(section=dropped):
                data = raw()
                del data[dropped]
                with self.assertRaises(ContractError):
                    Study(data)
        with self.assertRaises(ContractError):
            Study({**raw(), "ruels": {}})

    def test_an_incoherent_inventory_is_refused(self):
        data = raw()
        data["rules"]["rules"].append(dict(data["rules"]["rules"][0]))
        with self.assertRaises(ContractError):
            Study(data)
        data = raw()
        data["rules"]["rules"][0]["contradicts"] = ["nothing_concludes_this"]
        with self.assertRaises(ContractError):
            Study(data)
        data = raw()
        data["predicate_map"]["unreachable_label"] = ["selected_path:site-1:lte"]
        with self.assertRaises(ContractError):
            Study(data)
        data = raw()
        data["assembly"]["planning"]["goals"] = ["not_a_ground_predicate"]
        with self.assertRaises(ContractError):
            Study(data)


class ArbitrationTests(unittest.TestCase):
    def test_the_baseline_declares_contradictions_it_can_never_reach(self):
        """Every baseline pair is mutually exclusive, so arbitration cannot run."""
        self.assertEqual(resolve("baseline").arbitrable(), [])

    def test_the_arbitration_study_reaches_both_kinds(self):
        pairs = resolve("arbitration").arbitrable()
        self.assertIn("equal_priority", [kind for _, _, kind in pairs])
        self.assertIn("priority_inhibition", [kind for _, _, kind in pairs])

    def test_equal_authority_is_reported_unresolved_rather_than_decided(self):
        record = diagnose(resolve("arbitration"))
        self.assertEqual(sorted(record["unresolved_conflicts"]),
                         ["degraded_primary", "demand_outpacing"])
        self.assertEqual(resolve("baseline").arbitrable(), [])
        self.assertEqual(diagnose(resolve("baseline"))["unresolved_conflicts"], [])

    def test_the_conflict_is_reachable_over_a_window_and_not_a_single_instant(self):
        """With real probes the conflict needs a leg slow but still answering.

        That holds from when the load arrives until the leg's backlog makes its probe time
        out, so it is a window. A window that closed would make the arbitration the study
        declares unreachable again, which is the shape of defect this study exists to avoid.
        """
        reached = [at / 10 for at in range(10, 30)
                   if diagnose(resolve("arbitration"), at=at / 10)["unresolved_conflicts"]]
        self.assertGreaterEqual(len(reached), 3, reached)
        self.assertIn(1.5, reached)

    def test_the_weaker_of_two_authorities_is_inhibited_and_recorded(self):
        record = diagnose(resolve("arbitration"))
        inhibited = record["rule_trace"][0]["inhibited"]
        self.assertIn({"rule_id": "prefer_primary", "reason": "lower_priority",
                       "against": "alternative_preferred"}, inhibited)
        labels = {h["label"] for h in record["hypotheses"] if h["status"] == "supported"}
        self.assertIn("alternative_preferred", labels)
        self.assertNotIn("primary_preferred", labels)

    def test_an_inhibition_is_recorded_once_and_not_once_per_pass(self):
        """The trace is evidence: counting entries must not be counting passes."""
        inhibited = diagnose(resolve("arbitration"))["rule_trace"][0]["inhibited"]
        self.assertEqual(len(inhibited), len({json.dumps(e, sort_keys=True)
                                              for e in inhibited}))

    def test_no_accumulated_trace_field_repeats_an_entry(self):
        """Every list that grows across inference passes, not only the one that failed."""
        for organisation in ("single_engine", "blackboard"):
            with self.subTest(organisation=organisation):
                record = diagnose(resolve("arbitration"), organisation=organisation)
                trace = record["rule_trace"][0]
                for field, entries in (("inhibited", trace["inhibited"]),
                                       ("fired", trace["fired"]),
                                       ("unresolved_conflicts",
                                        record["unresolved_conflicts"]),
                                       ("hypotheses", [h["label"]
                                                       for h in record["hypotheses"]])):
                    with self.subTest(field=field):
                        rendered = [json.dumps(e, sort_keys=True) for e in entries]
                        self.assertEqual(len(rendered), len(set(rendered)),
                                         f"{field} repeats an entry across passes")


class PlanningTests(unittest.TestCase):
    def known(self):
        return frozenset([predicate("selected_path", "site-1", "lte"),
                          predicate("reachable", "site-1", "lte"),
                          predicate("reachable", "site-1", "alternative"),
                          predicate("pacing", "site-1", "normal")])

    def solve(self, study, search="uniform_cost"):
        operators = catalog(study.planner["sites"], study.planner["costs"])
        goals = study.assembly["planning"]["goals"]
        plan, cost, _ = SEARCHES[search](self.known(), frozenset(), operators, goals, 10000)
        achieved, _, _ = validate_plan(self.known(), frozenset(), operators, goals, plan or ())
        return plan, cost, achieved

    def test_one_goal_over_one_fluent_needs_one_action(self):
        plan, cost, achieved = self.solve(resolve("baseline"))
        self.assertEqual(len(plan), 1)
        self.assertTrue(achieved)

    def test_two_goals_over_two_fluents_need_a_sequence(self):
        for search in ("uniform_cost", "gps", "astar"):
            with self.subTest(search=search):
                plan, cost, achieved = self.solve(resolve("multi-goal"), search)
                self.assertEqual(len(plan), 2)
                self.assertEqual(cost, 3)
                self.assertTrue(achieved)

    def test_a_pacing_operator_declares_the_profile_it_moves_from(self):
        """Without it the delete effect removes a predicate nobody established."""
        operators = catalog(["site-1"], {"select_path": 2, "set_ami_pacing": 1})
        pacing = [o for o in operators if o.action == "set_ami_pacing"]
        self.assertTrue(pacing)
        for operator in pacing:
            with self.subTest(operator=operator.operator_id):
                self.assertTrue(operator.preconditions,
                                "a mutation with nothing to cite can never be issued")
                self.assertEqual(operator.delete, operator.preconditions)


class ContentionTests(unittest.TestCase):
    def proposals(self, study):
        known = sorted([predicate("selected_path", "site-1", "lte"),
                        predicate("reachable", "site-1", "lte"),
                        predicate("reachable", "site-1", "alternative"),
                        predicate("pacing", "site-1", "normal")])
        problem = Record("PlanningProblem", {**study.assembly["planning"],
                                             "known_predicates": known,
                                             "unknown_predicates": []})
        registry = Registry()
        binding = planner_binding(registry, GRANTS, study.planner, "uniform_cost")
        result = registry.resolve(binding).factory().invoke(
            [Message(problem)], Snapshot(), Context(binding["configuration"]))
        return registry, result.outputs

    def test_one_agent_produces_one_proposal_and_two_produce_two(self):
        self.assertEqual(len(self.proposals(resolve("baseline"))[1]), 1)
        _, proposals = self.proposals(resolve("contention"))
        self.assertEqual(len(proposals), 2)
        self.assertEqual(len({p.data["proposal_id"] for p in proposals}), 2,
                         "two agents must not collide on one proposal identity")
        self.assertEqual({p.data["service"] for p in proposals}, {"scada", "ami"})

    def test_two_agents_contend_for_the_resource_they_both_write(self):
        registry, proposals = self.proposals(resolve("contention"))
        study = resolve("contention")
        binding = eco_binding(registry, GRANTS, study.eco, "resolution", "expiring_marks")
        result = registry.resolve(binding).factory().invoke(
            [Message(p) for p in proposals], Snapshot(), Context(binding["configuration"]))
        record = next(r for r in result.outputs if r.kind == "ResolutionRecord")
        dispositions = sorted(d["disposition"] for d in record.data["decisions"])
        self.assertEqual(dispositions, ["admit", "defer"],
                         "one contender is admitted and the rest defer")
        self.assertTrue(any(d["conflicting_proposal_ids"] for d in record.data["decisions"]),
                        "the record must name what each proposal conflicted with")

    def test_an_agent_may_not_pursue_a_goal_the_study_did_not_freeze(self):
        study = resolve("contention")
        loosened = copy.deepcopy(study.data)
        loosened["planner"]["agents"][0]["goals"] = ["pacing:site-1:normal"]
        with self.assertRaises(ContractError):
            self.proposals(Study(loosened))


class ArmCoverageTests(unittest.TestCase):
    """Every stage carries the arms its evaluation case designates, and each resolves.

    A declared binding that no registered provider answers is a cell that cannot run, and
    a study whose coverage is assumed rather than checked is how an unsupported cell comes
    to be reported as though it had been measured.
    """

    def environment(self):
        from ecora.runner import closed_loop_environment
        model = build_world(load_scenario(SCENARIOS / "s0-nominal.json"))
        return closed_loop_environment(model, period_s=0.5)

    def test_every_stage_carries_all_three_arms(self):
        from ecora.schema import STAGES
        registry, study, _, _, _ = self.environment()
        arms = {stage: set() for stage in STAGES}
        for treatment in study.data["treatments"]:
            for binding in treatment["bindings"]:
                arms[binding["stage_id"]].add(binding["arm"])
        for stage in STAGES:
            with self.subTest(stage=stage):
                self.assertEqual(arms[stage], {"null", "proposed", "oracle"},
                                 f"{stage} is missing an arm its evaluation case designates")

    def test_every_declared_binding_resolves_to_a_registered_provider(self):
        registry, study, _, _, _ = self.environment()
        for treatment in study.data["treatments"]:
            for binding in treatment["bindings"]:
                with self.subTest(treatment=treatment["treatment_id"],
                                  stage=binding["stage_id"]):
                    entry = registry.resolve(binding)
                    self.assertIsNotNone(entry.factory)
                    self.assertTrue(hasattr(entry.factory(), "invoke"),
                                    "a binding must resolve to something that can be invoked")

    def test_an_oracle_binding_declares_its_information_regime(self):
        """A privileged arm must be labelled as one, or its results read as ordinary."""
        _, study, _, _, _ = self.environment()
        for treatment in study.data["treatments"]:
            for binding in treatment["bindings"]:
                if binding["arm"] != "oracle":
                    continue
                with self.subTest(provider=binding["provider_id"]):
                    self.assertIn(binding["information_regime"],
                                  ("contract_only", "oracle_state"))
                    if binding["information_regime"] == "oracle_state":
                        self.assertTrue(binding["allow_privileged_inputs"])


if __name__ == "__main__":
    unittest.main()
