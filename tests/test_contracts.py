import copy
import json
import random
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from ecora.contracts import ContractError, Record, canonical, decode, digest
from ecora.fixtures import batch, command, fixture_environment, observation, payload_fixtures
from ecora.schema import schema_document


class ContractTests(unittest.TestCase):
    def test_schema_is_valid_and_exports_match(self):
        schema = schema_document()
        Draft202012Validator.check_schema(schema)
        path = Path(__file__).resolve().parents[1] / "data/schemas/ecora-v1.schema.json"
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), schema)

    def test_all_payload_round_trips_and_required_fields(self):
        for record in payload_fixtures():
            with self.subTest(kind=record.kind):
                self.assertEqual(Record.from_json(record.to_json()), record)
                for field in record.data:
                    invalid = record.data
                    del invalid[field]
                    with self.assertRaises(ContractError, msg=f"{record.kind}.{field}"):
                        Record(record.kind, invalid)
                with self.assertRaises(ContractError):
                    Record(record.kind, {**record.data, "undeclared": True})

    def test_exported_payload_fixtures(self):
        path = Path(__file__).resolve().parents[1] / "data/fixtures/contracts-v1.json"
        documents = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual([Record.from_dict(d) for d in documents], list(payload_fixtures()))

    def test_record_and_nested_copies_are_immutable(self):
        source = {"state": {"nested": [1]}, "privileged_source_refs": [], "state_schema_version": "1"}
        record = Record("Snapshot", source)
        source["state"]["nested"].append(2)
        detached = record.data
        detached["state"]["nested"].append(3)
        self.assertEqual(record.data["state"], {"nested": [1]})
        with self.assertRaises(AttributeError):
            record._raw = b"{}"

    def test_key_order_and_random_nested_round_trip_properties(self):
        rng = random.Random(2048)
        for _ in range(100):
            values = {str(i): [rng.randrange(10000), rng.random(), None, "fixture"] for i in range(12)}
            reverse = dict(reversed(list(values.items())))
            self.assertEqual(canonical(values), canonical(reverse))
            self.assertEqual(decode(canonical(values)), values)

    def test_non_json_and_non_finite_values_rejected_recursively(self):
        for value in (float("nan"), float("inf"), -float("inf"), {1: "key"}, (1,), object()):
            with self.subTest(value=repr(value)), self.assertRaises(ContractError):
                canonical({"nested": [value]})
        for raw in ('{"x":NaN}', '{"x":1e999}', '{"x":1,"x":2}'):
            with self.assertRaises(ContractError):
                decode(raw)

    def test_version_and_payload_hash_tampering(self):
        record = batch()
        for version in ("0", "2", 1):
            doc = record.to_dict()
            doc["schema_version"] = version
            with self.assertRaises(ContractError):
                Record.from_dict(doc)
        doc = record.to_dict()
        doc["data"]["observations"][0]["value"] += 1
        with self.assertRaises(ContractError):
            Record.from_dict(doc)

    def test_units_missingness_ranges_and_temporal_order(self):
        changes = [{"unit": "bit/s"}, {"value": -1}, {"value": True}, {"value": 2.5},
                   {"value": 70000}, {"value": None}, {"quality": "missing"},
                   {"available_at_s": 1}, {"event_time_s": 1},
                   {"evidence_kind": "simulator_truth"}, {"metric": "injected_failure_label"},
                   {"quality": "derived", "evidence_kind": "derived"}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ContractError):
                batch(observations=[observation(**change)])

    def test_capability_and_scenario_duplicates(self):
        _, _, _, scenario, caps = fixture_environment()
        for record, field in ((scenario, "flows"), (caps, "capabilities")):
            data = record.data
            data[field].append(data[field][0])
            with self.assertRaises(ContractError):
                Record(record.kind, data)

    def test_action_cannot_write_study_or_defer_scada(self):
        for change in ({"write_set": ["study/requirements"]}, {"service": "scada"},
                       {"expires_at_s": 0}, {"scope": "site"},
                       {"arguments": {"profile": "unlimited"}}, {"precondition_evidence_ids": []}):
            with self.subTest(change=change), self.assertRaises(ContractError):
                command(**change)

    def test_receipt_evidence_and_cohort_conservation(self):
        records = {r.kind: r for r in payload_fixtures()}
        d = records["ActionReceipt"].data
        d.update(disposition="applied", applied_at_s=0)
        with self.assertRaises(ContractError):
            Record("ActionReceipt", d)
        for field in ("delivered_on_time", "lost", "pending"):
            d = records["ResultRecord"].data
            d["cohorts"][0][field] += 1
            with self.assertRaises(ContractError):
                Record("ResultRecord", d)


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry, self.study, self.scenario_set, self.scenario, self.caps = fixture_environment()

    def admit(self, **changes):
        args = dict(study=self.study, scenario_set=self.scenario_set, scenario=self.scenario,
                    capabilities=self.caps, treatment_id="reference", run_id="run:fixture")
        return self.registry.admit(**(args | changes))

    def test_binding_completeness_and_configuration_integrity(self):
        for mutate in (lambda b: b.pop(), lambda b: b.append(copy.deepcopy(b[0])),
                       lambda b: b[0]["configuration"].update(hidden=True)):
            data = self.study.data
            mutate(data["treatments"][0]["bindings"])
            with self.assertRaises(ContractError):
                Record("StudyManifest", data)

    def test_unresolved_provider_and_schema_mismatch(self):
        for field, value in (("provider_version", "missing"), ("arm", "null"),
                             ("input_types", ["PlanProposal"]), ("capability_ids", ["missing"])):
            data = self.study.data
            data["treatments"][0]["bindings"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ContractError):
                self.admit(study=Record("StudyManifest", data))

    def test_freeze_membership_and_run_identifiers(self):
        altered = Record("ScenarioSpec", self.scenario.data | {"initial_state": {"changed": True}})
        with self.assertRaises(ContractError):
            self.admit(scenario=altered)
        with self.assertRaises(ContractError):
            self.admit(treatment_id="unregistered")
        with self.assertRaises(ContractError):
            self.admit(run_id="../../bad path")
        self.assertEqual(self.admit().scope["scenario_hash"], self.scenario.content_hash)

    def test_ordinary_provider_cannot_request_direct_truth(self):
        data = self.study.data
        data["treatments"][0]["bindings"][0]["information_regime"] = "oracle_state"
        with self.assertRaises(ContractError):
            Record("StudyManifest", data)
        spec = self.registry.resolve(self.study.data["treatments"][0]["bindings"][0]).spec
        with self.assertRaises(ContractError):
            Record("ProviderSpec", spec.data | {"direct_truth_access": True})
