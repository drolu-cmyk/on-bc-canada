#!/usr/bin/env python3
"""Validate live-eval contracts and synthetic fixtures without making model calls."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.fixtures import build_career_fixture, build_employer_fixture, build_learner_fixture
from evals.run_local import load_cases
from runtime.career_intelligence import CareerIntelligenceBuilder
from runtime.openai_career_mobility_provider import build_career_agents
from runtime.openai_employer_workforce_provider import build_employer_workforce_agents
from runtime.openai_learner_provider import build_learner_agents


SUPPORTED = {"learner_execution", "career_mobility", "employer_workforce"}
COMMON_REQUIRED = {"case_id", "graph", "description", "expected"}


def _require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _validate_case(case: dict[str, Any], errors: list[str]) -> None:
    missing = COMMON_REQUIRED - set(case)
    _require(not missing, f"{case.get('case_id', '<unknown>')}: missing fields {sorted(missing)}", errors)
    graph = case.get("graph")
    _require(graph in SUPPORTED, f"{case.get('case_id', '<unknown>')}: unsupported graph {graph!r}", errors)
    _require(bool(str(case.get("description", "")).strip()), f"{case.get('case_id', '<unknown>')}: description required", errors)
    expected = case.get("expected")
    _require(isinstance(expected, dict), f"{case.get('case_id', '<unknown>')}: expected object required", errors)
    if not isinstance(expected, dict):
        return
    _require(expected.get("execution_status") in {"completed", "waiting_approval"}, f"{case.get('case_id')}: invalid execution_status", errors)
    if graph == "learner_execution":
        _require(expected.get("current_node") == "human_assessment", f"{case.get('case_id')}: learner case must target human_assessment", errors)
        _require(expected.get("authority") == "A3", f"{case.get('case_id')}: learner case must require A3", errors)
        _require(expected.get("model_call_count") == 3, f"{case.get('case_id')}: learner case expects three model workers", errors)
    elif graph == "career_mobility":
        _require(expected.get("career_status") == "guidance_ready", f"{case.get('case_id')}: career case must expect guidance_ready", errors)
        _require(expected.get("model_call_count") == 5, f"{case.get('case_id')}: career case expects five model workers", errors)
        allowed = set(expected.get("allowed_action_types", []))
        _require(
            allowed == {"practice", "learning", "portfolio_preparation", "interview_practice", "employer_research"},
            f"{case.get('case_id')}: career action allowlist does not match runtime boundary",
            errors,
        )
    elif graph == "employer_workforce":
        _require(set(expected.get("allowed_employer_status", [])) == {"analysis_ready", "no_change"}, f"{case.get('case_id')}: employer terminal states must allow analysis_ready and no_change", errors)
        _require(expected.get("model_call_count_min") == 2, f"{case.get('case_id')}: employer minimum call count must be two", errors)
        _require(expected.get("model_call_count_max") == 7, f"{case.get('case_id')}: employer maximum call count must be seven", errors)


def _validate_fixtures(errors: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="on-bc-eval-static-") as tmp:
        root = Path(tmp)
        learner = build_learner_fixture(root / "learner")
        submission = learner.learner_store.get_submission(learner.submission_id)
        _require(submission["status"] == "submitted", "learner fixture must stop at a newly submitted mission", errors)
        _require(len(submission["mission_requirements"]) == 2, "learner fixture must contain two reviewed evidence requirements", errors)

        career = build_career_fixture(root / "career")
        context = CareerIntelligenceBuilder(
            learner_store=career.learner_store,
            capability_store=career.capability_store,
            work_store=career.work_store,
        ).build(career.instance_id)
        _require(len(context.accepted_capabilities) == 2, "career fixture must contain two human-accepted capabilities", errors)
        career_text = repr(context.as_payload())
        leaked = [value for value in career.private_values if value in career_text]
        _require(not leaked, f"career fixture leaked private values into model context: {leaked}", errors)

        employer = build_employer_fixture(root / "employer")
        employer_text = repr(employer.request.as_model_payload())
        leaked = [value for value in employer.private_values if value in employer_text]
        _require(not leaked, f"employer fixture leaked local organization reference into model context: {leaked}", errors)


def main() -> int:
    errors: list[str] = []
    try:
        cases = load_cases()
    except (OSError, ValueError) as exc:
        print(f"Eval harness validation failed: {exc}", file=sys.stderr)
        return 1

    ids = [case.get("case_id") for case in cases]
    _require(len(cases) == 3, f"initial eval suite must contain exactly three cases; observed {len(cases)}", errors)
    _require(len(ids) == len(set(ids)), "eval case IDs must be unique", errors)
    _require({case.get("graph") for case in cases} == SUPPORTED, "initial eval suite must contain one case for each high-risk graph", errors)
    for case in cases:
        _validate_case(case, errors)

    try:
        _validate_fixtures(errors)
        learner_agents = build_learner_agents(model="gpt-5.6-sol")
        career_agents = build_career_agents(model="gpt-5.6-sol")
        employer_agents = build_employer_workforce_agents(model="gpt-5.6-sol")
        _require(all(not agent.tools for agent in (learner_agents.coach_agent, learner_agents.progress_agent, learner_agents.review_preparation_agent)), "learner eval workers must remain tool-free", errors)
        _require(all(not agent.tools for agent in (career_agents.profile_agent, career_agents.role_transition_agent, career_agents.evidence_packaging_agent, career_agents.interview_practice_agent, career_agents.action_plan_agent)), "career eval workers must remain tool-free", errors)
        _require(all(not agent.tools for agent in (employer_agents.workflow_agent, employer_agents.ai_opportunity_agent, employer_agents.workforce_impact_agent, employer_agents.capability_demand_agent, employer_agents.adoption_risk_agent, employer_agents.pilot_design_agent, employer_agents.measurement_agent)), "employer eval workers must remain tool-free", errors)
    except Exception as exc:
        errors.append(f"static fixture or SDK construction failed: {type(exc).__name__}: {exc}")

    if errors:
        print("Eval harness validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Agent-behaviour eval contracts passed for {len(cases)} cases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
