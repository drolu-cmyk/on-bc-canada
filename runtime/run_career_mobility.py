"""Command interface for deidentified Career Mobility guidance."""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from runtime.capability_graph import CapabilityGraphStore
from runtime.career_mobility_runner import career_mobility_summary, start_career_mobility
from runtime.execution_store_factory import create_execution_store
from runtime.learner_progress_store import LearnerProgressStore
from runtime.openai_career_mobility_provider import OpenAICareerMobilityProvider
from runtime.work_intelligence import WorkIntelligenceStore


DEFAULT_LEARNER_DB = Path(os.getenv("SOZOROCK_LEARNER_DB", "local-data/learner.sqlite3"))
DEFAULT_CAPABILITY_DB = Path(os.getenv("SOZOROCK_CAPABILITY_DB", "local-data/capabilities.sqlite3"))
DEFAULT_WORK_DB = Path(os.getenv("SOZOROCK_WORK_DB", "local-data/work-intelligence.sqlite3"))
DEFAULT_EXECUTION_DB = Path(os.getenv("SOZOROCK_GRAPH_DB", "local-data/graph-executions.sqlite3"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Career Mobility Graph.")
    parser.add_argument("--learner-db", default=str(DEFAULT_LEARNER_DB))
    parser.add_argument("--capability-db", default=str(DEFAULT_CAPABILITY_DB))
    parser.add_argument("--work-db", default=str(DEFAULT_WORK_DB))
    parser.add_argument("--execution-db", default=str(DEFAULT_EXECUTION_DB))
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Create deidentified learner-facing career guidance.")
    start.add_argument("--instance-id", required=True)
    start.add_argument("--execution-id", default=None)

    status = subparsers.add_parser("status", help="Read stored career guidance without a model call.")
    status.add_argument("--execution-id", required=True)
    return parser


def _provider() -> OpenAICareerMobilityProvider:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required to start Career Mobility agents")
    return OpenAICareerMobilityProvider()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    learner_store = LearnerProgressStore(args.learner_db)
    capability_store = CapabilityGraphStore(args.capability_db)
    work_store = WorkIntelligenceStore(args.work_db)
    execution_store = create_execution_store(local_path=args.execution_db)

    try:
        if args.command == "start":
            execution = start_career_mobility(
                provider=_provider(),
                learner_store=learner_store,
                capability_store=capability_store,
                work_store=work_store,
                execution_store=execution_store,
                execution_id=args.execution_id or f"career-{uuid.uuid4().hex[:12]}",
                instance_id=args.instance_id,
            )
        else:
            execution, _ = execution_store.load_execution(args.execution_id)
            if execution.graph_id != "career-mobility":
                raise ValueError("stored execution is not Career Mobility guidance")
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps(career_mobility_summary(execution), ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if execution.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
