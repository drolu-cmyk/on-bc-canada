"""Command-line operations for the reviewed Capability Graph."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from runtime.capability_graph import CapabilityGraphStore, EvidenceStandard
from runtime.work_intelligence import WorkIntelligenceStore


DEFAULT_CAPABILITY_DB = Path(os.getenv("SOZOROCK_CAPABILITY_DB", "local-data/capabilities.sqlite3"))
DEFAULT_WORK_DB = Path(os.getenv("SOZOROCK_WORK_INTELLIGENCE_DB", "local-data/work-intelligence.sqlite3"))
LEVELS = ("explain", "apply", "analyze", "evaluate", "design", "defend")
STATUSES = ("draft", "active", "retired")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate the reviewed learner Capability Graph.")
    parser.add_argument("--db", default=str(DEFAULT_CAPABILITY_DB), help="Capability Graph SQLite path.")
    parser.add_argument("--work-db", default=str(DEFAULT_WORK_DB), help="Work Intelligence SQLite path.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    draft = subparsers.add_parser("draft-from-work", help="Create a draft capability from Work Intelligence evidence.")
    draft.add_argument("--pathway-id", required=True)
    draft.add_argument("--pathway-name", required=True)
    draft.add_argument("--capability-id", required=True)
    draft.add_argument("--capability-name", required=True)
    draft.add_argument("--description", required=True)
    draft.add_argument("--target-level", required=True, choices=LEVELS)
    draft.add_argument("--prerequisite", action="append", default=[])
    draft.add_argument(
        "--evidence-standard",
        action="append",
        required=True,
        help="JSON object containing standard_id, description, artifact_types, minimum_level, and optional defense/revision flags.",
    )

    activate = subparsers.add_parser("activate", help="Activate a reviewed draft capability.")
    activate.add_argument("--capability-id", required=True)
    activate.add_argument("--approver-id", required=True)
    activate.add_argument("--note", default="")

    retire = subparsers.add_parser("retire", help="Retire an active capability after dependency checks.")
    retire.add_argument("--capability-id", required=True)
    retire.add_argument("--approver-id", required=True)
    retire.add_argument("--note", required=True)

    inspect = subparsers.add_parser("inspect", help="Inspect one capability definition.")
    inspect.add_argument("--capability-id", required=True)

    pathway = subparsers.add_parser("pathway", help="List capability definitions for one pathway.")
    pathway.add_argument("--pathway-id", required=True)
    pathway.add_argument("--status", choices=STATUSES, default=None)

    return parser


def _parse_standard(raw: str) -> EvidenceStandard:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("evidence standard must be a JSON object")
    return EvidenceStandard(
        standard_id=str(payload.get("standard_id", "")),
        description=str(payload.get("description", "")),
        artifact_types=tuple(payload.get("artifact_types", [])),
        minimum_level=payload.get("minimum_level", ""),
        requires_defense=bool(payload.get("requires_defense", False)),
        requires_revision=bool(payload.get("requires_revision", True)),
        requires_changed_scenario=bool(payload.get("requires_changed_scenario", False)),
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = CapabilityGraphStore(args.db)

    try:
        if args.command == "draft-from-work":
            work_store = WorkIntelligenceStore(args.work_db)
            definition = store.draft_from_work_intelligence(
                work_store=work_store,
                pathway_id=args.pathway_id,
                pathway_name=args.pathway_name,
                capability_id=args.capability_id,
                capability_name=args.capability_name,
                description=args.description,
                target_level=args.target_level,
                evidence_standards=tuple(_parse_standard(item) for item in args.evidence_standard),
                prerequisite_ids=tuple(args.prerequisite),
            )
            result = store.get(definition.capability_id)
        elif args.command == "activate":
            result = store.activate(args.capability_id, approver_id=args.approver_id, note=args.note)
        elif args.command == "retire":
            result = store.retire(args.capability_id, approver_id=args.approver_id, note=args.note)
        elif args.command == "inspect":
            result = store.get(args.capability_id)
        else:
            result = {
                "pathway_id": args.pathway_id,
                "status_filter": args.status,
                "capabilities": store.list_pathway(args.pathway_id, status=args.status),
            }
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
