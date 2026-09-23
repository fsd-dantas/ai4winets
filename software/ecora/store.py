"""Immutable objects and an fsynced, hash-chained single-writer JSONL journal."""

from pathlib import Path
import os

from .contracts import ContractError, Record, canonical, decode, digest, require


class ArtifactStore:
    """One journal writer at a time. An interrupted invocation is quarantined on reopen.

    This is corruption detection and a cooperative writer lock, not tamper-proof storage.
    A process crash leaves the lock file; an operator must inspect it before removing it.
    """

    def __init__(self, root, *, cache_records=8192):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.objects = self.root / "objects"
        self.objects.mkdir(exist_ok=True)
        # A record is content-addressed and immutable, so a hash identifies one validated
        # record for the life of the process. Revalidating it on every read dominated run
        # time. Eviction is least-recently-used and costs only a re-read.
        self._records = {}
        self._cache_records = cache_records
        self._lock_path = self.root / "writer.lock"
        try:
            self._lock_fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise ContractError("artifact store has a writer lock; inspect interrupted work before reopening") from exc
        self._closed = False
        self._poisoned = False
        self._events = []
        self._datasets = {}
        self._messages = {}
        self._invocations = {}
        self._states = {}
        self._sequences = {}
        self._delivered = set()
        self._claims = {}
        self._runs = {}
        self._recorded_inputs = {}
        self._delivery_sequences = {}
        self._dispatches = {}
        try:
            journal = self.root / "journal.jsonl"
            if journal.exists():
                raw = journal.read_bytes()
                require(not raw or raw.endswith(b"\n"), "truncated journal; store is quarantined")
                for line in raw.splitlines():
                    event = decode(line)
                    self._verify_event(event)
                    self._apply(event)
                    self._events.append(event)
                require(not any(state in {"InputRecorded", "Started"} for state in self._states.values()),
                        "unfinished invocation; reconcile or quarantine this run before resuming")
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        if not self._closed:
            os.close(self._lock_fd)
            self._lock_path.unlink()
            self._closed = True

    def put(self, record):
        require(not self._closed and not self._poisoned, "store is closed or quarantined")
        require(isinstance(record, Record), "store accepts validated Records only")
        path = self.objects / f"{record.content_hash}.json"
        try:
            with path.open("xb") as stream:
                stream.write(record.to_json())
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            require(path.read_bytes() == record.to_json(), "immutable object was modified")
        except OSError:
            self._poisoned = True
            raise
        self._remember(record.content_hash, record)
        return record.content_hash

    def get(self, content_hash, *, cached=True):
        require(type(content_hash) is str and len(content_hash) == 64
                and all(c in "0123456789abcdef" for c in content_hash), "invalid object hash")
        path = self.objects / f"{content_hash}.json"
        if cached:
            hit = self._records.pop(content_hash, None)
            if hit is not None:
                # Identity cannot change, so the record is not revalidated. Its file must
                # still be there: removing evidence must not pass unnoticed on a read.
                require(path.exists(), f"missing object: {content_hash}")
                self._records[content_hash] = hit
                return hit
        try:
            record = Record.from_json(path.read_bytes())
        except OSError as exc:
            raise ContractError(f"missing object: {content_hash}") from exc
        require(record.content_hash == content_hash, "object address/hash mismatch")
        self._remember(content_hash, record)
        return record

    def _remember(self, content_hash, record):
        if content_hash not in self._records and len(self._records) >= self._cache_records:
            self._records.pop(next(iter(self._records)))
        self._records[content_hash] = record

    def _verify_event(self, event):
        require(type(event) is dict and set(event) == {"sequence", "previous_hash", "event", "data", "content_hash"},
                "invalid journal event")
        require(event["sequence"] == len(self._events), "journal sequence gap")
        previous = self._events[-1]["content_hash"] if self._events else None
        require(event["previous_hash"] == previous, "journal hash-chain gap")
        require(event["content_hash"] == digest({k: v for k, v in event.items() if k != "content_hash"}),
                "journal integrity failure")

    def append(self, event_type, data):
        require(not self._closed and not self._poisoned, "store is closed or quarantined")
        core = {"sequence": len(self._events),
                "previous_hash": self._events[-1]["content_hash"] if self._events else None,
                "event": event_type, "data": data}
        event = {**core, "content_hash": digest(core)}
        self._verify_event(event)
        # Validate before persisting; state is updated only after a durable append.
        self._apply(event, validate_only=True)
        try:
            with (self.root / "journal.jsonl").open("ab") as stream:
                stream.write(canonical(event) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
        except OSError:
            self._poisoned = True
            raise
        self._apply(event)
        self._events.append(event)

    def _apply(self, event, validate_only=False):
        typ, data = event["event"], event["data"]
        if typ == "RunAdmitted":
            run_id = data["scope"]["run_id"]
            require(run_id not in self._runs, "run identity already admitted")
            records = [self.get(h) for h in data["record_hashes"]]
            require([r.kind for r in records] == ["StudyManifest", "ScenarioSetManifest", "ScenarioSpec", "CapabilityManifest"],
                    "run admission artifact types mismatch")
            study, scenario_set, scenario, caps = records
            require(study.data["scenario_set_hash"] == scenario_set.content_hash
                    and study.data["capability_manifest_hash"] == caps.content_hash,
                    "run admission hashes mismatch")
            require(data["scope"]["study_id"] == study.data["study_id"]
                    and data["scope"]["scenario_set_hash"] == scenario_set.content_hash
                    and data["scope"]["scenario_hash"] == scenario.content_hash, "run scope mismatch")
            if not validate_only:
                self._runs[run_id] = data
        elif typ in {"InputRecorded", "Started"}:
            invocation_id = data["invocation_id"]
            expected = None if typ == "InputRecorded" else "InputRecorded"
            require(self._states.get(invocation_id) == expected, "invalid invocation lifecycle transition")
            if typ == "InputRecorded":
                for content_hash in data["record_hashes"]:
                    self.get(content_hash)
                for dataset_id in data["input_dataset_ids"]:
                    self.dataset(dataset_id)
            if not validate_only:
                self._states[invocation_id] = typ
                if typ == "InputRecorded":
                    self._recorded_inputs[invocation_id] = data
        elif typ == "OutputRecorded":
            invocation = self.get(data["invocation_hash"])
            dataset = self.get(data["dataset_hash"])
            require(invocation.kind == "StageInvocation" and dataset.kind == "DatasetArtifact", "invalid output artifact kinds")
            inv, ds = invocation.data, dataset.data
            run_data = self._runs.get(inv["scope"]["run_id"])
            require(run_data is not None and run_data["scope"] == inv["scope"], "output run not admitted")
            require(self._states.get(inv["invocation_id"]) == "Started", "output has no started invocation")
            input_record = self._recorded_inputs[inv["invocation_id"]]
            require(inv["input_dataset_ids"] == input_record["input_dataset_ids"], "invocation changed recorded inputs")
            require(inv["prior_state_hash"] in input_record["record_hashes"], "prior state was not recorded before invocation")
            require(ds["stage_invocation_id"] == inv["invocation_id"]
                    and ds["dataset_id"] == inv["output_dataset_id"], "invocation/dataset mismatch")
            for key in ("scope", "stage_id", "provider_id", "provider_version", "arm", "configuration_hash",
                        "information_regime", "privileged_source_refs"):
                require(ds[key] == inv[key], f"dataset/invocation mismatch: {key}")
            require(ds["source_dataset_ids"] == inv["input_dataset_ids"], "input lineage mismatch")
            require(ds["terminal_status"] == inv["status"] and ds["reason"] == inv["reason"], "terminal outcome mismatch")
            require(ds["dataset_id"] not in self._datasets, "dataset ID already owned")
            inherited = set()
            parents = set()
            for dataset_id in ds["source_dataset_ids"]:
                source = self.dataset(dataset_id).data
                require(source["scope"] == ds["scope"], "cross-run dataset lineage")
                inherited.update(source["privileged_source_refs"])
                parents.update(source["message_ids"])
            require(inherited <= set(ds["privileged_source_refs"]), "dataset sheds inherited privilege")
            context = self.get(inv["context_hash"])
            require(context.kind == "ProviderContext" and context.data["privileged_source_refs"] == ds["privileged_source_refs"],
                    "invocation context privilege mismatch")
            for key in ("prior_state_hash", "next_state_hash", "random_state_hash", "trace_hash"):
                snapshot = self.get(inv[key])
                require(snapshot.kind == "Snapshot", "invocation snapshot has wrong type")
                require(set(snapshot.data["privileged_source_refs"]) <= set(ds["privileged_source_refs"]),
                        "snapshot privilege not propagated")
            messages = [self.get(h) for h in ds["message_hashes"]]
            sequence_updates = dict(self._sequences)
            for expected_id, message in zip(ds["message_ids"], messages):
                require(message.kind == "Message", "dataset includes a non-message")
                m = message.data
                require(m["message_id"] == expected_id and expected_id not in self._messages, "duplicate or mismatched message ID")
                require(m["scope"] == ds["scope"] and m["output_dataset_id"] == ds["dataset_id"], "message dataset ownership mismatch")
                require(m["stage_invocation_id"] == inv["invocation_id"] and m["source_stage"] == ds["stage_id"], "message producer mismatch")
                for field in ("provider_id", "provider_version", "arm", "configuration_hash"):
                    require(m[field] == ds[field], f"message producer mismatch: {field}")
                require(m["input_dataset_ids"] == ds["source_dataset_ids"] and set(m["parent_message_ids"]) == parents,
                        "message causal parents differ from consumed dataset messages")
                require(m["privileged_source_refs"] == ds["privileged_source_refs"]
                        and m["information_regime"] == ds["information_regime"], "message sheds privilege")
                key = (m["scope"]["run_id"], m["source_stage"], m["destination_stage"])
                require(m["sequence_number"] == sequence_updates.get(key, 0), "message sequence gap or out-of-order output")
                sequence_updates[key] = m["sequence_number"] + 1
            if not validate_only:
                self._datasets[ds["dataset_id"]] = dataset.content_hash
                self._invocations[inv["invocation_id"]] = invocation.content_hash
                self._messages.update({m.data["message_id"]: m.content_hash for m in messages})
                self._sequences = sequence_updates
                self._states[inv["invocation_id"]] = "OutputRecorded"
        elif typ == "DispatchIntent":
            require(self._states.get(data["invocation_id"]) == "Started", "dispatch requires started invocation")
            require(data["run_id"] in self._runs, "dispatch run not admitted")
            keys = []
            for content_hash in data["command_hashes"]:
                command = self.get(content_hash)
                require(command.kind == "ActionCommand", "dispatch intent needs a command")
                key = (data["run_id"], command.data["idempotency_key"])
                require(key not in self._dispatches and key not in keys,
                        "command idempotency key already claimed; reconcile rather than redispatch")
                keys.append(key)
            if not validate_only:
                self._dispatches.update({key: data["invocation_id"] for key in keys})
        elif typ in {"DeliveryClaimed", "Delivered"}:
            message_id, consumer = data["message_id"], data["consumer_id"]
            require(message_id in self._messages, "delivery of unknown message")
            key = (consumer, message_id)
            m = self.get(self._messages[message_id]).data
            stream_key = (consumer, m["scope"]["run_id"], m["source_stage"], m["destination_stage"])
            if typ == "DeliveryClaimed":
                require(key not in self._claims, "duplicate delivery claim")
                require(m["sequence_number"] == self._delivery_sequences.get(stream_key, 0), "out-of-order delivery")
                if not validate_only:
                    self._claims[key] = True
            else:
                require(key in self._claims and key not in self._delivered, "invalid delivery acknowledgement")
                if not validate_only:
                    self._delivered.add(key)
                    self._delivery_sequences[stream_key] = m["sequence_number"] + 1
                    ds = self.dataset(m["output_dataset_id"]).data
                    # Delivered means one consumer received the whole dataset. Pooling across
                    # consumers would mark it complete when no single consumer holds it all.
                    if all((consumer, mid) in self._delivered for mid in ds["message_ids"]):
                        self._states[m["stage_invocation_id"]] = "Delivered"
        elif typ == "IntegrityFailure":
            require(bool(data.get("reason")), "integrity failure needs reason")
        else:
            raise ContractError(f"unknown journal event: {typ}")

    def dataset(self, dataset_id, _seen=None):
        require(dataset_id in self._datasets, f"unresolved dataset: {dataset_id}")
        record = self.get(self._datasets[dataset_id])
        seen = set() if _seen is None else _seen
        if dataset_id in seen:
            return record
        seen.add(dataset_id)
        data = record.data
        invocation = self.get(self._invocations[data["stage_invocation_id"]])
        for key in ("prior_state_hash", "next_state_hash", "random_state_hash", "trace_hash", "context_hash"):
            self.get(invocation.data[key])
        for content_hash in self._runs[data["scope"]["run_id"]]["record_hashes"]:
            self.get(content_hash)
        for content_hash in data["message_hashes"]:
            self.get(content_hash)
        for parent in data["source_dataset_ids"]:
            self.dataset(parent, seen)
        return record

    def register_run(self, scope, treatment_id, record_hashes):
        data = {"scope": scope, "treatment_id": treatment_id, "record_hashes": record_hashes}
        if scope["run_id"] in self._runs:
            require(self._runs[scope["run_id"]] == data, "run identity cannot change study or treatment")
        else:
            self.append("RunAdmitted", data)

    def dataset_ids(self):
        """Every dataset this store holds, in a stable order."""
        return sorted(self._datasets)

    def messages(self, dataset_id):
        return tuple(self.get(h) for h in self.dataset(dataset_id).data["message_hashes"])

    def invocation(self, invocation_id):
        require(invocation_id in self._invocations, f"unresolved invocation: {invocation_id}")
        return self.get(self._invocations[invocation_id])

    def head(self):
        """Hash of the last journal event: a run's reproducibility fingerprint."""
        return self._events[-1]["content_hash"] if self._events else None

    def next_sequence(self, run_id, source, destination):
        return self._sequences.get((run_id, source, destination), 0)

    def verify(self):
        """Re-read and revalidate every addressed artifact from disk.

        This is the integrity audit, and the only place that re-reads what the cache
        already holds. An ordinary read checks that an object is still present but does
        not revalidate it; a file whose contents changed underneath the process is caught
        here, or when the store is reopened.
        """
        for path in self.objects.glob("*.json"):
            self.get(path.stem, cached=False)
        for content_hash in (*self._datasets.values(), *self._messages.values(), *self._invocations.values()):
            self.get(content_hash, cached=False)
        return {"events": len(self._events), "datasets": len(self._datasets), "messages": len(self._messages)}

    def deliver(self, message, consumer_id, consumer, *, destination, watermark_s,
                allow_privileged=False):
        """At most one callback attempt per durable claim; unknown effects need reconciliation.

        An arbitrary external effect cannot be made transactionally exactly-once here.
        An interrupted claimed delivery is refused, not blindly retried.
        """
        require(message.kind == "Message", "delivery requires a Message")
        m = message.data
        require(self._messages.get(m["message_id"]) == message.content_hash, "unregistered or changed message")
        self.get(message.content_hash)
        require(m["destination_stage"] == destination, "wrong consumer destination")
        require(m["available_at_s"] <= watermark_s, "message not yet available")
        require(not m["privileged_source_refs"] or allow_privileged, "consumer lacks privilege permission")
        key = (consumer_id, m["message_id"])
        if key in self._delivered:
            return False
        require(key not in self._claims, "delivery outcome unknown; reconcile before retry")
        self.append("DeliveryClaimed", {"message_id": m["message_id"], "consumer_id": consumer_id})
        consumer(message)
        self.append("Delivered", {"message_id": m["message_id"], "consumer_id": consumer_id})
        return True
