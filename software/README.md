# ECoRA contract foundation

**Status: implemented contract validation and audited provider boundary.** No network
simulator, research controller, certified Oracle or closed-loop replay is implemented.
The included providers are synthetic test fixtures, not experimental decision methods.

This package implements the [normative interfaces](../system/interfaces.md) for RQ0's
controlled stage comparisons. Providers change through frozen configuration; serialization,
provenance and permission checks stay outside provider code.

## Install and validate

Python 3.11 or newer is required. From the repository root, on Windows:

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e .
./.venv/Scripts/python.exe -m unittest discover -s tests -v
./.venv/Scripts/python.exe -m ecora demo .ecora-runs/example
./.venv/Scripts/python.exe -m ecora verify .ecora-runs/example/reference
```

On Linux/macOS, use `.venv/bin/python` in place of `.venv/Scripts/python.exe`. An activated
environment can use `python` directly. `make test` is an optional equivalent when Make is
installed. The demo requires fresh output directories and refuses to overwrite a prior run.
Its different diagnosis labels demonstrate binding substitution, not diagnostic accuracy.

For offline source-tree testing when the declared dependency is already installed, set
`PYTHONPATH=software` and run `python -m unittest discover -s tests -v`.

## Code and contracts

| Component | Implemented responsibility |
| --- | --- |
| [schema.py](ecora/schema.py) | Draft 2020-12 schemas for manifests, all stage payloads, messages, datasets, invocation records and state/context records |
| [contracts.py](ecora/contracts.py) | Immutable records, finite canonical JSON, content hashes, schema versions, units, time ordering, action scope and population conservation |
| [registry.py](ecora/registry.py) | Versioned provider identity, fixed input/output seams, capability requirements and complete frozen-study admission |
| [boundary.py](ecora/boundary.py) | Persist-before-invoke wrapper, lineage/privilege propagation, typed failures and dispatch intents |
| [store.py](ecora/store.py) | Exclusive writer, immutable content-addressed objects, hash-chained JSONL journal, delivery deduplication and integrity checks |
| [fixtures.py](ecora/fixtures.py) | Synthetic fixture manifests, payloads and provider substitutes |

The exported [JSON Schema](../data/schemas/ecora-v1.schema.json) defines structural types.
The Python validator additionally enforces hashes, cross-field inequalities, units,
capability relationships and population accounting; JSON Schema validation alone is not
full ECoRA admission. Both checks are needed. Unknown versions and undeclared record
fields fail validation. Explicit configuration, state, trace and initial-state
objects are JSON extension points, not executable callbacks. Topology and disturbances are
not among them: they carry declared shape, and
[`ecora.scenario`](ecora/scenario.py) builds the finite world from them, so a scenario is the
source of the world a run observes rather than a description beside it.

Generate the schema and fixtures without shell-dependent output encoding:

```text
python -m ecora schema --output data/schemas/ecora-v1.schema.json
python -m ecora fixtures --output data/fixtures/contracts-v1.json
python -m ecora validate path/to/a-record.json
```

The tests check that exported artifacts match their source definitions. The fixture array
contains payload examples; runtime tests generate and round-trip their message/dataset/
invocation envelopes with real hashes. All fixture names and values are synthetic and
uncalibrated, with no real network identifiers or external data.

The [validation record](validation.md) states the exercised platform, dependency versions,
commands and observed results.

## Serialization and provenance

`Record(kind, data)` validates and retains immutable canonical bytes; data access returns
a detached copy. `ecora-json-v1` uses UTF-8, sorted string keys, compact separators, finite
JSON-native numbers, and no Unicode normalization. It rejects duplicate JSON keys,
non-string map keys, nonfinite values and Python-only objects. Integer `1` and float `1.0`
retain their different encodings. This is a versioned Python encoding, not RFC 8785 or
a promise that arbitrary external JSON serializers produce identical bytes.

SHA-256 covers the canonical `{record_type, schema_version, data}` object. The digest
is stored in the outer `content_hash`. Nested messages retain their own validated payload
record. Dataset IDs identify a producing invocation; their separate content hash addresses
the immutable manifest, avoiding a cyclic message/dataset hash definition.

Each admitted run fixes its study, scenario-set/member, capability manifest and treatment.
Every output names its invocation, consumed datasets and parent messages. State, context,
random-state and trace records are persisted with hashes. No simulator pointer or callable
is allowed in serialized inputs. Scenario disturbance definitions remain in administrative
artifacts and are not passed to providers through context.

The journal records admission, input persistence, invocation start, output persistence,
dispatch intents, delivery claims/acknowledgements and integrity failures. Empty providers
emit an explicit `BoundaryOutcome`; no-op, rejection, error and timeout remain terminal
evidence. Invalid output/state becomes a rejected outcome; a thrown `TimeoutError` becomes
timeout evidence. The wrapper does not interrupt an uncooperative provider on a host deadline.

## Information and effect boundaries

Observation capability IDs resolve to exact subject, service, metric, unit and source kind.
Inputs must already be available at the invocation watermark. Direct truth capability is
Oracle-only. A separately enabled `allow_privileged_inputs` permits an ordinary downstream
method to consume already privileged evidence within its declared observation scope; it
does not grant direct truth queries. The wrapper propagates all input and prior-state
privilege references to outputs, state and reports, including failed invocations.

The initial wrapper has no callable TruthPort. Oracle bindings requiring it are rejected
unless current-truth evidence has explicitly entered through trusted, logged adapter ingress.
Implementing the simulator truth interface and reference methods remains later work.

`ArtifactStore.deliver` durably claims a message before calling its consumer and suppresses
completed duplicate deliveries for that stable consumer ID, including after restart. If
the consumer fails after its claim, another callback is refused pending reconciliation.
The action-stage wrapper similarly records a dispatch intent and refuses repeated command
idempotency keys, even under a new invocation ID. It does not claim transactional exactly-once
effects across an external simulator. State-dependent precondition checks, application
verification, receipts and reconciliation require the eventual actuator adapter.

Providers are trusted in-process Python plugins. Serialized APIs restrict normal data flow
but cannot sandbox arbitrary Python, prevent a malicious plugin's filesystem access, or
prove its knowledge inventory. M1 enforces contract admission, not process isolation.

## Persistence limits and verification

One writer owns an artifact directory. Use separate directories for concurrent runs.
Writes are exclusive for objects and flushed/fsynced for the journal. An incomplete
journal line, corrupt object, broken lineage or unfinished invocation causes reopening to
fail. A crashed process can leave `writer.lock`; inspect the lock and journal before any
manual cleanup. Automatic repair, reconciliation and replay are not implemented here.

Hashes detect corruption relative to the retained records. They are not signatures,
tamper-proof storage or externally anchored protection against removing an entire journal
suffix. The implementation has not been validated against power loss on every filesystem.
Verification opens an existing store under its writer lock and checks addressed artifacts.

Tests cover round trips, immutable copies, required fields, malformed/unknown versions,
nonfinite values, units and temporal ordering, frozen membership, capability scope,
terminal outcomes, duplicate invocation/delivery/dispatch, inherited privilege and state,
cross-run rejection, corrupt/truncated artifacts and write failures. The reference-world
simulation, state restoration, causal replay and study-specific providers remain M2 or later.

Dependency/API references: [jsonschema validation](https://python-jsonschema.readthedocs.io/en/stable/validate/)
and [Python packaging metadata](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/).
