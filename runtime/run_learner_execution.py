"""Command interface for deidentified learner coaching and human evidence review."""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from runtime.capability_graph import CapabilityGraphStore
from runtime.execution_store_factory import create_execution_store
from runtime.learner_execution_runner import (
    learner_assessment_summary,
    resume_learner_assessment,
    start_learner_assessment,
)
from runtime.learner_progress_store import LearnerProgressStore
from runtime.openai_learner_provider import OpenAILearnerSupportProvider


DEFAULT_LEARNER_DB = Path(os.getenv("SOZOROCK_LEARNER_DB", "local-data/learner.sqlite3"))
DEFAULT_CAPABILITY_DB = Path(os.getenv("SOZOROCK_CAPABILITY_DB", "local-data/capabilities.sqlite3"))
DEFAULT_EXECUTION_DB = Path(os.getenv("SOZOROCK_GRAPH_DB", "local-data/graph-executions.sqlite3"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Learner Execution Graph.")
    parser.add_argument("--learner-db", default=str(DEFAULT_LEARNER_DB))
    parser.add_argument("--capability-db", default=str(DEFAULT_CAPABILITY_DB))
    parser.add_argument("--execution-db", default=str(DEFAULT_EXECUTION_DB))
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Start deidentified coaching and evidence-readiness processing.")
    start.add_argument("--submission-id", required=True)
    start.add_argument("--execution-id", default=None)

    review = subparsers.add_parser("review", help="Record the accountable human evidence-review decision.")
    review.add_argument("--execution-id", required=True)
    decision = review.add_mutually_exclusive_group(required=True)
    decision.add_argument("--accept", action="store_true")
    decision.add_argument("--revise", action="store_true")
    review.add_argument("--reviewer-id", required=True)
    review.add_argument("--note", required=True)

    status = subparsers.add_parser("status", help="Read stored graph status without a model call.")
    status.add_argument("--execution-id", required=True)
    return parser


def _provider(*, live_call: bool) -> OpenAILearnerSupportProvider:
    if live_call and not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required to start learner coaching agents")
    return OpenAILearnerSupportProvider()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    progress = LearnerProgressStore(args.learner_db)
    capabilities = CapabilityGraphStore(args.capability_db)
    executions = create_execution_store(local_path=args.execution_db)

    try:
        if args.command == "start":
            execution = start_learner_assessment(
                provider=_provider(live_call=True),
                progress_store=progress,
                capability_store=capabilities,
                execution_store=executions,
                execution_id=args.execution_id or f"learner-assessment-{uuid.uuid4().hex[:12]}",
                submission_id=args.submission_id,
            )
        elif args.command == "review":
            execution = resume_learner_assessment(
                provider=_provider(live_call=False),
                progress_store=progress,
                capability_store=capabilities,
                execution_store=executions,
                execution_id=args.execution_id,
                accepted=bool(args.accept),
                reviewer_id=args.reviewer_id,
                note=args.note,
            )
        else:
            execution, _ = executions.load_execution(args.execution_id)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps(learner_assessment_summary(execution), ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if execution.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
