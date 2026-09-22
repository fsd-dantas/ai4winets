# Studies

A scenario declares the world. A study declares what the system knows and decides with:
the rule inventory, the local view a projection relays, the planner and coordination
configuration, how a concluded diagnosis becomes symbolic predicates, and the assembled
stage inputs a run freezes. `ecora.study` reads one, and nothing here is written in Python.

```
python -m ecora showcase .ecora-runs/demo --scenario s1-degraded-primary --study arbitration
```

## Why these are separate from scenarios

The two vary independently and answer different questions. A scenario asks what the world
did; a study asks what the system knew and chose. Running one study across several
scenarios isolates conditions, and running several studies across one scenario isolates
knowledge. Keeping them in one file would make every pairing a new file.

## The freeze still binds

Goals, action costs, budgets and cohort windows are frozen with a study so that an arm
cannot be tuned after its results are seen. That property is what makes the arm
comparisons worth anything, and reading these from a file does not loosen it: a run binds
one study, the assembly still governs what may be assembled, and every binding's
configuration is hashed into the study manifest. Editing a study produces a different
content hash, so switching studies is an explicit act rather than a quiet edit to the one
being measured.

## The set

| File | What it demonstrates |
| --- | --- |
| `baseline.json` | the declared baseline every other study varies from |
| `arbitration.json` | rule conflict: one pair at equal authority, one resolved by priority |
| `multi-goal.json` | two goals over two fluents, so the planner sequences rather than picks |
| `contention.json` | two service agents with incompatible objectives over one resource |

Each of the three exists because the baseline **cannot** reach the mechanism it exercises.
That is not a criticism of the baseline; it is what made the gap invisible.

### `arbitration.json`

Every contradicting rule pair in the baseline has mutually exclusive conditions
(`ge 49152` against `lt 49152`, `eq alternative` against `eq lte`), so a conflict is
structurally unreachable and the arbitration the inventory declares can never run.
`Study.arbitrable()` reports which contradicting pairs can actually both hold, and for the
baseline it reports none.

This study adds two pairs that can. `degraded_primary` and `demand_outpacing` are
competing explanations for the same growing queue at **equal authority**: with only these
signals neither dominates, so both are recorded as unresolved. That is the correct answer,
not a failure — a system that picked one would be claiming a distinction its evidence does
not support. `prefer_alternative` and `prefer_primary` sit at **different authority**, so
the weaker conclusion is inhibited and the inhibition is recorded rather than silently
dropped.

### `multi-goal.json`

The baseline declares one goal over one fluent, so every plan is a single action and the
planner never has to sequence. Two goals over two fluents produce a two-step plan at cost
3. All three searches still agree, because no operator in this domain interacts with
another; that is a property of the domain, and it is why the interacting-goal
microbenchmark is still owed.

### `contention.json`

The baseline has one site and therefore one agent, so the coordination stage never sees
more than one proposal and has no conflict to resolve. This study declares two service
agents at one site with incompatible objectives: SCADA wants AMI throttled to the minimum
profile to protect its deadline, AMI wants only the restricted profile and also wants the
alternative leg. Both write `site-1/pacing_profile`, so that resource is genuinely
contended while `site-1/selected_path` is not.

Per-agent goals live in the planner's binding configuration, not in the assembly, and
every agent goal must be one the study froze. The assembly's `goals` is the inventory of
what any agent may pursue, not a conjunctive goal for one planner to achieve.

## What a study must declare

Every section is required, and a file carrying an unknown section is refused rather than
silently ignored — a misspelled section that was skipped would leave the default in place
while appearing to have changed it.

| Section | Holds |
| --- | --- |
| `projection` | the neighbourhood and expected signals the telemetry arm relays |
| `rules` | the rule inventory and its activation budget |
| `planner` | sites, action costs, agents, validity and search bounds |
| `eco` | coordination mechanism settings and the authority map |
| `predicate_map` | how a concluded hypothesis becomes symbolic predicates |
| `oracle` | what the telemetry and diagnosis Oracles are permitted to read |
| `nulls` | the declared Null policy settings, fixed before measurement |
| `assembly` | the frozen stage inputs: planning goals and budgets, result cohorts |

A study is refused when a rule identifier repeats, a rule contradicts a conclusion no rule
reaches, a goal is malformed or duplicated, or the predicate map names a label no rule
concludes. All of it is checked when the file is read, not part-way through a run.
