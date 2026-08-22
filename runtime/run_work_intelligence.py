"""Command interface for the reviewed Work Intelligence store."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from runtime.domain_store_factory import create_work_intelligence_store
from runtime.research_store import ResearchStore


DEFAULT_RESEARCH_DB = Path(os.getenv("SOZOROCK_RESEARCH_DB", "local-data/research.sqlite3"))
DEFAULT_WORK_DB = Path(os.getenv("SOZOROCK_WORK_DB", "local-data/work-intelligence.sqlite3"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate the reviewed Work Intelligence Graph.")
    parser.add_argument("--work-db", default=str(DEFAULT_WORK_DB), help="Local SQLite path when SOZOROCK_DOMAIN_BACKEND=local.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="Ingest one completed Research Graph execution.")
    ingest.add_argument("--research-db", default=str(DEFAULT_RESEARCH_DB))
    ingest.add_argument("--execution-id", required=True)
    ingest.add_argument("--pathway-id", required=True)
    ingest.add_argument("--pathway-name", required=True)

    inspect = subparsers.add_parser("inspect", help="Inspect one entity and its relationships.")
    inspect.add_argument("--entity-type", required=True)
    inspect.add_argument("--name", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    work = create_work_intelligence_store(args.work_db)
    try:
        if args.command == "ingest":
            execution, _ = ResearchStore(args.research_db).load_execution(args.execution_id)
            result = work.ingest_research_execution(
                execution,
                pathway_id=args.pathway_id,
                pathway_name=args.pathway_name,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 0

        entity = work.find_entity(args.entity_type, args.name)
        if entity is None:
            raise KeyError(f"work intelligence entity not found: {args.entity_type}:{args.name}")
        result = {"entity": entity, "relations": work.relations_for_entity(entity["entity_id"])}
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (KeyError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
