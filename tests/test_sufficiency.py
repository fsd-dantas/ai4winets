import tempfile
import unittest
from pathlib import Path

from ecora import sufficiency
from ecora.__main__ import CAPABILITIES
from ecora.runner import closed_loop_environment
from ecora.scenario import SCENARIOS, build_world, load
from ecora.study import resolve

PERIOD = 0.5
# Four epochs close the run at 2.0 s, when the study's measured cohort ends. A shorter run
# censors that cohort and a real service difference reads as none.
EPOCHS = 4
SCENARIO = load(SCENARIOS / "s1-degraded-primary.json")
KNOWLEDGE = resolve("baseline")
DOWNSTREAM = ("planning", "resolution", "action", "result", "assurance")


def environment(model):
    return closed_loop_environment(model, period_s=PERIOD, scenario=SCENARIO, study=KNOWLEDGE)


class DeclarationTests(unittest.TestCase):
    """What holds before anything runs: the subsets, identifiability and the bindings."""

    def test_every_expected_signal_is_withheld_exactly_once(self):
        subsets = sufficiency.observation_subsets(KNOWLEDGE.projection)
        self.assertEqual(subsets["full"], [])
        withheld = [names[0] for subset, names in subsets.items() if subset != "full"]
        self.assertEqual(sorted(withheld), sorted(
            sufficiency.signal_name(e) for e in KNOWLEDGE.projection["expected"]))
        self.assertTrue(all(len(names) == 1 for s, names in subsets.items() if s != "full"))

    def test_identifiability_follows_derived_labels(self):
        rules = KNOWLEDGE.rules["rules"]
        self.assertEqual(sufficiency.unidentifiable(rules, []), [])
        # A label concluded from other labels is lost with them, not only with its signals.
        self.assertIn("settled_on_alternative_path",
                      sufficiency.unidentifiable(rules, ["queue_occupancy"]))
        self.assertEqual(sufficiency.unidentifiable(rules, ["site-1/alternative/path_probe"]),
                         ["alternative_viable"])

    def test_downstream_is_identical_across_every_arm_and_subset(self):
        registry, study, scenario_set, scenario, caps = environment(build_world(SCENARIO))
        extended, subsets = sufficiency.sufficiency_study(study, caps, KNOWLEDGE.projection)
        treatments = {t["treatment_id"]: {b["stage_id"]: b for b in t["bindings"]}
                      for t in extended.data["treatments"]
                      if t["treatment_id"].startswith("sufficiency:")}
        self.assertEqual(len(treatments), 2 * len(subsets))
        identities = {stage: {(b[stage]["provider_id"], b[stage]["configuration_hash"])
                              for b in treatments.values()} for stage in DOWNSTREAM}
        for stage, seen in identities.items():
            self.assertEqual(len(seen), 1, f"{stage} varies across the comparison")
        # Every added cell is admissible under the registry's ordinary checks.
        for treatment in treatments:
            registry.admit(extended, scenario_set, scenario, caps, treatment, f"run:{treatment}")

    def test_both_arms_are_restricted_to_the_same_signals(self):
        _, study, _, _, caps = environment(build_world(SCENARIO))
        extended, subsets = sufficiency.sufficiency_study(study, caps, KNOWLEDGE.projection)
        by_id = {c["capability_id"]: c for c in caps.data["capabilities"]}
        bindings = {t["treatment_id"]: {b["stage_id"]: b for b in t["bindings"]}
                    for t in extended.data["treatments"]}
        for subset, withheld in subsets.items():
            with self.subTest(subset=subset):
                expected = bindings[f"sufficiency:contract:{subset}"]["telemetry"]["configuration"]["expected"]
                reads = bindings[f"sufficiency:privileged:{subset}"]["diagnosis"]["configuration"]["reads"]
                relayed = {sufficiency.signal_name(e) for e in expected}
                read = {sufficiency.signal_name({"subject": by_id[c]["target"],
                                                 "metric": by_id[c]["name"]}) for c in reads}
                self.assertEqual(relayed, read)
                self.assertFalse(relayed & set(withheld))
                self.assertEqual(bindings[f"sufficiency:privileged:{subset}"]["diagnosis"]["information_regime"],
                                 "oracle_state")
                self.assertEqual(bindings[f"sufficiency:contract:{subset}"]["diagnosis"]["information_regime"],
                                 "contract_only")


class ComparisonTests(unittest.TestCase):
    """B38 over a scenario where the alternative leg matters."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.runs, cls.subsets = sufficiency.execute(
            Path(cls.temp.name), build_model=lambda: build_world(SCENARIO),
            environment=environment, capability_ids=CAPABILITIES, knowledge=KNOWLEDGE,
            period_s=PERIOD, epochs=EPOCHS)
        cls.comparison = sufficiency.compare(cls.runs, cls.subsets, KNOWLEDGE.rules)
        cls.rows = {row["subset"]: row for row in cls.comparison["rows"]}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_every_cell_ran_under_one_frozen_study(self):
        self.assertEqual(len(self.runs), 2 * len(self.subsets))
        self.assertEqual(len({run["study_hash"] for run in self.runs.values()}), 1)

    def test_no_arm_misses_a_label_its_subset_leaves_identifiable(self):
        """Every miss is explained by the subset, and no arm concludes what is false."""
        for subset, row in self.rows.items():
            for arm in ("contract", "privileged"):
                with self.subTest(subset=subset, arm=arm):
                    diagnosis = row[arm]["diagnosis"]
                    self.assertEqual(diagnosis["spurious"], {})
                    self.assertLessEqual(set(diagnosis["missed"]), set(row["unidentifiable"]))
        full = self.rows["full"]["privileged"]["diagnosis"]
        self.assertEqual(full["exact_epochs"], full["epochs"])

    def test_the_scorer_reads_truth_without_handing_it_to_the_controller(self):
        for (subset, arm), run in self.runs.items():
            with self.subTest(subset=subset, arm=arm):
                self.assertEqual(run["scorer_reads"],
                                 EPOCHS * len(KNOWLEDGE.oracle["diagnosis_reads"]))
                self.assertEqual(run["privileged"], arm == "privileged")

    def test_a_withheld_signal_can_cost_service_that_access_does_not_recover(self):
        """Without the alternative probe no arm may switch, privileged or not."""
        row = self.rows["without:site-1/alternative/path_probe"]
        self.assertEqual(row["contract"]["applied"], 0)
        self.assertEqual(row["privileged"]["applied"], 0)
        self.assertGreater(row["subset_cost"]["scada"], 0)
        self.assertEqual(row["access_headroom"]["scada"], 0)

    def test_no_access_headroom_where_the_contract_relays_fresh_evidence(self):
        """The finding for this model and these states, not a general claim."""
        for subset, row in self.rows.items():
            with self.subTest(subset=subset):
                self.assertTrue(all(gap == 0 for gap in row["access_headroom"].values()))


if __name__ == "__main__":
    unittest.main()
