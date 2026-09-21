"""CLI for schema export, record validation, artifact inspection and a synthetic demo."""

import argparse
import json
from pathlib import Path

from .boundary import Boundary
from .contracts import ContractError, Record
from .fixtures import batch, fixture_environment, payload_fixtures
from .schema import schema_document
from .store import ArtifactStore


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
