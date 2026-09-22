"""CLI for schema export, record validation, artifact inspection and synthetic runs."""

import argparse
import json
import time
from pathlib import Path

from .boundary import Boundary
from .contracts import ContractError, Record, require
from .fixtures import batch, fixture_environment, payload_fixtures
from .metrics import measurements, read_run
from .runner import Run, Streams, closed_loop_environment
from .scenario import SCENARIOS, build_world, load
from .schema import schema_document
from .store import ArtifactStore

CAPABILITIES = {("site-1", "queue_occupancy"): "observe.ami.queue",
                ("site-1", "path_state"): "observe.shared.path",
                ("site-1", "pacing_profile"): "observe.ami.pacing",
                ("site-1/lte", "path_probe"): "observe.probe.lte",
                ("site-1/alternative", "path_probe"): "observe.probe.alternative"}


DEFAULT_SCENARIO = "s0-nominal"


def _scenario(name):
    """The scenario to run, read from a file. Synthetic throughout; no calibrated value."""
    path = Path(name)
    if not path.exists():
        path = SCENARIOS / f"{name}.json"
    require(path.exists(), f"no scenario file at {name}")
    return load(path)


def _execute(root, treatment, epochs, period_s, scenario):
    model = build_world(scenario)
    registry, study, scenario_set, scenario, caps = closed_loop_environment(
        model, period_s=period_s, scenario=scenario)
    with ArtifactStore(root / treatment) as store:
        run = registry.admit(study, scenario_set, scenario, caps, treatment, f"run:{treatment}")
        boundary = Boundary(store, registry, run)
        dataset = Run(boundary, model, streams=Streams(study.data["seed_manifest"]),
                      capability_ids=CAPABILITIES, period_s=period_s, epochs=epochs,
                      assembly=study.data["assembly"]).execute()
        sensed = relayed = applied = 0
        for index in (*range(epochs), "closing"):
            for message in store.messages(f"dataset:ingest:{index}"):
                sensed += len(Record.from_dict(message.data["payload"]).data["observations"])
        for index in range(epochs):
            # What the telemetry stage passed on, which the Null arm withholds entirely.
            for message in store.messages(f"dataset:telemetry:{index}"):
                payload = Record.from_dict(message.data["payload"])
                if payload.kind == "TelemetryBatch":
                    relayed += len(payload.data["observations"])
            for message in store.messages(f"dataset:action:{index}"):
                payload = Record.from_dict(message.data["payload"])
                applied += payload.kind == "ActionReceipt" and payload.data["disposition"] == "applied"
        concluded, activations = set(), 0
        for index in range(epochs):
            for message in store.messages(f"dataset:diagnosis:{index}"):
                payload = Record.from_dict(message.data["payload"])
                if payload.kind != "DiagnosisRecord":
                    continue
                concluded.update(h["label"] for h in payload.data["hypotheses"]
                                 if h["status"] == "supported")
                for entry in payload.data["rule_trace"]:
                    activations += entry.get("activations", 0)
        measured, _ = measurements(
            read_run(store, epochs),
            {"stability_window_s": period_s * 2, "action_churn_limit": 2,
             "claim_churn_limit": 4, "stale_retry_limit": 2}, period_s)
        behaviour = {m["metric"]: m["value"] for m in measured}
        report = Record.from_dict(store.messages(dataset)[0].data["payload"])
        # The population the verdict rests on. A verdict without it reads as a finding
        # about the run, when the frozen cohort may have counted a handful of readings.
        population = 0
        for message in store.messages("dataset:result"):
            payload = Record.from_dict(message.data["payload"])
            if payload.kind == "ResultRecord":
                population = next((m["value"] for m in payload.data["measurements"]
                                   if m["metric"] == "generated"), 0)
        binding = run.binding("action")
        sensing = run.binding("telemetry")
        return {"treatment": treatment, "arm": binding["arm"], "provider": binding["provider_id"],
                "sensing_arm": sensing["arm"], "sensing_provider": sensing["provider_id"],
                "bindings": {stage: run.binding(stage)["provider_id"]
                             for stage in ("telemetry", "diagnosis", "planning", "resolution",
                                           "action", "result", "assurance")},
                "sensed": sensed, "relayed": relayed, "applied": applied,
                "concluded": sorted(concluded), "activations": activations,
                "behaviour": behaviour,
                "path": model.truth()["selected_path"]["site-1"],
                "verdict": report.data["claims"][0]["verdict"] if report.data["claims"] else "none",
                "population": population,
                "dataset": dataset, "scope": run.scope, "integrity": store.verify()}


