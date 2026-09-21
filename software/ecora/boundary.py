"""Audited invocation seam. This is not the M2 simulator/run orchestrator."""

from .contracts import ContractError, Record, require
from .registry import ProviderResult, Registry
from .schema import INPUT_TYPES, OUTPUT_TYPES, STAGES, STATUSES
from .store import ArtifactStore


NEXT_STAGE = dict(zip(STAGES, (*STAGES[1:], "sink")))


class Boundary:
    def __init__(self, store: ArtifactStore, registry: Registry, run):
        # Revalidate even a manually constructed AdmittedRun.
        self.run = registry.admit(run.study, run.scenario_set, run.scenario,
                                  run.capabilities, run.treatment_id, run.run_id)
        self.store, self.registry = store, registry
        hashes = [store.put(r) for r in (run.study, run.scenario_set, run.scenario, run.capabilities)]
        store.register_run(run.scope, run.treatment_id, hashes)

    def _capability(self, observation, permitted, accept_privileged=False):
        cap = self.run.capability(observation["capability_id"])
        require(cap["kind"] == ("truth" if observation["evidence_kind"] == "simulator_truth" else "observe"),
                "observation access kind mismatch")
        for left, right in (("target", "subject"), ("service", "service"), ("name", "metric"), ("unit", "unit")):
            require(cap[left] == observation[right], f"observation exceeds capability {left}")
        if observation["capability_id"] not in permitted:
            # Receiving a logged Oracle-derived field is not permission to open TruthPort.
            require(accept_privileged and cap["kind"] == "truth", "observation capability not granted")
            allowed = [self.run.capability(c) for c in permitted]
            require(any(c["kind"] == "observe" and all(c[k] == cap[k] for k in ("target", "service", "name", "unit"))
                        for c in allowed), "privileged field exceeds the recipient's observation scope")

    def _payload_checks(self, payload, binding, watermark, refs, *, input_record=False):
        data = payload.data
        if payload.kind in {"AdapterObservationBatch", "TelemetryBatch"}:
            require(data["watermark_s"] <= watermark, "telemetry is from a future watermark")
            for observation in data["observations"]:
                self._capability(observation, binding["capability_ids"], binding.get("allow_privileged_inputs", False))
                require(set(observation["privileged_source_refs"]) <= refs, "provider invented truth lineage")
                require(observation["available_at_s"] <= watermark, "future observation")
        elif payload.kind == "ActionCommand":
            cap_id = data["authority_capability_id"]
            require(cap_id in binding["capability_ids"], "actuator capability not granted")
            cap = self.run.capability(cap_id)
            require(cap["kind"] == "actuate" and cap["name"] == data["operator"]
                    and cap["target"] == data["target"] and cap["service"] == data["service"],
                    "command exceeds actuator permission")
            require(watermark < data["expires_at_s"], "stale command")
            if input_record:
                require(data["not_before_s"] <= watermark, "command dispatched too early")
        elif payload.kind == "PlanProposal":
            require(data["valid_until_s"] >= watermark, "expired plan proposal")
        elif payload.kind == "ActionReceipt":
            require(data["applied_at_s"] is None or data["applied_at_s"] <= watermark,
                    "receipt asserts future application")
        elif payload.kind == "AssuranceReport":
            require(data["study_id"] == self.run.scope["study_id"]
                    and data["scenario_set_hash"] == self.run.scope["scenario_set_hash"]
                    and data["scenario_set_version"] == self.run.scope["scenario_set_version"],
                    "report names a different frozen benchmark")
            require(self.run.run_id in data["contributing_run_ids"], "run report omits its producing run")

    def _inputs(self, dataset_ids, stage, watermark, binding):
        inputs, refs = [], set()
        require(len(dataset_ids) == len(set(dataset_ids)), "duplicate input dataset")
        for dataset_id in dataset_ids:
            dataset = self.store.dataset(dataset_id).data
            require(dataset["scope"] == self.run.scope, "input belongs to another run or benchmark")
            refs.update(dataset["privileged_source_refs"])
            for message in self.store.messages(dataset_id):
                m = message.data
                if m["destination_stage"] != stage:
                    continue
                require(m["available_at_s"] <= watermark, "message is unavailable at decision watermark")
                payload = Record.from_dict(m["payload"])
                if payload.kind == "ActionCommand":
                    require(m["status"] == "ok", "non-admitted command cannot reach an actuator")
                require(payload.kind in (*INPUT_TYPES[stage], "BoundaryOutcome"), "input schema seam mismatch")
                self._payload_checks(payload, binding, watermark, set(m["privileged_source_refs"]), input_record=True)
                inputs.append(message)
        require(not refs or binding["allow_privileged_inputs"], "privileged input is forbidden for this binding")
        return tuple(inputs), refs

    def _start(self, invocation_id, dataset_ids, records):
        self.store.append("InputRecorded", {"invocation_id": invocation_id,
                                            "input_dataset_ids": list(dataset_ids),
                                            "record_hashes": [self.store.put(r) for r in records]})
        self.store.append("Started", {"invocation_id": invocation_id})

    def _finish(self, invocation_id, stage, binding, dataset_ids, payloads, prior, next_state,
                random_state, trace, watermark, refs, status, reason, destination=None):
        require(status in STATUSES, "unknown terminal status")
        refs = sorted(refs)
        regime = "oracle_state" if refs else "contract_only"
        state_version = binding["state_schema_version"]
        def snapshot(state):
            return Record("Snapshot", {"state": state, "privileged_source_refs": refs,
                                       "state_schema_version": state_version})
        next_snapshot, random_snapshot, trace_snapshot = (snapshot(x) for x in (next_state, random_state, trace))
        if not payloads:
            if status == "ok":
                status, reason = "empty", {"code": "empty_output", "detail": "Provider returned no output records."}
            payloads = (Record("BoundaryOutcome", {"status": status, "reason": reason}),)
        dataset_id = f"dataset:{invocation_id}"
        parents = sorted({mid for ds in dataset_ids for mid in self.store.dataset(ds).data["message_ids"]})
        messages, sequences = [], {}
        for index, payload in enumerate(payloads):
            target = destination or NEXT_STAGE.get(stage, "telemetry")
            # A record the next stage does not accept terminates here. DiagnosisRecord,
            # ResolutionRecord and ActionReceipt are retained evidence; the input the next
            # stage consumes is built by assemble() from this dataset.
            if target != "sink" and payload.kind not in INPUT_TYPES.get(target, ()):
                target = "sink"
            key = (stage, target)
            sequence = sequences.get(key, self.store.next_sequence(self.run.run_id, stage, target))
            sequences[key] = sequence + 1
            message = Record("Message", {
                "message_id": f"message:{invocation_id}:{index}", "scope": self.run.scope,
                "stage_invocation_id": invocation_id, "source_stage": stage, "destination_stage": target,
                "provider_id": binding["provider_id"], "provider_version": binding["provider_version"],
                "arm": binding["arm"], "configuration_hash": binding["configuration_hash"],
                "sequence_number": sequence, "correlation_id": invocation_id, "parent_message_ids": parents,
                "input_dataset_ids": list(dataset_ids), "output_dataset_id": dataset_id,
                "clock_domain": "simulation", "event_time_s": watermark, "available_at_s": watermark,
                "decision_watermark_s": watermark, "information_regime": regime, "privileged_source_refs": refs,
                "access_policy_version": "v1", "serialization_version": "ecora-json-v1",
                "replay": {"mode": "none", "original_run_id": None, "original_invocation_id": None},
                "status": status, "reason": reason, "payload": payload.to_dict(),
            })
            self.store.put(message)
            messages.append(message)
        dataset = Record("DatasetArtifact", {
            "dataset_id": dataset_id, "scope": self.run.scope, "stage_invocation_id": invocation_id,
            "stage_id": stage, "provider_id": binding["provider_id"], "provider_version": binding["provider_version"],
            "arm": binding["arm"], "configuration_hash": binding["configuration_hash"],
            "message_ids": [m.data["message_id"] for m in messages], "message_hashes": [m.content_hash for m in messages],
            "record_count": len(messages), "source_dataset_ids": list(dataset_ids),
            "schema_versions": sorted({f"{p.kind}/1" for p in payloads}),
            "time_coverage": {"start_s": watermark, "end_s": watermark}, "format": "ecora-json-v1",
            "information_regime": regime, "privileged_source_refs": refs, "terminal_status": status, "reason": reason,
        })
        invocation = Record("StageInvocation", {
            "invocation_id": invocation_id, "scope": self.run.scope, "stage_id": stage,
            "provider_id": binding["provider_id"], "provider_version": binding["provider_version"],
            "arm": binding["arm"], "configuration_hash": binding["configuration_hash"],
            "input_dataset_ids": list(dataset_ids), "output_dataset_id": dataset_id,
            "prior_state_hash": self.store.put(prior), "next_state_hash": self.store.put(next_snapshot),
            "random_state_hash": self.store.put(random_snapshot), "trace_hash": self.store.put(trace_snapshot),
            "context_hash": self.store.put(Record("ProviderContext", {
                "configuration": binding.get("configuration", {}), "decision_watermark_s": watermark,
                "random_state": random_state, "information_regime": regime, "privileged_source_refs": refs})),
            "decision_watermark_s": watermark, "state_schema_version": state_version,
            "information_regime": regime, "privileged_source_refs": refs, "status": status, "reason": reason,
        })
        self.store.append("OutputRecorded", {"invocation_hash": self.store.put(invocation),
                                              "dataset_hash": self.store.put(dataset)})
        return dataset

    def _harness(self, invocation_id, payload, destination, dataset_ids, watermark_s, refs, provider_id):
        require(destination in STAGES and payload.kind in INPUT_TYPES[destination], "unsupported harness seam")
        caps = [c["capability_id"] for c in self.run.capabilities.data["capabilities"]]
        binding = {"provider_id": provider_id, "provider_version": "1", "arm": "oracle" if refs else "proposed",
                   "configuration_hash": self.run.scenario.content_hash, "capability_ids": caps, "state_schema_version": "1"}
        self._payload_checks(payload, binding, watermark_s, refs)
        prior = Record("Snapshot", {"state": {}, "privileged_source_refs": sorted(refs), "state_schema_version": "1"})
        self._start(invocation_id, dataset_ids, (payload, prior))
        return self._finish(invocation_id, "harness", binding, dataset_ids, (payload,), prior, {}, {}, {},
                            watermark_s, refs, "ok", None, destination)

    def ingest(self, invocation_id, payload, *, destination="telemetry", watermark_s=0):
        """Trusted, logged adapter ingress; not a substitute simulator or truth port."""
        refs = set()
        if payload.kind in ("AdapterObservationBatch", "TelemetryBatch"):
            for observation in payload.data["observations"]:
                refs.update(observation["privileged_source_refs"])
        return self._harness(invocation_id, payload, destination, (), watermark_s, refs, "adapter.ingress")

    def assemble(self, invocation_id, destination, dataset_ids, payload, *, watermark_s=0):
        """Build a downstream stage input from retained upstream evidence.

        The interface defines planning input as a PlanningProblem built from a
        DiagnosisRecord, and result input as receipts plus a cohort specification. That
        construction carries goal selection and cohort choice, which the experimental
        design holds fixed across a stage's Null, Proposed and Oracle arms. It therefore
        cannot sit inside the provider whose arms are being compared, and is logged here
        as its own harness invocation with explicit lineage.
        """
        dataset_ids = tuple(dataset_ids)
        refs = set()
        for dataset_id in dataset_ids:
            source = self.store.dataset(dataset_id).data
            require(source["scope"] == self.run.scope, "assembly input belongs to another run or benchmark")
            refs.update(source["privileged_source_refs"])
        self._conforms(destination, payload)
        return self._harness(invocation_id, payload, destination, dataset_ids, watermark_s, refs, "harness.assembler")

    def _conforms(self, destination, payload):
        """The frozen study owns what is assembled; the run owns only the measured parts."""
        spec = self.run.study.data["assembly"]
        if destination == "planning":
            frozen = spec["planning"]
            for field in ("goals", "operator_catalog_version", "action_costs", "expansion_budget",
                          "time_budget_s", "memory_budget_bytes", "horizon_steps"):
                require(payload.data[field] == frozen[field],
                        f"assembled planning problem departs from the frozen study: {field}")
        elif destination == "result":
            frozen = {c["cohort_id"]: c for c in spec["result"]["cohorts"]}
            require([c["cohort_id"] for c in payload.data["cohorts"]] == list(frozen),
                    "assembled cohorts differ from the frozen study's cohort set")
            for cohort in payload.data["cohorts"]:
                declared = frozen[cohort["cohort_id"]]
                require(cohort["generation_window"] == declared["generation_window"]
                        and cohort["deadline_s"] == declared["deadline_s"],
                        "assembled cohort departs from its frozen window or deadline")

    def invoke(self, stage, invocation_id, dataset_ids, *, watermark_s, prior_state_hash=None, random_state=None):
        require(stage in STAGES, "unknown stage")
        binding = self.run.binding(stage)
        entry = self.registry.resolve(binding)
        try:
            for dataset_id in dataset_ids:
                require(self.store.dataset(dataset_id).data["scope"] == self.run.scope, "cross-run input dataset")
        except ContractError as exc:
            self.store.append("IntegrityFailure", {"reason": str(exc), "invocation_id": invocation_id,
                                                    "input_dataset_ids": list(dataset_ids)})
            raise
        prior = self.store.get(prior_state_hash) if prior_state_hash else Record(
            "Snapshot", {"state": {}, "privileged_source_refs": [], "state_schema_version": binding["state_schema_version"]})
        require(prior.kind == "Snapshot" and prior.data["state_schema_version"] == binding["state_schema_version"],
                "unsupported prior-state schema")
        # Inputs and context are durable before provider execution, including rejected input attempts.
        base_context = Record("ProviderContext", {"configuration": binding["configuration"],
                              "decision_watermark_s": watermark_s, "random_state": random_state or {},
                              "information_regime": "contract_only", "privileged_source_refs": []})
        self._start(invocation_id, dataset_ids, (prior, base_context))
        refs = set(prior.data["privileged_source_refs"])
        # Include all source lineage before validating routing/permission, so even rejection is tainted.
        for dataset_id in dataset_ids:
            refs.update(self.store.dataset(dataset_id).data["privileged_source_refs"])
        try:
            require(not refs or binding["allow_privileged_inputs"], "binding cannot consume privileged state or input")
            inputs, input_refs = self._inputs(dataset_ids, stage, watermark_s, binding)
            refs.update(input_refs)
            require(binding["information_regime"] != "oracle_state" or refs,
                    "direct TruthPort is not implemented; an Oracle binding needs explicit current-truth input")
            context = Record("ProviderContext", {**base_context.data,
                             "information_regime": "oracle_state" if refs else "contract_only",
                             "privileged_source_refs": sorted(refs)})
            self.store.put(context)
            if stage == "action":
                command_hashes = [self.store.put(Record.from_dict(m.data["payload"])) for m in inputs
                                  if m.data["payload"]["record_type"] == "ActionCommand"]
                if command_hashes:
                    self.store.append("DispatchIntent", {"invocation_id": invocation_id,
                        "run_id": self.run.run_id, "command_hashes": command_hashes})
            result = entry.factory().invoke(inputs, prior, context)
            require(isinstance(result, ProviderResult), "provider must return ProviderResult")
            require(type(result.outputs) is tuple, "provider outputs must be a tuple of Records")
            require(result.status in STATUSES, "unknown provider status")
            require(result.status == "ok" or result.reason is not None, "terminal provider status requires reason")
            for output in result.outputs:
                require(isinstance(output, Record) and output.kind in (*OUTPUT_TYPES[stage], "BoundaryOutcome"),
                        "output schema seam mismatch")
                self._payload_checks(output, binding, watermark_s, refs)
                if output.kind == "BoundaryOutcome":
                    require(output.data["status"] == result.status, "provider terminal status mismatch")
            # Validate state/trace before any output is exposed.
            for state in (result.next_state, result.trace):
                Record("Snapshot", {"state": state, "privileged_source_refs": sorted(refs),
                                    "state_schema_version": binding["state_schema_version"]})
            if stage == "action":
                commands = {Record.from_dict(m.data["payload"]).data["command_id"]:
                            Record.from_dict(m.data["payload"]).data for m in inputs
                            if m.data["payload"]["record_type"] == "ActionCommand"}
                for receipt in result.outputs:
                    if receipt.kind == "ActionReceipt":
                        require(receipt.data["command_id"] in commands, "receipt for unknown command")
                        require(receipt.data["idempotency_key"] == commands[receipt.data["command_id"]]["idempotency_key"],
                                "receipt idempotency mismatch")
        except Exception as exc:
            # A provider failure is evidence. I/O failures in _finish still propagate and quarantine.
            status = "timeout" if isinstance(exc, TimeoutError) else "rejected" if isinstance(exc, ContractError) else "error"
            result = ProviderResult((), prior.data["state"], {"exception_type": type(exc).__name__}, status,
                                    {"code": type(exc).__name__, "detail": str(exc) or type(exc).__name__})
        return self._finish(invocation_id, stage, binding, dataset_ids, result.outputs, prior,
                            result.next_state, base_context.data["random_state"], result.trace,
                            watermark_s, refs, result.status, result.reason)
