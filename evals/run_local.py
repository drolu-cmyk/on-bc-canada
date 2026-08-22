#!/usr/bin/env python3
"""Run the small live agent-behaviour eval set against real platform graphs.

This command makes OpenAI API calls. It is local-only and never runs in CI.
Results persist grader outcomes and model-input hashes, not raw model inputs.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.fixtures import build_career_fixture, build_employer_fixture, build_learner_fixture
from evals.graders import Grade, grade_case
from runtime.career_mobility_runner import start_career_mobility
from runtime.employer_workforce_runner import start_employer_workforce_analysis
from runtime.learner_execution_runner import start_learner_assessment
from runtime.openai_career_mobility_provider import OpenAICareerMobilityProvider
from runtime.openai_employer_workforce_provider import OpenAIEmployerWorkforceProvider
from runtime.openai_learner_provider import OpenAILearnerSupportProvider


CASES_PATH = Path(__file__).with_name("cases.jsonl")
RESULTS_DIR = Path(__file__).with_name("results")
RESULT_PATH = RESULTS_DIR / "latest.json"


class RecordingRunner:
    """Capture model-call metadata while delegating to the real Agents SDK Runner."""

    def __init__(self) -> None:
        from agents import Runner

        self._runner = Runner
        self.calls: list[dict[str, Any]] = []

    def run_sync(self, agent: Any, input: str, **kwargs: Any) -> Any:
        self.calls.append(
            {
                "agent": getattr(agent, "name", "unknown"),
                "input": input,
                "max_turns": kwargs.get("max_turns"),
            }
        )
        return self._runner.run_sync(agent, input, **kwargs)

    def safe_manifest(self) -> list[dict[str, Any]]:
        return [
            {
                "agent": item["agent"],
                "max_turns": item["max_turns"],
                "input_sha256": hashlib.sha256(item["input"].encode("utf-8")).hexdigest(),
            }
            for item in self.calls
        ]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line_number, raw in enumerate(CASES_PATH.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid eval case JSON at line {line_number}: {exc}") from exc
    return cases


def _case_result(case: dict[str, Any], execution: Any, runner: RecordingRunner, private_values: tuple[str, ...]) -> dict[str, Any]:
    grades = grade_case(execution, case, runner.calls, private_values)
    return {
        "case_id": case["case_id"],
        "graph": case["graph"],
        "passed": all(item.passed for item in grades),
        "execution": {
            "graph_id": execution.graph_id,
            "graph_version": execution.graph_version,
            "status": execution.status,
            "current_node": execution.current_node,
            "failure": execution.failure,
        },
        "grades": [item.as_dict() for item in grades],
        "model_calls": runner.safe_manifest(),
    }


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    runner = RecordingRunner()
    with tempfile.TemporaryDirectory(prefix=f"on-bc-eval-{case['case_id']}-") as tmp:
        root = Path(tmp)
        try:
            if case["graph"] == "learner_execution":
                fixture = build_learner_fixture(root)
                provider = OpenAILearnerSupportProvider(runner=runner, max_turns=6)
                execution = start_learner_assessment(
                    provider=provider,
                    progress_store=fixture.learner_store,
                    capability_store=fixture.capability_store,
                    execution_store=fixture.execution_store,
                    execution_id=f"eval-{case['case_id']}",
                    submission_id=fixture.submission_id,
                )
                return _case_result(case, execution, runner, fixture.private_values)

            if case["graph"] == "career_mobility":
                fixture = build_career_fixture(root)
                provider = OpenAICareerMobilityProvider(runner=runner, max_turns=6)
                execution = start_career_mobility(
                    provider=provider,
                    learner_store=fixture.learner_store,
                    capability_store=fixture.capability_store,
                    work_store=fixture.work_store,
                    execution_store=fixture.execution_store,
                    execution_id=f"eval-{case['case_id']}",
                    instance_id=fixture.instance_id,
                )
                return _case_result(case, execution, runner, fixture.private_values)

            if case["graph"] == "employer_workforce":
                fixture = build_employer_fixture(root)
                provider = OpenAIEmployerWorkforceProvider(runner=runner, max_turns=7)
                execution = start_employer_workforce_analysis(
                    provider=provider,
                    execution_store=fixture.execution_store,
                    execution_id=f"eval-{case['case_id']}",
                    request=fixture.request,
                )
                return _case_result(case, execution, runner, fixture.private_values)

            raise ValueError(f"unsupported eval graph: {case['graph']}")
        except Exception as exc:
            grade = Grade("execution_exception", False, f"{type(exc).__name__}: {exc}")
            return {
                "case_id": case.get("case_id", "unknown"),
                "graph": case.get("graph", "unknown"),
                "passed": False,
                "execution": None,
                "grades": [grade.as_dict()],
                "model_calls": runner.safe_manifest(),
            }


def main() -> int:
    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is required for live agent-behaviour evals.", file=sys.stderr)
        return 2

    cases = load_cases()
    results = [run_case(case) for case in cases]
    payload = {
        "suite": "canada-agent-behaviour-v1",
        "ran_at": _utc_now(),
        "case_count": len(results),
        "passed": all(item["passed"] for item in results),
        "models": {
            "learner": os.getenv("SOZOROCK_LEARNER_MODEL", "gpt-5.6-sol"),
            "career": os.getenv("SOZOROCK_CAREER_MODEL", "gpt-5.6-sol"),
            "employer": os.getenv("SOZOROCK_EMPLOYER_MODEL", "gpt-5.6-sol"),
        },
        "cases": results,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
