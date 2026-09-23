# Scenarios

Each file here declares one world. `ecora.scenario.build_world` reads it and constructs the
finite reference model; nothing about the world is supplied from code. Changing a condition
is an edit to a file, not a change to a module.

Every scenario in this directory is **synthetic**. No topology, identifier, rate or
condition here is taken from, derived from or calibrated against any real network.

## Why these are JSON and not YAML

A scenario is a frozen artifact. Its canonical bytes are hashed, and that hash is bound into
the provenance of every claim a run produces, so the parse has to be exact and stable: YAML's
implicit typing would let `rate_bps: 0` and a leg named `no` change meaning between parsers
and versions. YAML may later be added as an authoring convenience that compiles to canonical
JSON, but the artifact that is hashed stays JSON.

## What a scenario declares

| Field | Meaning |
| --- | --- |
| `topology.sites` | the sites that generate traffic |
| `topology.legs` | the access legs, each declaring its `kind` |
| `topology.egress` | the shared point-to-point egress both services contend for |
| `topology.initial_path` | the leg selected at the start of the run |
| `topology.initial_pacing` | the AMI release profile at the start of the run |
| `flows` | one flow per service class, each with a `pattern` |
| `requirements` | what the assurance stage scores the run against |
| `disturbances` | scheduled changes to a leg, each naming a declared site and leg and a `kind` |
| `initial_state.note` | a plain statement of the condition the scenario creates |

**Leg kinds.** A `point_to_point` leg declares its rate, propagation delay and queue limit.
An `lte` leg declares no rate, because in the simulator its capacity follows from the radio.
It declares radio parameters (bandwidth, EARFCNs, transmit powers, noise figures,
positions) and, under `logical`, how the finite world reads it: a capacity, a delay and a
table from extra path loss to rate. The simulator reports the logical block as not
applicable rather than using it.

**Disturbance kinds.** `rate` changes a point-to-point leg's rate. `radio_loss` adds path
loss in dB to one site's LTE link. `cell_load` brings competing UEs, each saturating the
uplink, onto the cell at the site's position; the count replaces the previous one, and it
is bounded at 35, the model's valid range. The LTE leg keeps both conditions, and the finite
world reads them together through the leg's `rate_table`: the largest declared load not
above the current one, then within it the largest declared loss not above the current one.
The table is measured in the simulator and cites its dataset under `calibration`
(ADR-29, ADR-30).

**What degrades an LTE leg.** Measured, path loss alone makes the leg fine or silent for
this workload, and load alone leaves a site plenty. A leg that still delivers but too
slowly needs a cell-edge site in a busy cell with demand near its share, which is what
S1, S3 and S4 declare.

**Flow patterns.** SCADA is `request_response`: the central application sends
`payload_bytes` down the site's selected leg, and the site answers with `response_bytes`
after `processing_delay_s`. The deadline covers the round trip, and the transaction is the
obligation. AMI is `periodic`: readings from the site.

A scenario naming a site, leg or path it does not declare is refused when it is read. So is
one the finite model cannot build — a missing service flow, an unknown pacing profile, or a
topology without both legs the model reasons over.

## The set

| File | Condition | Visible from |
| --- | --- | --- |
| `s0-nominal.json` | undisturbed baseline; both legs at nominal rate throughout | — |
| `s1-degraded-primary.json` | a cell-edge site with heavier AMI demand loses LTE share when the cell becomes busy; SCADA runs late, and the load stays | 1.0 s |
| `s2-silent-primary.json` | the serving leg stops carrying bytes entirely (radio loss past the cliff) | 1.0 s |
| `s3-transient-primary.json` | as S1, and the load leaves, so a controller can be observed reverting | 1.0 s, recovery at 5.0 s |
| `s4-no-alternative.json` | as S1 while the alternative carries nothing, leaving pacing as the only lever | 1.0 s |
| `s5-narrow-egress.json` | the shared egress is narrower than the offered load, so the services contend with no disturbance at all | ~4 s, as the queue builds |

**Visible from** is when the condition starts to show in delivery, and therefore how long a
run has to be for the scenario to mean anything. A run shorter than that observes the
nominal baseline under another scenario's name. `s3` needs a run past 5.0 s for the recovery
to be reached at all, and `s5` has no disturbance to fire: its queue builds under sustained
overload, so a short run sees nothing.

These are **declared conditions, not calibrated ones**. The rates were chosen by running the
model until each scenario produced the behaviour its note describes, and they carry no claim
about any real network. They are not yet the frozen screening set: that is B40's obligation,
and freezing one is a separate decision from publishing these.

## Running one

```
python -m ecora showcase .ecora-runs/showcase --scenario s1-degraded-primary
```

The argument is either an identifier matching a file in this directory or a path to a
scenario file anywhere. The run is refused if the model does not match the scenario it
claims to run under.
