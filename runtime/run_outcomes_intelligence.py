"""Command interface for privacy-preserving Outcomes Intelligence."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import uuid
from pathlib import Path

from runtime.execution_store_factory import create_execution_store
from runtime.openai_outcomes_provider import OpenAIOutcomesIntelligenceProvider
from runtime.outcomes_intelligence import OutcomesSnapshotBuilder
from runtime.outcomes_intelligence_runner import outcomes_intelligence_summary, start_outcomes_intelligence


DEFAULT_LEARNER_DB = Path(os.getenv("SOZOROCK_LEARNER_DB", "local-data/learner-progress.sqlite3"))
DEFAULT_EXECUTION_DB = Path(os.getenv("SOZOROCK_GRAPH_DB", "local-data/graph-executions.sqlite3"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run privacy-preserving Outcomes Intelligence.")
    parser.add_argument("--learner-db", default=str(DEFAULT_LEARNER_DB))
    parser.add_argument("--execution-db", default=str(DEFAULT_EXECUTION_DB))
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Build an aggregate outcomes snapshot and analyze it.")
    start.add_argument("--pathway-id", default=None)
    start.add_argument("--learning-version", default=None)
    start.add_argument("--execution-id", default=None)

    status = subparsers.add_parser("status", help="Read stored Outcomes Intelligence without a model call.")
    status.add_argument("--execution-id", required=True)
    return parser


def _provider() -> OpenAIOutcomesIntelligenceProvider:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required to start Outcomes Intelligence agents")
    return OpenAIOutcomesIntelligenceProvider()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = create_execution_store(local_path=args.execution_db)
    try:
        if args.command == "start":
            snapshot = OutcomesSnapshotBuilder(args.learner_db).build(
                pathway_id=args.pathway_id,
                learning_version=args.learning_version,
            )
            execution = start_outcomes_intelligence(
                provider=_provider(),
                execution_store=store,
                execution_id=args.execution_id or f"outcomes-{uuid.uuid4().hex[:12]}",
                snapshot=snapshot,
            )
        else:
            execution, _ = store.load_execution(args.execution_id)
            if execution.graph_id != "outcomes-intelligence":
                raise ValueError("stored execution is not Outcomes Intelligence")
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps(outcomes_intelligence_summary(execution), ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if execution.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
