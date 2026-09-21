"""Versioned provider lookup and admission against frozen study artifacts."""

from dataclasses import dataclass
from typing import Protocol

from .contracts import Record, digest, require
from .schema import INPUT_TYPES, OUTPUT_TYPES, STAGES


class Provider(Protocol):
    def invoke(self, input_messages: tuple[Record, ...], prior_state: Record,
               context: Record) -> "ProviderResult": ...


@dataclass(frozen=True)
class ProviderResult:
    outputs: tuple[Record, ...]
    next_state: dict
    trace: dict
    status: str = "ok"
    reason: dict | None = None


@dataclass(frozen=True)
class Entry:
    spec: Record
    factory: object


@dataclass(frozen=True)
class AdmittedRun:
    study: Record
    scenario_set: Record
    scenario: Record
    capabilities: Record
    treatment_id: str
    run_id: str

    @property
    def scope(self):
        s = self.scenario.data
        return {"study_id": self.study.data["study_id"],
                "scenario_set_version": self.scenario_set.data["version"],
                "scenario_set_hash": self.scenario_set.content_hash,
                "scenario_id": s["scenario_id"], "scenario_revision": s["revision"],
                "scenario_hash": self.scenario.content_hash, "run_id": self.run_id}

    def binding(self, stage):
        treatment = next(t for t in self.study.data["treatments"] if t["treatment_id"] == self.treatment_id)
        return next(b for b in treatment["bindings"] if b["stage_id"] == stage)

    def capability(self, capability_id):
        values = [c for c in self.capabilities.data["capabilities"] if c["capability_id"] == capability_id]
        require(len(values) == 1, f"unavailable capability: {capability_id}")
        return values[0]


class Registry:
    def __init__(self):
        self._entries = {}

    @staticmethod
    def key(data):
        return data["stage_id"], data["provider_id"], data["provider_version"]

    def registered(self, stage_id, provider_id, provider_version):
        return (stage_id, provider_id, provider_version) in self._entries

    def register(self, spec: Record, factory):
        require(spec.kind == "ProviderSpec", "registry needs a ProviderSpec")
        d = spec.data
        require(set(d["input_types"]) == set(INPUT_TYPES[d["stage_id"]]), "provider input seam mismatch")
        require(set(d["output_types"]) == set(OUTPUT_TYPES[d["stage_id"]]), "provider output seam mismatch")
        require(self.key(d) not in self._entries, "provider version already registered")
        require(callable(factory), "provider factory must be callable")
        self._entries[self.key(d)] = Entry(spec, factory)

    def resolve(self, binding):
        key = self.key(binding)
        require(key in self._entries, f"unresolved provider: {key}")
        entry = self._entries[key]
        spec = entry.spec.data
        for field in ("arm", "input_types", "output_types", "state_schema_version", "capability_ids"):
            require(binding[field] == spec[field], f"binding/spec mismatch: {field}")
        require(binding["configuration_hash"] == digest(binding["configuration"]), "configuration hash mismatch")
        require((binding["information_regime"] == "oracle_state") == spec["direct_truth_access"],
                "binding truth permissions differ from provider")
        return entry

    def admit(self, study, scenario_set, scenario, capabilities, treatment_id, run_id):
        for record, kind in ((study, "StudyManifest"), (scenario_set, "ScenarioSetManifest"),
                             (scenario, "ScenarioSpec"), (capabilities, "CapabilityManifest")):
            require(record.kind == kind, f"expected {kind}")
        d = study.data
        require(d["scenario_set_hash"] == scenario_set.content_hash
                and d["scenario_set_version"] == scenario_set.data["version"], "scenario-set freeze mismatch")
        require(d["capability_manifest_hash"] == capabilities.content_hash, "capability manifest mismatch")
        require(d["parameter_set_hash"] == scenario.data["parameter_set_hash"], "parameter-set mismatch")
        require(any(m["scenario_id"] == scenario.data["scenario_id"]
                    and m["revision"] == scenario.data["revision"]
                    and m["content_hash"] == scenario.content_hash for m in scenario_set.data["members"]),
                "scenario is not an exact member of the frozen set")
        require(treatment_id in {t["treatment_id"] for t in d["treatments"]}, "treatment not frozen in study")
        caps = {c["capability_id"]: c for c in capabilities.data["capabilities"]}
        require(set(scenario.data["required_capability_ids"]) <= caps.keys(), "scenario capability unavailable")
        # Validate every frozen treatment, not just the one about to run.
        for treatment in d["treatments"]:
            for binding in treatment["bindings"]:
                self.resolve(binding)
                require(set(binding["capability_ids"]) <= caps.keys(), "provider capability unavailable")
                truth = [caps[c] for c in binding["capability_ids"] if caps[c]["kind"] == "truth"]
                require(not truth or binding["information_regime"] == "oracle_state", "truth capability granted to ordinary provider")
        run = AdmittedRun(study, scenario_set, scenario, capabilities, treatment_id, run_id)
        # Reuse the schema's identifier/scope checks without storing a phantom invocation.
        from jsonschema import Draft202012Validator
        from .schema import schema_document
        schema = schema_document()
        schema["$ref"] = "#/$defs/Scope"
        require(Draft202012Validator(schema).is_valid(run.scope), "invalid run identity")
        return run
