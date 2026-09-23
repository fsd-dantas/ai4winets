"""The ns-3 model manifest: what the pinned build is, assembled and hashed as a record.

`software/simulator/build-ns3.sh` builds the declared release and dumps two things: every
registered type with the initial value of each attribute, and the facts of the build. This
module turns them into the manifest the simulator adapter must attach to every response.

The manifest carries two hashes, because two different questions get asked of it.

- `model_hash` covers what the model is: the release, the archive it came from, the whole
  attribute registry and the global values. Two builds of the same declaration on
  different hosts should agree on it; if they do not, the model is not the same model.
- `build_hash` covers that and the toolchain and host that produced it. It is what makes a
  response attributable to one build rather than to any build of the same release.

The registry is hashed whole, so a default changing anywhere changes `model_hash`. Only the
groups the v1 model draws on are written out in readable form, because a reviewer needs to
be able to find an RLC or HARQ setting without reading every registered type.
"""

import hashlib
import json
from pathlib import Path

from .contracts import canonical, digest, require

MANIFEST_VERSION = "ns3-model-manifest-v1"
SIMULATOR = Path(__file__).resolve().parents[1] / "simulator"
DECLARATION = SIMULATOR / "ns3-build.json"
MANIFEST = Path(__file__).resolve().parents[2] / "data" / "simulator" / "ns3-model-manifest.json"


def declaration():
    """The pinned build as declared: release, archive checksum, profile, modules."""
    return json.loads(DECLARATION.read_text(encoding="utf-8"))


def source_hashes(declared):
    """SHA-256 of each program source the build compiles into the pinned tree."""
    return {f"{program}.cc": hashlib.sha256(
                (SIMULATOR / "src" / f"{program}.cc").read_bytes()).hexdigest()
            for program in declared["programs"]}


def assemble(attributes, facts, declared=None):
    """Build the manifest from the registry dump and the build facts, or refuse."""
    declared = declared or declaration()
    require(facts["release"] == declared["release"],
            f"the build is {facts['release']}, the declaration pins {declared['release']}")
    require(facts["archive_sha256"] == declared["sha256"],
            "the build was made from an archive other than the pinned one")
    require(facts["build_profile"] == declared["build_profile"],
            f"the build profile is {facts['build_profile']}, not {declared['build_profile']}")
    require(facts["native_optimizations"] == "OFF",
            "host-specific code generation would tie the build to the CPU it ran on")
    types = attributes["types"]
    names = [t["name"] for t in types]
    require(len(set(names)) == len(names), "a type is registered twice in the dump")
    groups = {t["group"] for t in types}
    missing = [g for g in declared["manifest_groups"] if g not in groups]
    require(not missing, f"the dump registers no types in: {', '.join(missing)}")

    readable = {}
    for entry in sorted(types, key=lambda t: t["name"]):
        if entry["group"] not in declared["manifest_groups"]:
            continue
        readable[entry["name"]] = {a["name"]: a["value"] for a in entry["attributes"]}
    registry = {"types": len(types),
                "attributes": sum(len(t["attributes"]) for t in types),
                "digest": digest(attributes["types"])}
    global_values = {g["name"]: g["value"] for g in attributes["globals"]}
    model = {"release": declared["release"], "archive_sha256": declared["sha256"],
             "registry": registry, "globals": global_values}
    manifest = {"manifest_version": MANIFEST_VERSION, **model,
                "declaration_hash": digest(declared),
                "sources": source_hashes(declared),
                "build": facts, "attributes": readable,
                "model_hash": digest(model)}
    manifest["build_hash"] = digest({k: v for k, v in manifest.items() if k != "build_hash"})
    return manifest


def verify(manifest, declared=None):
    """Check a committed manifest against the current declaration and sources."""
    declared = declared or declaration()
    require(manifest["manifest_version"] == MANIFEST_VERSION, "unknown manifest version")
    require(manifest["declaration_hash"] == digest(declared),
            "the build declaration changed after this manifest was made; rebuild it")
    require(manifest["sources"] == source_hashes(declared),
            "a simulator source changed after this manifest was made; rebuild it")
    model = {k: manifest[k] for k in ("release", "archive_sha256", "registry", "globals")}
    require(manifest["model_hash"] == digest(model), "model_hash does not match its content")
    require(manifest["build_hash"] == digest(
        {k: v for k, v in manifest.items() if k != "build_hash"}),
        "build_hash does not match its content")
    return manifest


def write(manifest, path=MANIFEST):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Indented for review; the hashes are over canonical encoding, not these bytes.
    text = json.dumps(json.loads(canonical(manifest)), indent=1, sort_keys=True,
                      ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")
    return path


def load(path=MANIFEST):
    return json.loads(Path(path).read_text(encoding="utf-8"))