def showcase(directory, epochs, period_s=0.5, scenario=DEFAULT_SCENARIO):
    """Run the declared treatments over one frozen study and compare them.

    Each differs from the previous one in a single stage binding, so the difference
    between any two rows is attributable to the stage that changed.
    """
    started = time.perf_counter()
    spec = _scenario(scenario)
    results = [_execute(directory, treatment, epochs, period_s, spec)
               for treatment in ("null_baseline", "closed_loop", "observing", "expert",
                                 "blackboard", "planner", "eco", "assured",
                                 "oracle_diagnosis")]
    scope = results[0]["scope"]
    print(f"ECoRA -- one frozen study, {len(results)} treatments, one binding apart\n")
    print(f"  study     {scope['study_id']}")
    print(f"  scenario  {scope['scenario_id']} revision {scope['scenario_revision']}")
    print(f"  set       v{scope['scenario_set_version']}  {scope['scenario_set_hash'][:12]}")
    topology = spec.data["topology"]
    print(f"  world     {len(topology['sites'])} site, {len(topology['legs'])} legs, "
          f"shared egress {topology['egress']['capacity_bps']:.0f} bit/s (synthetic)")
    print(f"  condition {spec.data['initial_state'].get('note', 'undeclared')}")
    print(f"  schedule  {epochs} decision epochs at {period_s} s\n")
    header = (f"  {'treatment':<16}{'relayed':>8}{'concluded':>11}{'activations':>13}"
              f"{'applied':>9}   {'path':<13}{'verdict':<14}{'scored on'}")
    print(header)
    print("  " + "-" * (len(header) - 2))
    for r in results:
        print(f"  {r['treatment']:<16}{r['relayed']:>8}{len(r['concluded']):>11}"
              f"{r['activations']:>13}{r['applied']:>9}   {r['path']:<13}{r['verdict']:<14}"
              f"{r['population']} reading" + ("" if r['population'] == 1 else "s"))
    print(f"\n  relayed     = signals the telemetry stage passed on"
          f" (the adapter sensed {results[0]['sensed']})")
    print("  concluded   = distinct supported hypotheses the diagnosis stage reached")
    print("  activations = rule activations, which is orchestration cost and not evidence")
    print("\n  What changed between each pair, binding by binding:")
    for earlier, later in zip(results, results[1:]):
        changed = [stage for stage in earlier["bindings"]
                   if earlier["bindings"][stage] != later["bindings"][stage]]
        for stage in changed:
            print(f"    {earlier['treatment']:<14} -> {later['treatment']:<14} {stage:<11}"
                  f"{earlier['bindings'][stage]} -> {later['bindings'][stage]}")
    closed = results[-1]
    print(f"\n  Provenance of the {closed['treatment']} claim:")
    print(f"    study {closed['scope']['study_id']}")
    print(f"      scenario {closed['scope']['scenario_id']}@{closed['scope']['scenario_revision']}")
    print(f"        run {closed['scope']['run_id']}")
    print(f"          stage assurance")
    print(f"            dataset {closed['dataset']}")
    print("\n  Evidence integrity, re-read from disk:")
    for r in results:
        i = r["integrity"]
        print(f"    {r['treatment']:<16} {i['datasets']:>4} datasets  {i['messages']:>4} messages"
              f"  {i['events']:>4} journal events")
    print("\n  Measured behaviour, read from each run's own evidence:")
    behaviour = (f"    {'treatment':<16}{'reversals':>10}{'repeats':>9}{'deadlock':>10}"
                 f"{'starved':>9}{'expansions':>12}{'mark bytes':>12}{'stable':>8}")
    print(behaviour)
    print("    " + "-" * (len(behaviour) - 4))
    for r in results:
        b = r["behaviour"]
        settled = {1: "yes", 0: "no", None: "n/a"}[b["coordination_stable"]]
        print(f"    {r['treatment']:<16}{b['action_reversals']:>10}"
              f"{b['repeated_applications']:>9}{b['deadlocked_epochs']:>10}"
              f"{b['coordination_starvation_epochs']:>9}{b['search_expansions']:>12}"
              f"{b['mark_bytes']:>12}{settled:>8}")
    print("  Stability consults no service outcome, by design: a controller that sat still")
    print("  while failing its requirements is stable and failing, and the two are reported")
    print("  beside each other rather than folded together. Service starvation needs")
    print("  per-reading delivery evidence the v1 contract does not carry, so it stays unknown.")

    named = {r["treatment"]: r for r in results}
    if {"blackboard", "planner"} <= named.keys():
        repeating, settling = named["blackboard"], named["planner"]
        if repeating["applied"] > settling["applied"]:
            print(f"\n  The Null planner reapplies its configured switch every epoch"
                  f" ({repeating['applied']} times).")
            print(f"  The symbolic planner reaches the goal and stops ({settling['applied']}),"
                  f" because an achieved")
            print("  goal yields an empty plan. That difference is action churn, which is what")
            print("  the coordination instrumentation is meant to measure.")
    if {"expert", "blackboard"} <= named.keys():
        single, board = named["expert"], named["blackboard"]
        agree = single["concluded"] == board["concluded"]
        print("\n  RQ-E: with identical rules, snapshots and conflict policy, do the two")
        print("  organisations of the same rule inventory agree, and does their cost differ?")
        print(f"    conclusions agree : {agree}  {single['concluded']}")
        print(f"    activations       : single_engine {single['activations']},"
              f" blackboard {board['activations']}")
        print("  Agreement is a result here, not an assumption; a test asserts it and can fail.")
    if {"eco", "oracle_diagnosis"} <= named.keys():
        limited, informed = named["eco"], named["oracle_diagnosis"]
        gap = sorted(set(informed["concluded"]) - set(limited["concluded"]))
        print("\n  RQ0 headroom at diagnosis: what does exact current truth conclude that")
        print("  the contract-limited arm, running the same rules, does not?")
        print(f"    contract_only : {len(limited['concluded'])} conclusions")
        print(f"    oracle_state  : {len(informed['concluded'])} conclusions")
        print(f"    gap           : {gap if gap else 'none'}")
        if not gap:
            print("  No gap here, and that is the finding: for these predicates in this state")
            print("  the observation contract loses nothing. A gap appears when evidence goes")
            print("  stale or a signal is withheld, which a test exercises separately.")
        print("  A small gap alone would not identify telemetry as the bottleneck; it could")
        print("  equally be an adequate diagnoser, a downstream limit or a saturated metric.")
    print("\n  Only an arm that concluded something from evidence can act. A mutation needs")
    print("  precondition evidence, and the Null diagnosis offers a first-candidate guess")
    print("  carrying no support, so the first three arms reach no command at all. Capability")
    print("  accrues as bindings are swapped; the loop does not assume it.")
    print("\n  Nothing here is a network result. The world is a deterministic queueing model,")
    print("  and every verdict is inconclusive because no requirement was evaluated.")
    print(f"\n  Elapsed {time.perf_counter() - started:.1f} s")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ecora")
    commands = parser.add_subparsers(dest="command", required=True)
    schema = commands.add_parser("schema", help="export the complete JSON Schema")
    schema.add_argument("--output", type=Path)
    fixtures = commands.add_parser("fixtures", help="export synthetic payload fixtures")
    fixtures.add_argument("--output", type=Path)
    validate = commands.add_parser("validate", help="validate a canonical Record JSON file")
    validate.add_argument("file", type=Path)
    demo = commands.add_parser("demo", help="run synthetic provider substitution fixtures")
    demo.add_argument("directory", type=Path)
    verify = commands.add_parser("verify", help="verify an artifact store")
    verify.add_argument("directory", type=Path)
    show = commands.add_parser("showcase", help="run the declared treatments and compare them")
    show.add_argument("directory", type=Path)
    show.add_argument("--epochs", type=int, default=4)
    show.add_argument("--scenario", default=DEFAULT_SCENARIO,
                      help="a scenario identifier under scenarios/, or a path to a scenario file")
    args = parser.parse_args(argv)
    try:
        if args.command in {"schema", "fixtures"}:
            document = schema_document() if args.command == "schema" else [r.to_dict() for r in payload_fixtures()]
            text = json.dumps(document, indent=2, sort_keys=True) + "\n"
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(text, encoding="utf-8")
            else:
                print(text, end="")
        elif args.command == "validate":
            record = Record.from_json(args.file.read_bytes())
            print(f"Valid {record.kind}/1 {record.content_hash}")
        elif args.command == "showcase":
            for treatment in ("null_baseline", "closed_loop", "observing", "expert",
                              "blackboard", "planner", "eco", "assured",
                              "oracle_diagnosis"):
                if (args.directory / treatment).exists():
                    raise ContractError(f"showcase directory already exists: {args.directory / treatment}")
            showcase(args.directory, args.epochs, scenario=args.scenario)
        elif args.command == "verify":
            if not (args.directory / "journal.jsonl").is_file():
                raise ContractError("no existing artifact journal at this path")
            with ArtifactStore(args.directory) as store:
                print(json.dumps(store.verify(), sort_keys=True))
        else:
            registry, study, scenario_set, scenario, caps = fixture_environment()
            for treatment in ("reference", "substitution"):
                if (args.directory / treatment).exists():
                    raise ContractError(f"demo directory already exists: {args.directory / treatment}")
            for treatment in ("reference", "substitution"):
                path = args.directory / treatment
                with ArtifactStore(path) as store:
                    run = registry.admit(study, scenario_set, scenario, caps, treatment, f"run:{treatment}")
                    boundary = Boundary(store, registry, run)
                    source = boundary.ingest(f"{treatment}:source", batch())
                    telemetry = boundary.invoke("telemetry", f"{treatment}:telemetry", [source.data["dataset_id"]], watermark_s=0)
                    diagnosis = boundary.invoke("diagnosis", f"{treatment}:diagnosis", [telemetry.data["dataset_id"]], watermark_s=0)
                    message = store.messages(diagnosis.data["dataset_id"])[0]
                    payload = Record.from_dict(message.data["payload"])
                    print(json.dumps({"treatment": treatment, "record_type": payload.kind, "data": payload.data,
                                      "integrity": store.verify()}, sort_keys=True))
    except (ContractError, OSError) as exc:
        parser.exit(1, f"ecora: {exc}\n")


if __name__ == "__main__":
    main()
