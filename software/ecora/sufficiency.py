"""Telemetry sufficiency: contract-limited versus privileged diagnosis over named subsets.

docs/ECoRA/stage-arms.md and system/telemetry-contract.md set the procedure, and each of its
three parts is here because leaving one out makes the result mean something else.

**Downstream is held fixed.** Every treatment in the comparison shares its planning,
resolution, action, result and assurance bindings. Only the diagnosis arm and the
observation subset vary, so a service difference is attributable to what diagnosis knew.

**Two references, matched on the signals they may use.** The contract-limited arm runs the
study's rules over what the telemetry projection relays. The privileged arm runs the same
rules over exact current truth of the *same* signals. The gap between them is information
access: freshness, fidelity and coverage at a fixed signal set. It is not a gap in reasoning,
because the rules and the inference are shared.

**Named observation subsets.** The full projection, then each expected signal withheld in
turn. Withholding is an intervention on what the study grants, declared by name, and the
difference between the full contract arm and a withheld one is what that signal is worth
to the configuration downstream of it.

Two further obligations keep a small gap from being read as sufficiency:

- **Diagnosis is scored against ground truth after the decision.** The harness reads truth
  at each decision instant through its own logged port and derives the labels the rules
  would reach on it. Nothing it reads is delivered to any provider. A controller with no
  diagnostic error and a controller whose errors happened not to matter downstream look the
  same in service outcomes; the score separates them.
- **Identifiability is stated, not inferred from a run.** A label whose every derivation
  needs a withheld signal cannot be concluded by any diagnoser on that subset, privileged
  or not. That is a property of the rule inventory and the subset, so it is computed from
  them and reported beside the measured gap.

A small privileged-minus-contract gap on this model shows that the observation contract
loses little for these predicates in these states. It does not show that telemetry is not a
bottleneck elsewhere, and a finite deterministic model is not a network.
"""

from .boundary import Boundary
from .contracts import Record, digest, require
from .experts import infer
from .report import run_report
from .runner import Run, Streams
from .store import ArtifactStore
from .truth import TruthPort

VERSION = "sufficiency-v1"
SERVICE_METRIC = "within_age_delivery"


def signal_name(entry):
    """How rules refer to a signal: its metric, qualified by subject below site level."""
    return entry["metric"] if "/" not in entry["subject"] else f"{entry['subject']}/{entry['metric']}"


def observation_subsets(projection):
    """The full projection, then each expected signal withheld in turn, by name.

    Leave-one-out is declared rather than chosen per result: every signal the projection
    expects is withheld exactly once, so no subset is included because it made a point.
    """
    names = [signal_name(entry) for entry in projection["expected"]]
    require(len(set(names)) == len(names), "two expected signals share a name")
    subsets = {"full": []}
    for name in names:
        subsets[f"without:{name}"] = [name]
    return subsets


def unidentifiable(rules, withheld):
    """Labels no diagnoser can conclude when these signals are withheld.

    A label is lost when every rule that concludes it needs a withheld signal or another
    lost label. This holds for the privileged arm as much as the contract one, because
    both are restricted to the same signals.
    """
    withheld = set(withheld)
    authors = {}
    for rule in rules:
        authors.setdefault(rule["concludes"], []).append(rule)
    lost, changed = set(), True
    while changed:
        changed = False
        for label, concluding in authors.items():
            if label in lost:
                continue
            if all(set(rule["requires"]) & withheld
                   or set(rule.get("requires_predicates", [])) & lost for rule in concluding):
                lost.add(label)
                changed = True
    return sorted(lost)


def _truth_reads(capabilities, reads, withheld):
    """The Oracle's reads restricted to the signals the subset keeps."""
    by_id = {c["capability_id"]: c for c in capabilities}
    kept = []
    for capability_id in reads:
        capability = by_id[capability_id]
        name = signal_name({"subject": capability["target"], "metric": capability["name"]})
        if name not in withheld:
            kept.append(capability_id)
    return kept


def _rebind(binding, configuration=None, **changes):
    updated = {**binding, **changes}
    if configuration is not None:
        updated["configuration"] = configuration
        updated["configuration_hash"] = digest(configuration)
    return updated


