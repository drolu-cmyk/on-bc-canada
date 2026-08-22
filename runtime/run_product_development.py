"""Command-line entrypoint for durable Product Development Graph executions."""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from runtime.openai_product_provider import OpenAIProductDevelopmentProvider
from runtime.product_development_runner import (
    product_execution_summary,
    resume_product_development,
    start_product_development,
)
from runtime.product_development_store import ProductDevelopmentStore


DEFAULT_DB = Path(os.getenv("SOZOROCK_PRODUCT_DB", "local-data/product-development.sqlite3"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Product Development Graph.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Local SQLite execution-state path.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Start an agent-assisted product-development execution.")
    start.add_argument("--problem", required=True)
    start.add_argument("--constraint", action="append", default=[])
    start.add_argument("--surface", action="append", default=[])
    start.add_argument("--evidence", action="append", default=[])
    start.add_argument("--execution-id", default=None)

    resume = subparsers.add_parser("resume", help="Resolve the A3 release review and continue the graph.")
    resume.add_argument("--execution-id", required=True)
    decision = resume.add_mutually_exclusive_group(required=True)
    decision.add_argument("--approve", action="store_true")
    decision.add_argument("--deny", action="store_true")
    resume.add_argument("--approver-id", required=True)
    resume.add_argument("--note", required=True)

    status = subparsers.add_parser("status", help="Read stored execution state without a model call.")
    status.add_argument("--execution-id", required=True)
    return parser


def _provider() -> OpenAIProductDevelopmentProvider:
    return OpenAIProductDevelopmentProvider()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = ProductDevelopmentStore(args.db)
    try:
        if args.command == "start":
            if not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError("OPENAI_API_KEY is required for a live product-development execution")
            request = {
                "problem": args.problem,
                "constraints": args.constraint,
                "target_surfaces": args.surface,
                "evidence": args.evidence,
                "market": "Canada",
            }
            execution = start_product_development(
                provider=_provider(),
                store=store,
                execution_id=args.execution_id or f"product-{uuid.uuid4().hex[:10]}",
                request=request,
            )
        elif args.command == "resume":
            execution = resume_product_development(
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

    print(json.dumps(product_execution_summary(execution), ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if execution.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
