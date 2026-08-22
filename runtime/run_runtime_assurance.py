"""Command interface for aggregate autonomous-platform Runtime Assurance."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import uuid
from pathlib import Path

from runtime.aws_runtime_observability import (
    CloudWatchRuntimeTelemetrySource,
    apply_cloudwatch_runtime_to_snapshot,
    aws_observability_enabled,
)
from runtime.graph_execution_store import GraphExecutionStore
from runtime.model_runtime_telemetry import telemetry_db_path
from runtime.openai_runtime_assurance_provider import OpenAIRuntimeAssuranceProvider
from runtime.runtime_assurance import RuntimeAssuranceSnapshotBuilder, RuntimeStoreSource
from runtime.runtime_assurance_runner import runtime_assurance_summary, start_runtime_assurance


DEFAULT_EXECUTION_DB = Path(os.getenv("SOZOROCK_GRAPH_DB", "local-data/graph-executions.sqlite3"))
DEFAULT_RESEARCH_DB = Path(os.getenv("SOZOROCK_RESEARCH_DB", "local-data/research.sqlite3"))
DEFAULT_TELEMETRY_DB = telemetry_db_path()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run aggregate Runtime Assurance.")
    parser.add_argument("--execution-db", default=str(DEFAULT_EXECUTION_DB))
    parser.add_argument("--research-db", default=str(DEFAULT_RESEARCH_DB))
    parser.add_argument("--telemetry-db", default=str(DEFAULT_TELEMETRY_DB))
    parser.add_argument(
        "--telemetry-source",
        choices=("local", "aws"),
        default="aws" if aws_observability_enabled() else "local",
        help="Read model runtime telemetry from local SQLite or centralized AWS CloudWatch Logs.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Build aggregate runtime telemetry and analyze it.")
    start.add_argument("--execution-id", default=None)

    status = subparsers.add_parser("status", help="Read stored Runtime Assurance without a model call.")
    status.add_argument("--execution-id", required=True)
    return parser


def _provider() -> OpenAIRuntimeAssuranceProvider:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required to start Runtime Assurance agents")
    return OpenAIRuntimeAssuranceProvider()


def _snapshot(args: argparse.Namespace) -> dict[str, object]:
    sources = (
        RuntimeStoreSource(args.execution_db, "generic_graph"),
        RuntimeStoreSource(args.research_db, "research"),
    )
    if args.telemetry_source == "local":
        return RuntimeAssuranceSnapshotBuilder(sources, model_telemetry_path=args.telemetry_db).build()

    base = RuntimeAssuranceSnapshotBuilder(sources).build()
    cloud_runtime = CloudWatchRuntimeTelemetrySource().read()
    return apply_cloudwatch_runtime_to_snapshot(base, cloud_runtime)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = GraphExecutionStore(args.execution_db)
    try:
        if args.command == "start":
            execution = start_runtime_assurance(
                provider=_provider(),
                execution_store=store,
                execution_id=args.execution_id or f"runtime-assurance-{uuid.uuid4().hex[:12]}",
                snapshot=_snapshot(args),
            )
        else:
            execution, _ = store.load_execution(args.execution_id)
            if execution.graph_id != "runtime-assurance":
                raise ValueError("stored execution is not Runtime Assurance")
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps(runtime_assurance_summary(execution), ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if execution.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
