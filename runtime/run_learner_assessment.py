"""Command-line entrypoint for durable learner mission assessment."""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from runtime.capability_graph import CapabilityGraphStore
from runtime.graph_execution_store import GraphExecutionStore
from runtime.learner_assessment_runner import (
    learner_assessment_summary,
    resume_learner_assessment,
    start_learner_assessment,
)
from runtime.learner_progress_store import LearnerProgressStore
from runtime.openai_learner_assessment_provider import OpenAILearnerAssessmentProvider


DEFAULT_ASSESSMENT_DB = Path(os.getenv("SOZOROCK_ASSESSMENT_DB", "local-data/learner-assessment.sqlite3"))
DEFAULT_LEARNER_DB = Path(os.getenv("SOZOROCK_LEARNER_DB", "local-data/learner-progress.sqlite3"))
DEFAULT_CAPABILITY_DB = Path(os.getenv("SOZOROCK_CAPABILITY_DB", "local-data/capabilities.sqlite3"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run learner mission evidence assessment.")
    parser.add_argument("--db", default=str(DEFAULT_ASSESSMENT_DB), help="Assessment graph SQLite path.")
    parser.add_argument("--learner-db", default=str(DEFAULT_LEARNER_DB), help="Learner progress SQLite path.")
    parser.add_argument("--capability-db", default=str(DEFAULT_CAPABILITY_DB), help="Capability Graph SQLite path.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Assess one recorded mission submission.")
    start.add_argument("--submission-id", required=True)
    start.add_argument("--evidence-file", default=None, help="Optional JSON list of secure evidence summaries or references.")
    start.add_argument("--execution-id", default=None)

    resume = subparsers.add_parser("resume", help="Resolve the A3 capability-evidence review.")
    resume.add_argument("--execution-id", required=True)
    decision = resume.add_mutually_exclusive_group(required=True)
    decision.add_argument("--approve", action="store_true")
    decision.add_argument("--deny", action="store_true")
    resume.add_argument("--approver-id", required=True)
    resume.add_argument("--note", required=True)

    status = subparsers.add_parser("status", help="Read stored assessment state without a model call.")
    status.add_argument("--execution-id", required=True)
    return parser


def _read_evidence_file(path: str | None) -> list[dict[str, object]]:
    if not path:
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError("evidence file must contain a JSON list of objects")
    return payload


def _provider() -> OpenAILearnerAssessmentProvider:
    return OpenAILearnerAssessmentProvider()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assessments = GraphExecutionStore(args.db)
    progress = LearnerProgressStore(args.learner_db)
    capabilities = CapabilityGraphStore(args.capability_db)
    try:
        if args.command == "start":
            if not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError("OPENAI_API_KEY is required for a live learner assessment")
            execution = start_learner_assessment(
                provider=_provider(),
                execution_store=assessments,
                progress_store=progress,
                capability_store=capabilities,
                execution_id=args.execution_id or f"assessment-{uuid.uuid4().hex[:10]}",
                submission_id=args.submission_id,
                evidence_material=_read_evidence_file(args.evidence_file),
            )
        elif args.command == "resume":
            execution = resume_learner_assessment(
                provider=_provider(),
                execution_store=assessments,
                progress_store=progress,
                execution_id=args.execution_id,
                approved=bool(args.approve),
                approver_id=args.approver_id,
                note=args.note,
            )
        else:
            execution, _ = assessments.load_execution(args.execution_id)
    except (json.JSONDecodeError, KeyError, OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps(learner_assessment_summary(execution), ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if execution.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
