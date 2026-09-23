"""The declared failure cases, exercised end to end.

Each case the milestone names is covered here or in the test noted beside it:

- missing observations  : this module
- stale commands        : test_boundary.test_stale_command_cannot_reach_action_provider
- conflicting proposals : this module
- unknown receipts      : this module
- interrupted runs      : test_boundary.test_writer_lock_and_partial_invocation_quarantine
                          and test_boundary.test_journal_write_failure_prevents_provider_execution

A failure case is evidence. None of these may be dropped, silently repaired, or turned
into a success by the stage that met it.
"""

import tempfile
import unittest
from pathlib import Path

from ecora.boundary import Boundary
from ecora.contracts import ContractError, Record
from ecora.fixtures import batch, fixture_environment, observation, reason
from ecora.registry import ProviderResult
from ecora.store import ArtifactStore


def proposal(proposal_id, *, path="alternative"):
    step = {"operator": "select_path", "target": "site-1", "arguments": {"path": path},
            "preconditions": ["observation:ami:0"], "add_effects": [], "delete_effects": [],
            "cost": 2}
    return Record("PlanProposal", {
        "proposal_id": proposal_id, "agent_id": "agent:site-1:ami", "site_id": "site-1",
        "service": "ami", "steps": [step], "assumptions": [], "estimated_cost": 2,
        "valid_until_s": 1, "goal_status": "unmet", "certificate_ref": None,
        "state_versions": {"site-1/selected_path": 0, "site-1/pacing_profile": 0}})


class StrayReceiptProvider:
    """Returns a receipt for a command the resolution stage never issued."""

    def invoke(self, inputs, prior_state, context):
        return ProviderResult((Record("ActionReceipt", {
            "command_id": "command:never-issued", "idempotency_key": "idempotency:stray",
            "disposition": "applied", "applied_at_s": 0, "resulting_state": {},
            "application_observation_ids": ["observation:ami:0"], "reason": None}),), {}, {})


class FailureCaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def open(self, name, treatment="null_baseline", environment=None):
        registry, study, scenario_set, scenario, caps = environment or fixture_environment()
        store = ArtifactStore(Path(self.temp.name) / name)
        self.addCleanup(store.close)
        run = registry.admit(study, scenario_set, scenario, caps, treatment, f"run:{name}")
        return store, Boundary(store, registry, run), registry

    def test_missing_observations_are_retained_as_unknown_not_dropped(self):
        store, boundary, _ = self.open("missing", treatment="reference")
        absent = observation(quality="missing", value=None,
                             missing_reason=reason("sensor_gap", "No sample in this window."))
        supplied = Record("AdapterObservationBatch", {
            "observations": [absent], "watermark_s": 0, "window": {"start_s": 0, "end_s": 0},
            "sequence": 0, "completeness": 0, "omitted_metrics": []})
        self.assertLess(supplied.data["completeness"], 1)
        source = boundary.ingest("ingest", supplied, watermark_s=0)
        telemetry = boundary.invoke("telemetry", "telemetry",
                                    [source.data["dataset_id"]], watermark_s=0)
        self.assertEqual(telemetry.data["terminal_status"], "ok")
        carried = Record.from_dict(store.messages(telemetry.data["dataset_id"])[0].data["payload"])
        kept = carried.data["observations"][0]
        self.assertEqual(kept["quality"], "missing")
        self.assertIsNone(kept["value"])
        self.assertEqual(kept["missing_reason"]["code"], "sensor_gap")

    def test_a_batch_cannot_claim_full_coverage_while_withholding_a_signal(self):
        with self.assertRaises(ContractError):
            Record("AdapterObservationBatch", {
                "observations": [observation(quality="missing", value=None,
                                             missing_reason=reason("gap", "No sample."))],
                "watermark_s": 0, "window": {"start_s": 0, "end_s": 0}, "sequence": 0,
                "completeness": 1, "omitted_metrics": []})

    def test_conflicting_proposals_resolve_to_one_with_the_rest_deferred(self):
        store, boundary, _ = self.open("conflict")
        first = boundary.ingest("ingest:a", proposal("proposal:a"),
                                destination="resolution", watermark_s=0)
        second = boundary.ingest("ingest:b", proposal("proposal:b", path="lte"),
                                 destination="resolution", watermark_s=0)
        resolved = boundary.invoke("resolution", "resolution",
                                   [first.data["dataset_id"], second.data["dataset_id"]],
                                   watermark_s=0)
        self.assertEqual(resolved.data["terminal_status"], "ok")
        payloads = [Record.from_dict(m.data["payload"])
                    for m in store.messages(resolved.data["dataset_id"])]
        record = next(p for p in payloads if p.kind == "ResolutionRecord")
        dispositions = sorted(d["disposition"] for d in record.data["decisions"])
        self.assertEqual(dispositions, ["admit", "defer"])
        # Both competing proposals are accounted for, and only one command is issued.
        self.assertEqual(sorted(record.data["proposal_ids"]), ["proposal:a", "proposal:b"])
        self.assertEqual(len(record.data["command_ids"]), 1)
        self.assertEqual(sum(1 for p in payloads if p.kind == "ActionCommand"), 1)

    def test_a_receipt_for_a_command_that_was_never_issued_is_refused(self):
        registry, study, scenario_set, scenario, caps = fixture_environment()
        # study.data decodes a fresh copy on every access, so hold one and mutate that.
        data = study.data
        binding = next(b for b in data["treatments"][0]["bindings"] if b["stage_id"] == "action")
        spec = Record("ProviderSpec", {**registry.resolve(binding).spec.data,
                                       "provider_id": "fixture.stray_receipt"})
        registry.register(spec, StrayReceiptProvider)
        binding["provider_id"] = spec.data["provider_id"]
        environment = (registry, Record("StudyManifest", data), scenario_set, scenario, caps)
        store, boundary, _ = self.open("stray", treatment="reference", environment=environment)
        from ecora.fixtures import command
        source = boundary.ingest("ingest", command(), destination="action", watermark_s=0)
        result = boundary.invoke("action", "action", [source.data["dataset_id"]], watermark_s=0)
        self.assertEqual(result.data["terminal_status"], "rejected")
        self.assertIn("unknown command", result.data["reason"]["detail"])

    def test_an_unknown_receipt_is_retained_and_claims_no_application(self):
        unknown = Record("ActionReceipt", {
            "command_id": "command:fixture", "idempotency_key": "idempotency:fixture",
            "disposition": "unknown", "applied_at_s": None, "resulting_state": {},
            "application_observation_ids": [],
            "reason": reason("no_confirmation", "The actuator did not confirm; reconcile.")})
        self.assertIsNone(unknown.data["applied_at_s"])
        self.assertEqual(unknown.data["application_observation_ids"], [])
        # An unknown outcome cannot be recorded as applied without observed evidence.
        with self.assertRaises(ContractError):
            Record("ActionReceipt", {**unknown.data, "disposition": "applied",
                                     "applied_at_s": 0})


if __name__ == "__main__":
    unittest.main()
