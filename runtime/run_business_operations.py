"""Command-line entrypoint for durable Business Operations Graph executions."""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from runtime.business_operations_runner import (
    business_execution_summary,
    resume_business_operations,
    start_business_operations,
)
from runtime.graph_execution_store import GraphExecutionStore
from runtime.openai_business_operations_provider import OpenAIBusinessOperationsProvider


DEFAULT_DB = Path(os.getenv("SOZOROCK_BUSINESS_DB", "local-data/business-operations.sqlite3"))
WORKSTREAMS = ("growth", "marketing", "partnerships", "operations", "finance")
ACTION_CLASSES = ("analysis", "prepare", "external_publish", "external_contact", "financial_commitment")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the routed Business Operations Graph.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Local SQLite execution-state path.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Start one bounded business-operations execution.")
    start.add_argument("--workstream", required=True, choices=WORKSTREAMS)
    start.add_argument("--action-class", required=True, choices=ACTION_CLASSES)
    start.add_argument("--problem", required=True)
    start.add_argument("--metric", action="append", default=[])
    start.add_argument("--evidence", action="append", default=[])
    start.add_argument("--constraint", action="append", default=[])
    start.add_argument("--execution-id", default=None)

    resume = subparsers.add_parser("resume", help="Resolve an A3 or A4 human gate and continue the graph.")
    resume.add_argument("--execution-id", required=True)
    decision = resume.add_mutually_exclusive_group(required=True)
    decision.add_argument("--approve", action="store_true")
    decision.add_argument("--deny", action="store_true")
    resume.add_argument("--approver-id", required=True)
    resume.add_argument("--note", required=True)

    status = subparsers.add_parser("status", help="Read stored execution state without a model call.")
    status.add_argument("--execution-id", required=True)
    return parser


def _provider() -> OpenAIBusinessOperationsProvider:
    return OpenAIBusinessOperationsProvider()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = GraphExecutionStore(args.db)
    try:
        if args.command == "start":
            if not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError("OPENAI_API_KEY is required for a live business-operations execution")
            request = {
                "workstream": args.workstream,
                "action_class": args.action_class,
                "problem": args.problem,
                "metrics": args.metric,
                "evidence": args.evidence,
                "constraints": args.constraint,
                "market": "Canada",
            }
            execution = start_business_operations(
                provider=_provider(),
                store=store,
                execution_id=args.execution_id or f"business-{args.workstream}-{uuid.uuid4().hex[:10]}",
                request=request,
            )
        elif args.command == "resume":
            execution = resume_business_operations(
                provider=_provider(),
                store=store,
                execution_id=args.execution_id,
                approved=bool(args.approve),
                approver_id=args.approver_id,
                note=args.note,
            )
        else:
            execution, _ = store.load_execution(args.execution_id)
    except (KeyError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps(business_execution_summary(execution), ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if execution.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