def sufficiency_study(study, capabilities, projection):
    """Add the paired treatments for every named subset to a frozen study manifest.

    The result is a different study, with a different hash, which is the honest way to
    add cells: a study already measured is not extended in place.
    """
    treatments = {t["treatment_id"]: t["bindings"] for t in study.data["treatments"]}
    require({"eco", "assured", "oracle_diagnosis"} <= treatments.keys(),
            "the sufficiency comparison is built from the eco, assured and oracle_diagnosis arms")

    def stage(treatment, name):
        return next(b for b in treatments[treatment] if b["stage_id"] == name)

    # Downstream of diagnosis: eco's planning, resolution and action, and the Proposed
    # extraction and evaluator, so both arms reach verdicts from the same frozen scoring.
    fixed = {name: stage("eco", name) for name in ("planning", "resolution", "action")}
    fixed.update({name: stage("assured", name) for name in ("result", "assurance")})
    telemetry, limited = stage("eco", "telemetry"), stage("eco", "diagnosis")
    privileged = stage("oracle_diagnosis", "diagnosis")
    every = capabilities.data["capabilities"]
    added, subsets = [], observation_subsets(projection)
    for subset, withheld in subsets.items():
        expected = [e for e in projection["expected"] if signal_name(e) not in withheld]
        sensing = _rebind(telemetry, {**telemetry["configuration"], "expected": expected})
        reads = _truth_reads(every, privileged["configuration"]["reads"], withheld)
        require(reads, f"the {subset} subset leaves the privileged arm nothing to read")
        informed = _rebind(privileged, {**privileged["configuration"], "reads": reads})
        for arm, diagnosis in (("contract", limited), ("privileged", informed)):
            chain = {"telemetry": sensing, "diagnosis": diagnosis, **fixed}
            taint = arm == "privileged"
            bindings = [chain[b["stage_id"]] if b["stage_id"] in ("telemetry", "diagnosis")
                        else _rebind(chain[b["stage_id"]],
                                     allow_privileged_inputs=taint or chain[b["stage_id"]]["allow_privileged_inputs"])
                        for b in treatments["eco"]]
            added.append({"treatment_id": f"sufficiency:{arm}:{subset}", "bindings": bindings})
    data = {**study.data, "treatments": [*study.data["treatments"], *added]}
    return Record("StudyManifest", data), subsets


class ScoredRun(Run):
    """A run whose diagnoses are scored against truth after the fact.

    The scorer reads truth at each decision instant, immediately after the world advances
    and before any stage runs, through a port of its own. What it reads goes into this
    object and nowhere else: not into the store, not into any provider's inputs. The
    controller's evidence is exactly what it would have been without the scorer.
    """

    def __init__(self, *args, truth_capabilities, truth_reads, rules, **kwargs):
        super().__init__(*args, **kwargs)
        self.scorer = TruthPort(self.model, truth_capabilities)
        self.truth_reads = truth_reads
        self.rules = rules
        self.truth_labels = []

    def _export(self, label, at, sequence):
        exported = super()._export(label, at, sequence)
        if label != "closing":
            observations = [self.scorer.read(c, at) for c in self.truth_reads]
            inference, _, _ = infer(self.rules["rules"], observations,
                                    self.rules.get("activation_budget", 1000))
            self.truth_labels.append(sorted(inference.concluded))
        return exported


def _concluded(store, epochs):
    labels = []
    for index in range(epochs):
        found = set()
        for message in store.messages(f"dataset:diagnosis:{index}"):
            payload = Record.from_dict(message.data["payload"])
            if payload.kind == "DiagnosisRecord":
                found.update(h["label"] for h in payload.data["hypotheses"]
                             if h["status"] == "supported")
        labels.append(sorted(found))
    return labels


