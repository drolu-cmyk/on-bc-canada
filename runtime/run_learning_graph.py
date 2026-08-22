"""Command-line operations for agent-assisted Learning Graph design and review."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from runtime.domain_store_factory import create_capability_store, create_learning_store
from runtime.openai_learning_provider import LearningDesignContext, OpenAILearningDesignProvider


DEFAULT_LEARNING_DB = Path(os.getenv("SOZOROCK_LEARNING_DB", "local-data/learning.sqlite3"))
DEFAULT_CAPABILITY_DB = Path(os.getenv("SOZOROCK_CAPABILITY_DB", "local-data/capabilities.sqlite3"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate the reviewed Learning Graph.")
    parser.add_argument("--db", default=str(DEFAULT_LEARNING_DB), help="Local Learning Graph SQLite path when SOZOROCK_DOMAIN_BACKEND=local.")
    parser.add_argument("--capability-db", default=str(DEFAULT_CAPABILITY_DB), help="Local Capability Graph SQLite path when SOZOROCK_DOMAIN_BACKEND=local.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    design = subparsers.add_parser("design", help="Generate and validate a candidate learning path from active capabilities.")
    design.add_argument("--pathway-id", required=True)
    design.add_argument("--version", required=True)
    design.add_argument("--title", required=True)
    design.add_argument("--capability", action="append", required=True)
    design.add_argument(
        "--module-context",
        action="append",
        default=[],
        help="Optional JSON object describing an existing module that may be reused.",
    )

    activate = subparsers.add_parser("activate", help="Activate a reviewed candidate learning path.")
    activate.add_argument("--pathway-id", required=True)
    activate.add_argument("--version", required=True)
    activate.add_argument("--approver-id", required=True)
    activate.add_argument("--note", required=True)

    retire = subparsers.add_parser("retire", help="Retire an active learning path version.")
    retire.add_argument("--pathway-id", required=True)
    retire.add_argument("--version", required=True)
    retire.add_argument("--approver-id", required=True)
    retire.add_argument("--note", required=True)

    inspect = subparsers.add_parser("inspect", help="Inspect one learning path version.")
    inspect.add_argument("--pathway-id", required=True)
    inspect.add_argument("--version", required=True)

    active = subparsers.add_parser("active", help="Read the active path for one pathway.")
    active.add_argument("--pathway-id", required=True)
    return parser


def _module_context(items: list[str]) -> tuple[dict[str, object], ...]:
    modules = []
    for raw in items:
        item = json.loads(raw)
        if not isinstance(item, dict):
            raise ValueError("module context must be a JSON object")
        modules.append(item)
    return tuple(modules)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    learning = create_learning_store(args.db)
    capabilities = create_capability_store(args.capability_db)

    try:
        if args.command == "design":
            if not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError("OPENAI_API_KEY is required for agent-assisted learning design")
            capability_records = tuple(capabilities.get(capability_id) for capability_id in args.capability)
            context = LearningDesignContext(
                pathway_id=args.pathway_id,
                version=args.version,
                title=args.title,
                active_capabilities=capability_records,
                existing_modules=_module_context(args.module_context),
            )
            definition = OpenAILearningDesignProvider().propose(context)
            result = learning.save_candidate(definition, capabilities=capabilities)
        elif args.command == "activate":
            result = learning.activate(args.pathway_id, args.version, approver_id=args.approver_id, note=args.note)
        elif args.command == "retire":
            result = learning.retire(args.pathway_id, args.version, approver_id=args.approver_id, note=args.note)
        elif args.command == "inspect":
            result = learning.get(args.pathway_id, args.version)
        else:
            result = learning.active_path(args.pathway_id)
            if result is None:
                raise KeyError(f"active learning path not found: {args.pathway_id}")
    except (json.JSONDecodeError, KeyError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
