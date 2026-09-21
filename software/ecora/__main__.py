"""CLI for schema export, record validation, artifact inspection and synthetic runs."""

import argparse
import json
import time
from pathlib import Path

from .boundary import Boundary
from .contracts import ContractError, Record
from .fixtures import batch, fixture_environment, payload_fixtures
from .model import FiniteModel, Link
from .runner import Run, Streams, closed_loop_environment
from .schema import schema_document
from .store import ArtifactStore

CAPABILITIES = {("site-1", "queue_occupancy"): "observe.ami.queue",
                ("site-1", "path_state"): "observe.shared.path"}


def _world():
    """The finite reference world. Synthetic throughout; no radio and no calibration."""
    return FiniteModel(
        sites=["site-1"],
        links={"lte": Link("lte", 1000000, 0.010, 65536),
               "alternative": Link("alternative", 1000000, 0.010, 65536)},
        egress=Link("egress", 256000, 0.001, 65536),
        scada_period_s=0.1, ami_period_s=1.0, scada_bytes=512, ami_bytes=512,
        scada_deadline_s=0.25, ami_deadline_s=10.0)


def _execute(root, treatment, epochs, period_s):
    model = _world()
    registry, study, scenario_set, scenario, caps = closed_loop_environment(model, period_s=period_s)
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
        report = Record.from_dict(store.messages(dataset)[0].data["payload"])
        binding = run.binding("action")
        return {"treatment": treatment, "arm": binding["arm"], "provider": binding["provider_id"],
                "sensed": sensed, "relayed": relayed, "decided": epochs, "applied": applied,
                "path": model.truth()["selected_path"]["site-1"],
                "verdict": report.data["claims"][0]["verdict"] if report.data["claims"] else "none",
                "dataset": dataset, "scope": run.scope, "integrity": store.verify()}


def showcase(directory, epochs, period_s=0.5):
    """Run the Null baseline and the closed loop over one frozen study, and compare them."""
    started = time.perf_counter()
    results = [_execute(directory, treatment, epochs, period_s)
               for treatment in ("null_baseline", "closed_loop")]
    scope = results[0]["scope"]
    print("ECoRA -- one frozen study, two treatments, one differing binding\n")
    print(f"  study     {scope['study_id']}")
    print(f"  scenario  {scope['scenario_id']} revision {scope['scenario_revision']}")
    print(f"  set       v{scope['scenario_set_version']}  {scope['scenario_set_hash'][:12]}")
    print(f"  world     1 site, two legs, shared egress 256000 bit/s (synthetic)")
    print(f"  schedule  {epochs} decision epochs at {period_s} s\n")
    header = (f"  {'treatment':<16}{'action arm':<12}{'sensed':>8}{'relayed':>9}{'decided':>9}"
              f"{'applied':>9}   {'path':<13}{'verdict'}")
    print(header)
    print("  " + "-" * (len(header) - 2))
    for r in results:
        print(f"  {r['treatment']:<16}{r['arm']:<12}{r['sensed']:>8}{r['relayed']:>9}"
              f"{r['decided']:>9}{r['applied']:>9}   {r['path']:<13}{r['verdict']}")
    print("\n  sensed  = signals the adapter read from the world")
    print("  relayed = signals the telemetry stage passed on. The Null arm withholds every")
    print("            one, so neither treatment reasons from evidence in this configuration.")
    print("\n  The treatments differ in the action stage alone:")
    for r in results:
        print(f"    {r['treatment']:<16} action <- {r['provider']:<16} ({r['arm']})")
    print("\n  Provenance of the closed-loop claim:")
    closed = results[-1]
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
    print("\n  The closed loop still acts, because the Null planner proposes from its declared")
    print("  configuration rather than from evidence. That is the baseline behaving correctly:")
    print("  it sets a floor, and each stage stays substitutable on its own.")
    print("\n  Nothing here is a network result. The world is a deterministic queueing model,")
    print("  and both verdicts are inconclusive because no requirement was evaluated.")
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
    show = commands.add_parser("showcase", help="run the Null and closed-loop arms and compare them")
    show.add_argument("directory", type=Path)
    show.add_argument("--epochs", type=int, default=4)
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
            for treatment in ("null_baseline", "closed_loop"):
                if (args.directory / treatment).exists():
                    raise ContractError(f"showcase directory already exists: {args.directory / treatment}")
            showcase(args.directory, args.epochs)
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
