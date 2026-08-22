"""Command-line entrypoint for durable live Canadian technical-work research."""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from runtime.openai_research_provider import OpenAIResearchProvider
from runtime.research_runner import execution_summary, resume_research, start_research
from runtime.research_store import ResearchStore


DEFAULT_DB = Path(os.getenv("SOZOROCK_RESEARCH_DB", "local-data/research.sqlite3"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Canadian technical-work Research Graph.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Local SQLite state path. Defaults under ignored local-data/.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Start a live research execution.")
    start.add_argument("--question", required=True)
    start.add_argument("--geography", default="Canada")
    start.add_argument("--execution-id", default=None)

    resume = subparsers.add_parser("resume", help="Resolve a pending human gate and resume the graph.")
    resume.add_argument("--execution-id", required=True)
    decision = resume.add_mutually_exclusive_group(required=True)
    decision.add_argument("--approve", action="store_true")
    decision.add_argument("--deny", action="store_true")
    resume.add_argument("--approver-id", required=True)
    resume.add_argument("--note", default="")

    status = subparsers.add_parser("status", help="Read a stored execution without calling a model.")
    status.add_argument("--execution-id", required=True)

    return parser


def _live_provider() -> OpenAIResearchProvider:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for a live research execution")
    return OpenAIResearchProvider()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = ResearchStore(args.db)

    try:
        if args.command == "start":
            execution = start_research(
                provider=_live_provider(),
                store=store,
                execution_id=args.execution_id or f"research-{uuid.uuid4().hex[:12]}",
                question=args.question,
                geography=args.geography,
            )
        elif args.command == "resume":
            execution = resume_research(
                provider=_live_provider(),
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

    print(json.dumps(execution_summary(execution), ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if execution.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
