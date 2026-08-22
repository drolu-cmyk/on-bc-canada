"""Typed OpenAI workers for learner mission review and evidence assessment.

Workers receive only the supplied mission evidence package. They have no web,
learner-record mutation, or credential tools. AI use by a learner is not itself a
failure; the workers assess whether the submitted evidence demonstrates the
required capability and whether the learner can defend the work.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field


class SubmissionReviewOutput(BaseModel):
    status: Literal["ready", "action_recommended"]
    strengths: list[str] = Field(default_factory=list, max_length=12)
    gaps: list[str] = Field(default_factory=list, max_length=12)
    feedback: list[str] = Field(default_factory=list, max_length=15)
    learner_actions: list[str] = Field(default_factory=list, max_length=12)


class EvidenceFinding(BaseModel):
    capability_id: str
    standard_id: str
    verdict: Literal["meets", "partially_meets", "does_not_meet", "insufficient_evidence"]
    rationale: str
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)
    confidence: float = Field(ge=0.0, le=1.0)


class EvidenceAssessmentOutput(BaseModel):
    findings: list[EvidenceFinding] = Field(min_length=1, max_length=20)
    overall_note: str


class AssessmentChallengeOutput(BaseModel):
    status: Literal["clear", "concern"]
    concerns: list[str] = Field(default_factory=list, max_length=12)
    challenge_questions: list[str] = Field(default_factory=list, max_length=8)
    note: str


class RunnerLike(Protocol):
    def run_sync(self, agent: Any, input: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class LearnerAssessmentAgentSet:
    review: Any
    assessment: Any
    challenge: Any


def _input(task: str, payload: dict[str, Any]) -> str:
    return f"{task}\n\nINPUT_JSON\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def build_learner_assessment_agents(model: str | None = None) -> LearnerAssessmentAgentSet:
    from agents import Agent

    model_name = model or os.getenv("SOZOROCK_ASSESSMENT_MODEL", "gpt-5.6-sol")
    shared = (
        "Assess only the supplied mission, evidence standards, artifact references, and evidence material. Do not infer work that is not present. "
        "AI-assisted work is allowed; do not penalize a learner merely for using AI. The question is whether the evidence demonstrates understanding, judgment, and the required work. "
        "Do not use writing polish as a proxy for technical capability unless the evidence standard explicitly requires communication quality. "
        "Do not issue a credential, accept capability evidence, change a learner record, or invent a score. Human acceptance happens outside the model layer. "
    )

    review = Agent(
        name="Submission Review Agent",
        model=model_name,
        instructions=shared + (
            "Give concise formative feedback before final evidence judgment. Identify demonstrated strengths, missing reasoning, unsupported conclusions, unclear evidence, and concrete learner actions. "
            "Use action_recommended only when a substantive improvement is needed; otherwise use ready."
        ),
        output_type=SubmissionReviewOutput,
    )
    assessment = Agent(
        name="Capability Evidence Assessment Agent",
        model=model_name,
        instructions=shared + (
            "Assess every mission evidence requirement separately. Preserve the exact capability_id and standard_id supplied. Use meets only when the evidence demonstrates the standard. "
            "Use partially_meets, does_not_meet, or insufficient_evidence when appropriate. Cite only supplied evidence references in evidence_refs and explain the judgment in plain technical language."
        ),
        output_type=EvidenceAssessmentOutput,
    )
    challenge = Agent(
        name="Evidence Challenge Agent",
        model=model_name,
        instructions=shared + (
            "Try to falsify an overly generous assessment. Look for contradictions between artifacts and explanations, missing causal reasoning, unsupported tool output, inability to explain decisions, or evidence that does not survive a changed scenario. "
            "Do not treat AI use as a concern by itself. Return concern only when a material evidence weakness remains."
        ),
        output_type=AssessmentChallengeOutput,
    )
    return LearnerAssessmentAgentSet(review, assessment, challenge)


class OpenAILearnerAssessmentProvider:
    def __init__(
        self,
        agents: LearnerAssessmentAgentSet | None = None,
        runner: RunnerLike | None = None,
        *,
        max_turns: int = 8,
    ) -> None:
        self.agents = agents or build_learner_assessment_agents()
        if runner is None:
            from agents import Runner

            runner = Runner
        self.runner = runner
        self.max_turns = max_turns

    @staticmethod
    def normalize(request: dict[str, Any]) -> dict[str, Any]:
        submission = request.get("submission")
        standards = request.get("standards")
        if not isinstance(submission, dict) or not submission.get("submission_id"):
            raise ValueError("assessment request requires a learner submission")
        if not isinstance(standards, list) or not standards:
            raise ValueError("assessment request requires evidence standards")
        requirements = submission.get("mission_requirements", [])
        required_pairs = {(item.get("capability_id"), item.get("standard_id")) for item in requirements}
        standard_pairs = {(item.get("capability_id"), item.get("standard_id")) for item in standards}
        if not required_pairs or not required_pairs.issubset(standard_pairs):
            raise ValueError("assessment standards do not cover the mission requirements")
        normalized = {
            "submission": submission,
            "standards": standards,
            "mission": request.get("mission", {}),
            "evidence_material": request.get("evidence_material", []),
        }
        return normalized

    def _run(self, agent: Any, task: str, request: dict[str, Any], expected: type[BaseModel]) -> dict[str, Any]:
        result = self.runner.run_sync(agent, _input(task, {"assessment_request": request}), max_turns=self.max_turns)
        output = result.final_output
        if not isinstance(output, expected):
            raise TypeError(f"agent {getattr(agent, 'name', 'unknown')} returned untyped output")
        return output.model_dump()

    def review_submission(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._run(
            self.agents.review,
            "Review the mission submission for formative feedback without accepting capability evidence.",
            request,
            SubmissionReviewOutput,
        )

    def assess_evidence(self, request: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
        payload = dict(request)
        payload["formative_review"] = review
        return self._run(
            self.agents.assessment,
            "Assess each mission evidence requirement against its supplied evidence standard.",
            payload,
            EvidenceAssessmentOutput,
        )

    def challenge_assessment(
        self,
        request: dict[str, Any],
        review: dict[str, Any],
        assessment: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(request)
        payload["formative_review"] = review
        payload["evidence_assessment"] = assessment
        return self._run(
            self.agents.challenge,
            "Challenge the evidence assessment and surface any material weakness that would make acceptance unsafe.",
            payload,
            AssessmentChallengeOutput,
        )
