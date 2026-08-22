"""Command interface for organization-level Employer Workforce analysis."""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from runtime.employer_workforce_context import AggregateMetric, EmployerWorkforceRequest, WorkTask
from runtime.employer_workforce_runner import employer_workforce_summary, start_employer_workforce_analysis
from runtime.execution_store_factory import create_execution_store
from runtime.openai_employer_workforce_provider import OpenAIEmployerWorkforceProvider


DEFAULT_EXECUTION_DB = Path(os.getenv("SOZOROCK_GRAPH_DB", "local-data/graph-executions.sqlite3"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Employer Workforce Graph.")
    parser.add_argument("--execution-db", default=str(DEFAULT_EXECUTION_DB))
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Analyze an organization-level workflow request from JSON.")
    start.add_argument("--request-file", required=True)
    start.add_argument("--execution-id", default=None)

    status = subparsers.add_parser("status", help="Read stored Employer Workforce analysis without a model call.")
    status.add_argument("--execution-id", required=True)
    return parser


def _provider() -> OpenAIEmployerWorkforceProvider:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required to start Employer Workforce agents")
    return OpenAIEmployerWorkforceProvider()


def _load_request(path: str) -> EmployerWorkforceRequest:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return EmployerWorkforceRequest(
        organization_ref=payload["organization_ref"],
        sector=payload["sector"],
        workflow_name=payload["workflow_name"],
        workflow_purpose=payload["workflow_purpose"],
        tasks=tuple(
            WorkTask(
                task_id=item["task_id"],
                description=item["description"],
                role_labels=tuple(item["role_labels"]),
                current_tools=tuple(item.get("current_tools", [])),
                pain_points=tuple(item.get("pain_points", [])),
            )
            for item in payload["tasks"]
        ),
        constraints=tuple(payload.get("constraints", [])),
        baseline_metrics=tuple(
            AggregateMetric(
                metric_id=item["metric_id"],
                description=item["description"],
                value=float(item["value"]),
                unit=item["unit"],
            )
            for item in payload.get("baseline_metrics", [])
        ),
        desired_outcomes=tuple(payload.get("desired_outcomes", [])),
        data_classification=payload.get("data_classification", "operational"),
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = create_execution_store(local_path=args.execution_db)

    try:
        if args.command == "start":
            execution = start_employer_workforce_analysis(
                provider=_provider(),
                execution_store=store,
                execution_id=args.execution_id or f"employer-{uuid.uuid4().hex[:12]}",
                request=_load_request(args.request_file),
            )
        else:
            execution, _ = store.load_execution(args.execution_id)
            if execution.graph_id != "employer-workforce":
                raise ValueError("stored execution is not Employer Workforce analysis")
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps(employer_workforce_summary(execution), ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if execution.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
