# Synthetic contract fixtures

`contracts-v1.json` contains generated payload examples, including unknown receipts,
censored populations and inconclusive assurance. All identifiers and settings are
synthetic. They originate in [`software/ecora/fixtures.py`](../../software/ecora/fixtures.py)
and use the repository's MIT licence. They contain no field data, private identifiers or
calibrated thresholds.

Regenerate using `python -m ecora fixtures --output data/fixtures/contracts-v1.json`.
The tests validate each record and detect stale exports; runtime tests also construct
hashed message, dataset and invocation examples. Fixtures establish contract behaviour,
not service performance. See the [package guide](../../software/README.md) for reproduction
and limits.
