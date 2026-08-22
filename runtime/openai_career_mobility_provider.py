"""Typed learner-facing Career Mobility workers.

Workers receive deidentified, human-accepted capability evidence plus deterministic
role alignment from Work Intelligence. They cannot rank people for employers,
predict hiring, apply to jobs, contact employers, or make immigration/licensing
decisions.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from runtime.career_intelligence import CareerModelContext


class CapabilityPositioning(BaseModel):
    capability_id: str
    statement: str
    evidence_boundary: str


class CareerProfileOutput(BaseModel):
    positioning_summary: str
    demonstrated_capabilities: list[CapabilityPositioning] = Field(min_length=1, max_length=20)
    boundary_notes: list[str] = Field(default_factory=list, max_length=6)


class RoleAnalysis(BaseModel):
    role_name: str
    evidence_based_strengths: list[str] = Field(default_factory=list, max_length=12)
    capability_gaps: list[str] = Field(default_factory=list, max_length=12)
    interpretation: str


class RoleTransitionOutput(BaseModel):
    roles: list[RoleAnalysis] = Field(default_factory=list, max_length=12)
    note: str


class EvidenceCard(BaseModel):
    capability_id: str
    standard_id: str
    label: str
    proof_prompt: str


class EvidencePackagingOutput(BaseModel):
    cards: list[EvidenceCard] = Field(min_length=1, max_length=24)
    portfolio_structure: list[str] = Field(min_length=1, max_length=10)
    note: str


class InterviewQuestion(BaseModel):
    role_name: str
    question: str
    capability_ids: list[str] = Field(min_length=1, max_length=6)
    what_to_demonstrate: str


class InterviewPracticeOutput(BaseModel):
    questions: list[InterviewQuestion] = Field(min_length=1, max_length=18)
    practice_method: str


class CareerAction(BaseModel):
    action_type: Literal[
        "practice",
        "learning",
        "portfolio_preparation",
        "interview_practice",
        "employer_research",
    ]
    action: str
    related_role_names: list[str] = Field(default_factory=list, max_length=6)
    related_capability_ids: list[str] = Field(default_factory=list, max_length=8)


class CareerActionPlanOutput(BaseModel):
    actions: list[CareerAction] = Field(min_length=1, max_length=12)
    sequencing_note: str
    boundary_note: str


class RunnerLike(Protocol):
    def run_sync(self, agent: Any, input: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class CareerAgentSet:
    profile_agent: Any
    role_transition_agent: Any
    evidence_packaging_agent: Any
    interview_practice_agent: Any
    action_plan_agent: Any


def build_career_agents(model: str | None = None) -> CareerAgentSet:
    """Construct Career Mobility workers without performing an API call."""

    from agents import Agent

    model_name = model or os.getenv("SOZOROCK_CAREER_MODEL", "gpt-5.6-sol")
    common_boundary = (
        "Use only the supplied deidentified accepted-capability and Work Intelligence context. "
        "Do not infer employment history, identity, education outside the supplied records, protected characteristics, immigration status, "
        "licensing status, salary entitlement, or hiring probability. Evidence alignment is not employability or likelihood of hire. "
        "Do not recommend automatic job applications, employer contact, or external publication."
    )
    profile = Agent(
        name="Career Profile Agent",
        model=model_name,
        instructions=(
            common_boundary
            + " Create a restrained learner-facing positioning summary from capabilities that have human-accepted evidence. "
            "Every demonstrated capability item must use an accepted capability_id from INPUT_JSON. State the evidence boundary clearly; "
            "do not claim to have inspected raw artifacts."
        ),
        output_type=CareerProfileOutput,
    )
    transitions = Agent(
        name="Role Transition Agent",
        model=model_name,
        instructions=(
            common_boundary
            + " Interpret only the role_alignments supplied by deterministic Work Intelligence. Analyze strengths and gaps for those roles only. "
            "Do not invent additional target roles and do not translate evidence_alignment into a hiring score."
        ),
        output_type=RoleTransitionOutput,
    )
    packaging = Agent(
        name="Career Evidence Packaging Agent",
        model=model_name,
        instructions=(
            common_boundary
            + " Build a learner-facing evidence packaging structure using only accepted capability_id and standard_id pairs. "
            "You do not receive raw artifacts. Create prompts that help the learner explain evidence accurately without fabricating outcomes, clients, employers, or metrics."
        ),
        output_type=EvidencePackagingOutput,
    )
    interview = Agent(
        name="Interview Practice Agent",
        model=model_name,
        instructions=(
            common_boundary
            + " Generate practice questions only for supplied role names and accepted capability IDs. Questions should test reasoning, evidence, tradeoffs, "
            "failure handling, and technical judgment rather than encourage scripted claims."
        ),
        output_type=InterviewPracticeOutput,
    )
    action = Agent(
        name="Career Action Agent",
        model=model_name,
        instructions=(
            common_boundary
            + " Produce a practical next-action sequence for the learner. Allowed action types are practice, learning, portfolio preparation, interview practice, "
            "and employer research. Employer research means learning about roles or organizations; it does not include contacting, applying, messaging, or publishing."
        ),
        output_type=CareerActionPlanOutput,
    )
    return CareerAgentSet(profile, transitions, packaging, interview, action)


class OpenAICareerMobilityProvider:
    def __init__(
        self,
        agents: CareerAgentSet | None = None,
        runner: RunnerLike | None = None,
        *,
        max_turns: int = 6,
    ) -> None:
        self.agents = agents or build_career_agents()
        if runner is None:
            from agents import Runner

            runner = Runner
        self.runner = runner
        self.max_turns = max_turns

    @staticmethod
    def _message(task: str, context: CareerModelContext) -> str:
        return task + "\n\nINPUT_JSON\n" + json.dumps(context.as_payload(), ensure_ascii=False, sort_keys=True)

    def _run(self, agent: Any, task: str, context: CareerModelContext, expected: type[BaseModel]) -> BaseModel:
        result = self.runner.run_sync(
            agent,
            self._message(task, context),
            max_turns=self.max_turns,
        )
        output = result.final_output
        if not isinstance(output, expected):
            raise TypeError(f"career agent {getattr(agent, 'name', 'unknown')} returned untyped output")
        return output

    def profile(self, context: CareerModelContext) -> dict[str, Any]:
        return self._run(
            self.agents.profile_agent,
            "Describe the learner's demonstrated capability evidence without overstating it.",
            context,
            CareerProfileOutput,
        ).model_dump()

    def analyze_role_transitions(self, context: CareerModelContext) -> dict[str, Any]:
        return self._run(
            self.agents.role_transition_agent,
            "Interpret the deterministic role evidence alignments and capability gaps.",
            context,
            RoleTransitionOutput,
        ).model_dump()

    def package_evidence(self, context: CareerModelContext) -> dict[str, Any]:
        return self._run(
            self.agents.evidence_packaging_agent,
            "Create a portfolio evidence structure without accessing raw learner artifacts.",
            context,
            EvidencePackagingOutput,
        ).model_dump()

    def prepare_interview_practice(self, context: CareerModelContext) -> dict[str, Any]:
        return self._run(
            self.agents.interview_practice_agent,
            "Create evidence-grounded interview practice for the supplied roles.",
            context,
            InterviewPracticeOutput,
        ).model_dump()

    def plan_actions(self, context: CareerModelContext) -> dict[str, Any]:
        return self._run(
            self.agents.action_plan_agent,
            "Sequence learner-controlled next actions without external execution.",
            context,
            CareerActionPlanOutput,
        ).model_dump()
