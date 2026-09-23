# ns-3 build and model manifest

**Status: implemented build and manifest. The simulator program the adapter drives is not
built yet; this directory produces the pinned library and the record of what it is.**

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
