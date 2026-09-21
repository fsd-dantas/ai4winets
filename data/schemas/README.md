# Executable contract schemas

`ecora-v1.schema.json` is the generated Draft 2020-12 structural schema for ECoRA records.
Its source is [`software/ecora/schema.py`](../../software/ecora/schema.py). Hash and
cross-record/semantic checks additionally require the Python contract validator and
admission boundary; a structural schema pass alone is insufficient.

Regenerate with `python -m ecora schema --output data/schemas/ecora-v1.schema.json` from
an installed checkout. The test suite detects stale exports. This is a schema artifact,
not a network model or an experimental result.
