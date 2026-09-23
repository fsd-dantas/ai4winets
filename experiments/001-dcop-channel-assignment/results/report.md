# Core demonstration results

Deterministic software evidence on declared maps. Synthetic scores; no radio-performance claim.
All successful assignments are independently evaluated. Budget stops have no assignment or reported conflict rate.

| Run | Outcome | Cost | Conflicts | Baseline conflicts | Separator | Max joined entries | UTIL entries transmitted | DFS / UTIL / VALUE |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| grid12-zero-lowest | optimal_cost | 0 | 0 | 17 | 4 | 1024 | 1700 | 34 / 11 / 11 |
| grid12-zero-highest | optimal_cost | 0 | 0 | 17 | 5 | 4096 | 3812 | 34 / 11 / 11 |
| grid12-shared-lowest | optimal_cost | 60 | 0 | 17 | 4 | 1024 | 1700 | 34 / 11 / 11 |
| grid12-shared-highest | optimal_cost | 60 | 0 | 17 | 5 | 4096 | 3812 | 34 / 11 / 11 |
| hand10-zero-lowest | optimal_cost | 0 | 0 | 14 | 2 | 64 | 132 | 28 / 9 / 9 |
| hand10-zero-highest | optimal_cost | 0 | 0 | 14 | 3 | 256 | 468 | 28 / 9 / 9 |
| hand10-shared-lowest | optimal_cost | 60 | 0 | 14 | 2 | 64 | 132 | 28 / 9 / 9 |
| hand10-shared-highest | optimal_cost | 60 | 0 | 14 | 3 | 256 | 468 | 28 / 9 / 9 |
| core14-zero-lowest | optimal_cost | 0 | 0 | 29 | 5 | 4096 | 3028 | 58 / 13 / 13 |
| core14-zero-curitiba | optimal_cost | 0 | 0 | 29 | 6 | 16384 | 8404 | 58 / 13 / 13 |
| core14-shared-lowest | optimal_cost | 140 | 0 | 29 | 5 | 4096 | 3028 | 58 / 13 / 13 |
| core14-shared-curitiba | optimal_cost | 140 | 0 | 29 | 6 | 16384 | 8404 | 58 / 13 / 13 |
| metro29-zero-lowest | budget_exceeded | None | None | 66 | 11 | 65536 | 38404 | 132 / 10 / 0 |
| metro29-zero-curitiba | budget_exceeded | None | None | 66 | 10 | 65536 | 52228 | 132 / 16 / 0 |
| metro29-shared-lowest | budget_exceeded | None | None | 66 | 11 | 65536 | 38404 | 132 / 10 / 0 |
| metro29-shared-curitiba | budget_exceeded | None | None | 66 | 10 | 65536 | 52228 | 132 / 16 / 0 |

## Mobile-cell snapshots

Both arms start from the same baseline plan. Penalties apply to surviving fixed APs only.
The mobile region is excluded even when it persists across epochs. No movement occurs during a solve.

| Arm | Epoch | Fixed reassignments | Base cost | Penalized objective | Conflicts |
| --- | --- | --- | --- | --- | --- |
| free | baseline | 0 | 60 | 60 | 0 |
| free | arrival | 1 | 80 | 80 | 0 |
| free | move | 12 | 80 | 80 | 0 |
| free | departure | 12 | 60 | 60 | 0 |
| stable | baseline | 0 | 60 | 60 | 0 |
| stable | arrival | 0 | 160 | 160 | 0 |
| stable | move | 0 | 160 | 160 | 0 |
| stable | departure | 0 | 60 | 60 | 0 |

Total fixed-AP reassignments: free=25, stability-penalized=0. This comparison is specific to this sequence.
A dominant penalty minimizes changes relative to each arm's own previous valid plan; it does not guarantee fewer cumulative changes for every possible sequence.

## Claim assessment

- C1: supported for completed demonstration solves; entry-budget stops are explicitly excluded from completeness.
- C2: exact optimality is tested on bounded small instances; enumeration is not used to solve the larger maps.
- C3: independent cheapest-channel choices conflict on these inputs; their local score is not a feasible objective.
- C4: counts and table sizes describe this implementation, including its materialized joins, under the declared roots.
- C5: the table above reports the observed stability effect without assuming strict improvement.

## Limits

The 29-region map exceeds the tested 1,000,000-entry budget. This does not prove that no root, representation or larger budget can solve it.
There is no timing-performance claim. host-timings.json supplies one-host demonstration estimates only.
No throughput, latency, SINR, loss, security, or fault-tolerance conclusions follow. The 960-run comparative study is deferred.