def score(truth_labels, concluded):
    """Per-epoch agreement with ground truth: missed, spurious and exact epochs."""
    missed, spurious, exact = {}, {}, 0
    for truth, reached in zip(truth_labels, concluded):
        for label in set(truth) - set(reached):
            missed[label] = missed.get(label, 0) + 1
        for label in set(reached) - set(truth):
            spurious[label] = spurious.get(label, 0) + 1
        exact += set(truth) == set(reached)
    return {"epochs": len(truth_labels), "exact_epochs": exact,
            "missed": dict(sorted(missed.items())), "spurious": dict(sorted(spurious.items()))}


def execute(root, *, build_model, environment, capability_ids, knowledge, period_s, epochs):
    """Run every subset under both arms and return the per-run evidence."""
    subsets = observation_subsets(knowledge.projection)
    runs = {}
    for subset in subsets:
        for arm in ("contract", "privileged"):
            treatment = f"sufficiency:{arm}:{subset}"
            # A fresh world and a fresh environment per run, so no state carries across
            # cells. The study hash is the same each time because the build is.
            model = build_model()
            registry, base, scenario_set, scenario, caps = environment(model)
            study, _ = sufficiency_study(base, caps, knowledge.projection)
            truths = [c for c in caps.data["capabilities"] if c["kind"] == "truth"]
            directory = root / treatment.replace(":", "_").replace("/", "_")
            with ArtifactStore(directory) as store:
                run = registry.admit(study, scenario_set, scenario, caps, treatment,
                                     f"run:{treatment}")
                scored = ScoredRun(Boundary(store, registry, run), model,
                                   streams=Streams(study.data["seed_manifest"]),
                                   capability_ids=capability_ids, period_s=period_s,
                                   epochs=epochs, assembly=study.data["assembly"],
                                   predicate_map=knowledge.predicate_map,
                                   truth_capabilities=truths,
                                   truth_reads=knowledge.oracle["diagnosis_reads"],
                                   rules=knowledge.rules)
                scored.execute()
                report = run_report(store)
                runs[(subset, arm)] = {
                    "study_hash": study.content_hash,
                    "diagnosis": score(scored.truth_labels, _concluded(store, epochs)),
                    "scorer_reads": len(scored.scorer.log),
                    "applied": sum(p.data["disposition"] == "applied"
                                   for index in range(epochs)
                                   for p in (Record.from_dict(m.data["payload"])
                                             for m in store.messages(f"dataset:action:{index}"))
                                   if p.kind == "ActionReceipt"),
                    "path": model.truth()["selected_path"],
                    "service": report["service_outcomes"],
                    "privileged": report["privileged_information"]["present"]}
    return runs, subsets


def _service(run):
    return {service: metrics.get(SERVICE_METRIC, {}).get("value")
            for service, metrics in run["service"]["by_service"].items()}


def _difference(high, low):
    """Paired difference per service; unknown where either side is unknown."""
    return {service: None if high.get(service) is None or low.get(service) is None
            else high[service] - low[service] for service in sorted(set(high) | set(low))}


def compare(runs, subsets, rules):
    """The two contrasts the procedure defines, per subset, with identifiability beside them."""
    full = _service(runs[("full", "contract")])
    rows = []
    for subset, withheld in subsets.items():
        limited, informed = runs[(subset, "contract")], runs[(subset, "privileged")]
        rows.append({
            "subset": subset, "withheld": withheld,
            "unidentifiable": unidentifiable(rules["rules"], withheld),
            "contract": {"service": _service(limited), "diagnosis": limited["diagnosis"],
                         "applied": limited["applied"], "verdicts": limited["service"]["verdicts"]},
            "privileged": {"service": _service(informed), "diagnosis": informed["diagnosis"],
                           "applied": informed["applied"],
                           "verdicts": informed["service"]["verdicts"]},
            # Information-access headroom at this signal set.
            "access_headroom": _difference(_service(informed), _service(limited)),
            # What withholding this subset cost the contract arm, relative to the full set.
            "subset_cost": _difference(full, _service(limited))})
    return {"version": VERSION, "service_metric": SERVICE_METRIC, "rows": rows,
            "note": "Downstream stages held fixed; privileged results are references, not "
                    "deployable evidence; a small gap is not a sufficiency finding by itself."}
