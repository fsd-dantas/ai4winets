# ns-3 build, model manifest and simulator process

**Status: implemented build, manifest, simulator process and Python adapter, answering
`configure`, `advance` and `cohorts`. `observe`, `apply`, `truth` and `fork` are refused
with a reason until their items land. No ns-3 value is calibrated.**

## Driving it from Python

`ecora.simulator.Ns3World.start(scenario)` starts the process, directly on Linux and
through `wsl.exe` on Windows (override with `ECORA_SIMULATOR`, or `ECORA_NS3_ROOT` for the
build's location). The adapter refuses any response whose build identity differs from the
committed manifest's, any response to a different request, and treats a closed output as a
crash rather than an answer. The simulator's refusals are raised with their codes.
`verify_simulated(world.resolved, scenario)` is acceptance 1 of the adapter contract. The
tests that need a real build skip, and say so, on a host without one.

## The simulator process

[src/ecora-sim/ecora-sim.cc](src/ecora-sim/ecora-sim.cc) builds one world from one scenario
and answers one request at a time on standard input and output. Each frame is a four-byte
big-endian length and that many bytes of JSON. It never writes anything else to standard
output and never initiates a message. Every response carries the build identity compiled
into it, which the manifest records and `ecora.ns3build` can recompute from the repository.

What `configure` builds, from the scenario alone:

| Element | ns-3 realisation |
| --- | --- |
| LTE leg | `LteHelper` with `PointToPointEpcHelper`, `PfFfMacScheduler`, `FriisSpectrumPropagationLossModel`, RLC UM set explicitly, RLC buffer from the leg's queue limit, radio parameters and positions from the scenario |
| LTE impairment | a `MatrixPropagationLossModel` on both spectrum channels, per site, 0 dB until a `radio_loss` disturbance sets it |
| Alternative leg | point-to-point, DropTail at the declared byte limit, `RateErrorModel` at both receivers; no queue disc |
| Egress | point-to-point, DropTail at the declared byte limit; no queue disc |
| SCADA | central request to the site over its selected leg, response after the processing delay over the leg selected then |
| AMI | readings at the site, released through the same pacing gate as the finite world |
| Identity | a 32-byte envelope on every datagram, plus a packet tag so a drop can be attributed |

The `configure` response reads settings back from the objects built rather than echoing the
request, so a setting ns-3 did not take shows up as a disagreement. Two findings from doing
so are recorded in the program: `LteHelper`'s `PathlossModel` is write-only, so the loss
models are read from the channels; and with an EPC attached, ns-3 silently changes its
`RLC_SM_ALWAYS` default to RLC UM, so the mode is set explicitly and reported.

A `cell_load` disturbance activates competing UEs built at `configure` for the largest load
any disturbance declares, at the loaded site's position, each saturating the uplink. Their
traffic goes to a background sink beside the EPC, so it contends for the radio and never for
the study's egress, and their drops are counted apart from the study's. The LTE leg is built
in one place, [src/ecora-sim/lte-leg.h](src/ecora-sim/lte-leg.h), shared with the
calibration program [src/ecora-calibrate/](src/ecora-calibrate/ecora-calibrate.cc), so what
is calibrated is the leg that runs. `python -m ecora calibrate-lte` measures it and
`--apply` writes the measured rate table into every scenario.

The `cohorts` response also carries `queues`: every device queue on the egress and the
alternative leg, instrumented per class from its own enqueue, dequeue and drop traces, with
occupancy over time. The LTE leg's queue is the RLC buffer inside the stack, which exposes
no such trace, and is reported as not instrumented. `python -m ecora bottleneck-pilot` uses
this to measure the shared egress in both worlds.

A rate disturbance of zero on the alternative leg is realised as a receive error rate of 1
at both ends, because a point-to-point device cannot run at zero. Drops are attributed from
point-to-point queue and PHY drops, IPv4 drops and LTE RLC drops. A datagram discarded where
its identity cannot be read is counted as untraced and attributed to nothing; one the UE
discards silently before attaching stays pending, not lost.

The [simulator adapter contract](../../system/simulator-adapter.md) runs ns-3 in a separate
process and requires every response to carry the hash of the model that produced it. This
directory is where that model comes from.

| File | Role |
| --- | --- |
| [ns3-build.json](ns3-build.json) | The declaration: release, archive URL and SHA-256, build profile, modules, configure flags, and which attribute groups the manifest writes out |
| [build-ns3.sh](build-ns3.sh) | Verifies the archive, extracts a tree of its own, configures, builds, and dumps the attribute registry and build facts |
| [src/ecora-attributes.cc](src/ecora-attributes.cc) | Exports every registered type with each attribute's initial value, and every global value |
| [../../data/simulator/ns3-model-manifest.json](../../data/simulator/ns3-model-manifest.json) | The committed manifest, assembled by `python -m ecora simulator-manifest` |

## Build

Linux or WSL2 with a C++ compiler, CMake, Ninja and Python 3:

```bash
software/simulator/build-ns3.sh            # root defaults to $ECORA_NS3_ROOT, then ~/ecora-ns3
```

Then, from any Python environment with the package installed:

```text
python -m ecora simulator-manifest --attributes <root>/out/ns3-attributes.json \
                                   --facts <root>/out/build-facts.json
```

The script refuses an archive whose checksum differs from the declared one, and a source
tree it did not extract itself: a tree edited by anything else is not evidence of what the
pinned release contains. The assembly refuses a build whose release, archive, profile or
code generation differs from the declaration.

## What the manifest establishes

`model_hash` covers the release, the archive checksum, the whole attribute registry and the
global values. `build_hash` covers that plus the toolchain and host. The registry is
hashed whole, so a default that changes anywhere changes `model_hash`; the readable section
lists only the groups the v1 model draws on, including the types ns-3 registers without a
group, among them `LteHelper` and `UeManager`.

A pointer-valued default is exported as the type it points to, not its address. The
address differed on every run of the exporter, which would have made a reproducible
manifest impossible; that was found by running it twice.

It does not establish that the selected components are configured as v1 declares. The
manifest records what a model inherits for anything a scenario does not set; the values a
scenario does set are resolved at `configure`, which belongs to the topology item.
