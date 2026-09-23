# DPOP channel assignment: core demonstration

**Status: implemented and simulated on the declared logical model.** The deterministic
core is recorded here; the 960-run comparative study remains deferred. This is independent
research documentation originating in a learning exercise, not an institutional submission.

## Inspect the result

- [Curitiba channel assignment and DFS/UTIL/VALUE replay](results/core14-shared-curitiba-replay.html)
- [Mobile-cell snapshots, free versus stability-penalized](results/mobile-epochs.html)
- [Results and claim assessment](results/report.md)
- [Complete five-region transcript and derivation](results/trace-five.md)
- [Five-region replay](results/trace-five-replay.html)
- [Review of the revised design](design-review.md)

Questions: can locally informed agents obtain an independently verified four-coloring;
does its score match exact enumeration on small instances; what table/message burden does
the pseudo-tree induce; and what reassignment tradeoff appears when a mobile cell moves?
See the [study design](../../docs/dcop-channel-assignment/README.md),
[architecture](../../docs/dcop-channel-assignment/architecture.md) and
[simulation declaration](../../docs/dcop-channel-assignment/simulation-declaration.md).

## Scope and outcomes

The recorded matrix has four maps (12-region grid, 10-region hand-authored border graph,
14-municipality Curitiba core, 29-municipality metropolitan area), two score modes and two
roots: **16 runs**. Twelve complete with independently checked zero-conflict assignments;
four metropolitan runs stop at the declared table budget. There are **8 mobile epoch runs**
and **1 hand-checkable trace run**. All records retain assignments or explicit failure
outcomes, messages and resource counts. This is descriptive evidence, not a randomized
performance comparison. One deterministic run per declared configuration is used.

The mobile fixture has baseline, arrival, move and departure. A mobile rectangle partitions
a strip from its host's fixed region, never overlaps it, and is not penalized for changing
channels. Fixed scores are `(0,10,20,30)`; mobile scores `(0,100,100,100)` explicitly exercise
conflicting preferences. The same baseline starts both arms. Stability `s=101*N` prioritizes
retaining fixed-AP channels over base score. The sequence yields 25 versus 0 fixed-AP
changes; stable plans have base cost 160 during arrival/move versus 80 without the penalty.
This tradeoff is instance-specific, not a guarantee of lower cumulative reassignment.

The earlier all-zero-score fixture produced 0 changes in both arms. Its inputs and eight
run records are retained in [pilot-zero-score](pilot-zero-score/) as a zero-effect pilot,
excluded from the main matrix. The final fixture was deliberately designed after this
pilot to exercise the stability mechanism; no holdout or generalization claim is made.

## Reproduce from this directory alone

The recorded environment is Python 3.13 with the exact dependencies in
[requirements.txt](requirements.txt). `source.zip` contains the package source, focused
tests and geographic fixtures. It is a source snapshot, not a separate maintained fork.
All files are bound by `manifest.json`. `reproduction.json` records the isolated-environment
verification. The archive includes no local work boards or assistant configuration.

Every text file here uses LF line endings and git stores this directory's bytes unconverted, so
the manifest verifies on any checkout. Run records hash the package source with line endings
normalized, so a Windows and a Linux checkout regenerate identical records. After a change to
the package or its results, the maintainer runs `python reproduce.py --seal`, which rebuilds
`source.zip` from the repository and rewrites the manifest; it refuses CRLF text.

From this directory, in PowerShell:

```powershell
python reproduce.py --verify
python -m zipfile -e source.zip reproduced-source
python -m venv reproduced-env
.\reproduced-env\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONPATH = 'reproduced-source/software'
.\reproduced-env\Scripts\python.exe -m unittest discover -s reproduced-source/tests -p 'test_dcop*.py' -v
.\reproduced-env\Scripts\python.exe -m dcop_channel_assignment.demonstration --inputs configuration --output reproduced-results
python reproduce.py --compare reproduced-results
```

On Linux/macOS use `reproduced-env/bin/python` and `export PYTHONPATH=reproduced-source/software`.
Dependencies require access to their package index unless already cached. No map download,
radio hardware, ECoRA modules or external simulator is required. Host timings vary and are
excluded from equality comparisons; deterministic records, summaries and rendered artifacts
are compared. Resource limits are per-table entries, not process memory or wall time.

To regenerate figures only, without running DPOP:

```powershell
.\reproduced-env\Scripts\python.exe -m dcop_channel_assignment.demonstration --output results --render-only
```

## Presentation runbook

From the repository root with the map dependencies installed:

```powershell
$env:PYTHONPATH = 'software'
.\.venv\Scripts\python.exe -m dcop_channel_assignment --solve --output .ecora-runs/grid.json
.\.venv\Scripts\python.exe -m dcop_channel_assignment --solve --preferences --geojson data/geography/curitiba-metropolitan/central-core-14.geojson --root ap-4106902 --output .ecora-runs/core.json
.\.venv\Scripts\python.exe -m dcop_channel_assignment --solve --map experiments/001-dcop-channel-assignment/configuration/hand-map.json --output .ecora-runs/hand.json
.\.venv\Scripts\python.exe -m dcop_channel_assignment --solve --geojson data/geography/curitiba-metropolitan/metropolitan-29.geojson --root ap-4106902 --output .ecora-runs/limit.json
```

Expected: grid cost 0; core preference cost 140; hand-map cost 0; all three have evaluator
`feasible=true`. The metropolitan case returns `budget_exceeded`, no assignment and no
feasible objective. Every command prints the phase counts, complete assignment when
available, evaluator verdict and baseline conflicts. Add `--trace` to print all messages.
For indicative per-map elapsed seconds on the recorded host see
[host-timings.json](results/host-timings.json); these are presentation estimates, not benchmarks.

A new hand-authored file uses `id`, unique `regions`, and `borders` (pairs of region IDs).
Optional `scores` supplies four nonnegative integer scores per region. See the ten-region
example. Loops, duplicate/unknown borders, disconnection and nonplanarity are rejected.
This format declares a topological map; its drawing is a planar graph embedding, not
invented geographic polygons. Polygon maps continue to derive adjacency from shared segments.

## Evidence and limitations

The evaluator imports no solver code and recomputes completeness, domains, conflicts and
unary scores from resolved map inputs. Exact references enumerate only bounded small
instances; they are never available to agents. K5 infeasibility and its feasible
counterparts are covered by the archived tests. A full transcript explains the five-region
tables analytically and displays every actual protocol message.

All scores and AP identities are synthetic. Municipal geometry is public IBGE 2022 data,
with metropolitan membership from AMEP; [source attribution](../../data/geography/curitiba-metropolitan/README.md)
and a copy in `configuration/geographic-provenance.md` describe dates and access terms.
Software is covered by the repository MIT license, copied here as `LICENSE`; geographic
source material is attributed separately and is not relicensed as original software.

These results concern planar surrogate constraints and reliable logical messages. They
do not establish radio coverage, throughput, loss, SINR, airtime or service assurance.
Budget stops are a result of the tested configuration, not proof that another root or
implementation cannot solve the same graph. Changing topology during a solve, lossy
transport and incremental DCOP are outside scope.

Resource-count convention: `messages` and the legacy `transmitted_entries` field count successfully delivered messages and their UTIL cells. A budget-stop record describes its delivered prefix; messages queued but not delivered at interruption are not counted. The largest completed join and the first rejected requested join are recorded separately.
