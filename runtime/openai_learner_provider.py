"""Typed learner-support workers that never receive raw learner submissions.

The model layer receives only deidentified learning metadata derived from reviewed
program records. Raw artifact references, learner identity, attendance, support
records, credentials, and submission content remain outside model context.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field


class CoachingOutput(BaseModel):
    focus: str
    next_actions: list[str] = Field(min_length=1, max_length=6)
    questions_for_learner: list[str] = Field(default_factory=list, max_length=4)
    note: str


class ProgressOutput(BaseModel):
    status: Literal["on_track", "needs_iteration", "needs_human_learning_support", "ready_for_review"]
    rationale: str
    recommended_next_step: str
    signals: list[str] = Field(default_factory=list, max_length=6)


class ReviewChecklistItem(BaseModel):
    capability_id: str
    standard_id: str
    review_question: str


class ReviewChecklistOutput(BaseModel):
    summary: str
    checklist: list[ReviewChecklistItem] = Field(min_length=1, max_length=20)
    reviewer_cautions: list[str] = Field(default_factory=list, max_length=6)


class RunnerLike(Protocol):
    def run_sync(self, agent: Any, input: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class LearnerAgentSet:
    coach_agent: Any
    progress_agent: Any
    review_preparation_agent: Any


@dataclass(frozen=True)
class LearnerModelContext:
    pathway_id: str
    learning_version: str
    unit_id: str
    unit_kind: str
    unit_title: str
    unit_purpose: str
    attempt_number: int
    unit_status_counts: dict[str, int]
    artifact_types: tuple[str, ...]
    readiness_complete: bool
    readiness_requirements: tuple[dict[str, Any], ...]

    def as_payload(self) -> dict[str, Any]:
        return {
            "pathway_id": self.pathway_id,
            "learning_version": self.learning_version,
            "unit_id": self.unit_id,
            "unit_kind": self.unit_kind,
            "unit_title": self.unit_title,
            "unit_purpose": self.unit_purpose,
            "attempt_number": self.attempt_number,
            "unit_status_counts": dict(self.unit_status_counts),
            "artifact_types": list(self.artifact_types),
            "readiness_complete": self.readiness_complete,
            "readiness_requirements": list(self.readiness_requirements),
        }


def build_learner_agents(model: str | None = None) -> LearnerAgentSet:
    """Construct learner-support workers without making an API call."""

    from agents import Agent

    model_name = model or os.getenv("SOZOROCK_LEARNER_MODEL", "gpt-5.6-sol")
    coach = Agent(
        name="Learning Coach Agent",
        model=model_name,
        instructions=(
            "Help a learner prepare stronger evidence using only the deidentified learning metadata in INPUT_JSON. "
            "Do not claim to have seen the learner's work. Do not infer identity, attendance, support history, disability, health, "
            "immigration status, or other personal circumstances. Give concrete next actions tied to the supplied learning purpose "
            "and evidence-readiness flags. Do not grade, certify, or decide whether capability evidence passes."
        ),
        output_type=CoachingOutput,
    )
    progress = Agent(
        name="Learner Progress Agent",
        model=model_name,
        instructions=(
            "Interpret the supplied deidentified path-progress counts, attempt number, and evidence-readiness metadata. "
            "Recommend the next learning action without making punitive, credential, enrollment, employment, or eligibility decisions. "
            "Use needs_human_learning_support only for ordinary learning support when repeated iteration or progress signals justify it. "
            "Do not infer sensitive personal causes."
        ),
        output_type=ProgressOutput,
    )
    review = Agent(
        name="Human Review Preparation Agent",
        model=model_name,
        instructions=(
            "Prepare a concise checklist for a human assessor from the supplied capability evidence standards. "
            "You do not receive and must not pretend to assess learner submission content. Create questions that help a human verify "
            "the evidence against each supplied standard. Never return a pass/fail judgment, grade, credential decision, or learner ranking."
        ),
        output_type=ReviewChecklistOutput,
    )
    return LearnerAgentSet(coach, progress, review)


class OpenAILearnerSupportProvider:
    def __init__(
        self,
        agents: LearnerAgentSet | None = None,
        runner: RunnerLike | None = None,
        *,
        max_turns: int = 6,
    ) -> None:
        self.agents = agents or build_learner_agents()
        if runner is None:
            from agents import Runner

            runner = Runner
        self.runner = runner
        self.max_turns = max_turns

    @staticmethod
    def _message(task: str, context: LearnerModelContext) -> str:
        payload = context.as_payload()
        forbidden = {
            "learner_ref",
            "learner_id",
            "cohort_id",
            "artifact_refs",
            "submission_id",
            "attendance",
            "support",
            "credential",
            "email",
            "name",
        }
        if forbidden.intersection(payload):
            raise ValueError("learner model context contains a prohibited identity or record field")
        return task + "\n\nINPUT_JSON\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _run(self, agent: Any, task: str, context: LearnerModelContext, expected: type[BaseModel]) -> BaseModel:
        result = self.runner.run_sync(
            agent,
            self._message(task, context),
            max_turns=self.max_turns,
        )
        output = result.final_output
        if not isinstance(output, expected):
            raise TypeError(f"learner agent {getattr(agent, 'name', 'unknown')} returned untyped output")
        return output

    def coach(self, context: LearnerModelContext) -> dict[str, Any]:
        output = self._run(
            self.agents.coach_agent,
            "Provide preparation guidance without grading the learner.",
            context,
            CoachingOutput,
        )
        return output.model_dump()

    def analyze_progress(self, context: LearnerModelContext) -> dict[str, Any]:
        output = self._run(
            self.agents.progress_agent,
            "Recommend the next learning action from deidentified progress signals.",
            context,
            ProgressOutput,
        )
        return output.model_dump()

    def prepare_human_review(self, context: LearnerModelContext) -> dict[str, Any]:
        output = self._run(
            self.agents.review_preparation_agent,
            "Prepare the human evidence-review checklist. Do not judge the evidence.",
            context,
            ReviewChecklistOutput,
        )
        return output.model_dump()
