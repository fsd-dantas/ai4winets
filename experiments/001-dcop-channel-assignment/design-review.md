# Review of design revision 0.3

Accepted direction: complete a verifiable descriptive demonstration and mobile-cell
snapshots; defer the factorial comparative study. The existing VALUE implementation was
retained and verified rather than replaced.

Corrections incorporated into revision 0.4:

1. Four-color feasibility does not imply completion under a finite table budget. C1 applies
   to completed feasible solves; interrupted runs remain visible with no assignment.
2. The 29-region map exceeds the tested budget under two roots. It has not been proven
   impractical for every root, representation or larger budget. The recorded largest
   successfully allocated join is distinct from the rejected requested allocation.
3. A persistent mobile cell can have a previous channel. Its exclusion from the penalty is
   an explicit modeling decision. Fixed-AP changes and all-survivor changes are separate metrics.
4. A dominant penalty minimizes fixed-AP changes relative to that arm's previous plan.
   It need not beat another arm's cumulative change count over every possible sequence.
   The report states the measured effect and the base-score tradeoff for the declared case.
5. Hand-authored shared-border graphs are a separate admission path. Their planar embedding
   is not a reconstructed administrative map; polygon inputs still derive edges geometrically.
6. Independent evaluation reduces shared-bug risk, but does not prove the evaluator infallible.
   Corrupted assignments, reference checks and explicit invariants are retained as evidence.
7. DFS skips ancestor neighbors on its current path. SEEN is returned when a completed
   descendant is subsequently probed by an ancestor; the protocol description now matches code.

No new optimization algorithm, radio model, LLM, ontology engine or distributed-service
framework was introduced. The declared DDD ownership boundaries remain intact.
