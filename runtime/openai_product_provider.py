"""Typed OpenAI workers for the Product Development Graph.

These agents produce bounded product and release-analysis artifacts. They have no
production tools, deployment authority, spending authority, or external messaging
authority. The Product Development Graph owns sequencing and release review.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field


ReviewStatus = Literal["pass", "warn", "block"]


class ProductAnalysisOutput(BaseModel):
    problem: str
    primary_users: list[str] = Field(min_length=1, max_length=8)
    user_jobs: list[str] = Field(min_length=1, max_length=12)
    desired_outcome: str
    in_scope: list[str] = Field(min_length=1, max_length=15)
    out_of_scope: list[str] = Field(default_factory=list, max_length=15)
    success_signals: list[str] = Field(min_length=1, max_length=12)
    assumptions_to_test: list[str] = Field(default_factory=list, max_length=10)


class ExperienceAnalysisOutput(BaseModel):
    key_tasks: list[str] = Field(min_length=1, max_length=15)
    journey_steps: list[str] = Field(min_length=1, max_length=20)
    friction_risks: list[str] = Field(default_factory=list, max_length=12)
    information_architecture: list[str] = Field(min_length=1, max_length=20)
    research_gaps: list[str] = Field(default_factory=list, max_length=10)


class InterfaceSurface(BaseModel):
    surface: str
    purpose: str
    hierarchy: list[str] = Field(min_length=1, max_length=12)
    key_components: list[str] = Field(min_length=1, max_length=20)
    states: list[str] = Field(default_factory=list, max_length=15)


class InterfaceDesignOutput(BaseModel):
    design_direction: str
    surfaces: list[InterfaceSurface] = Field(min_length=1, max_length=12)
    interaction_rules: list[str] = Field(min_length=1, max_length=15)
    responsive_rules: list[str] = Field(default_factory=list, max_length=12)
    design_system_needs: list[str] = Field(default_factory=list, max_length=12)


class ReviewOutput(BaseModel):
    status: ReviewStatus
    summary: str
    release_blockers: list[str] = Field(default_factory=list, max_length=12)
    warnings: list[str] = Field(default_factory=list, max_length=12)
    recommendations: list[str] = Field(default_factory=list, max_length=15)


class EngineeringPlanOutput(BaseModel):
    architecture_summary: str
    components: list[str] = Field(min_length=1, max_length=20)
    data_changes: list[str] = Field(default_factory=list, max_length=15)
    api_changes: list[str] = Field(default_factory=list, max_length=15)
    agent_changes: list[str] = Field(default_factory=list, max_length=15)
    migration_risks: list[str] = Field(default_factory=list, max_length=12)
    implementation_slices: list[str] = Field(min_length=1, max_length=20)
    rollback_strategy: str


class RunnerLike(Protocol):
    def run_sync(self, agent: Any, input: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class ProductAgentSet:
    product: Any
    experience: Any
    interface: Any
    copy: Any
    brand: Any
    engineering: Any
    cloud: Any
    security: Any
    accessibility: Any
    quality: Any


def _input(task: str, payload: dict[str, Any]) -> str:
    return f"{task}\n\nINPUT_JSON\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def build_product_agents(model: str | None = None) -> ProductAgentSet:
    from agents import Agent

    model_name = model or os.getenv("SOZOROCK_PRODUCT_MODEL", "gpt-5.6-sol")
    shared = (
        "Work only from the supplied evidence and constraints. Do not invent user research, performance data, partnerships, approvals, or outcomes. "
        "This is a Canadian technical workforce platform that is free at launch and is not presented as a college, university, or degree-granting institution. "
        "Use precise natural language. Avoid generic AI marketing phrases, filler, and unsupported claims. "
    )

    product = Agent(
        name="Product Agent",
        model=model_name,
        instructions=shared + (
            "Turn the request into a precise product problem. Identify primary users, jobs to be done, scope, non-scope, measurable success signals, "
            "and assumptions that still need evidence. Do not jump directly to screens or implementation."
        ),
        output_type=ProductAnalysisOutput,
    )
    experience = Agent(
        name="Experience Agent",
        model=model_name,
        instructions=shared + (
            "Design the user experience around real tasks. Define the smallest coherent journey and information architecture, identify friction and research gaps, "
            "and avoid conventional LMS navigation when the work can be expressed more directly."
        ),
        output_type=ExperienceAnalysisOutput,
    )
    interface = Agent(
        name="UI Design Agent",
        model=model_name,
        instructions=shared + (
            "Translate the approved product and experience logic into a distinctive interface specification. Define surface purpose, visual hierarchy, components, states, "
            "responsive behavior, and design-system needs. Avoid generic dashboard cards, decorative AI motifs, and dense school-portal layouts."
        ),
        output_type=InterfaceDesignOutput,
    )
    copy = Agent(
        name="Copy Agent",
        model=model_name,
        instructions=shared + (
            "Review product and interface language for clarity, Canadian context, hierarchy, conversion value, and evidence. Block unsupported claims, school-like terminology, "
            "generic AI phrases, vague calls to action, or copy that says more than the product can currently prove."
        ),
        output_type=ReviewOutput,
    )
    brand = Agent(
        name="Brand Agent",
        model=model_name,
        instructions=shared + (
            "Review the interface and copy for a coherent, credible applied-technology workforce brand. Block visual or verbal choices that make the product look like a generic LMS, "
            "a conventional school, a template startup, or an unsubstantiated AI product. Preserve restraint, hierarchy, accessibility, and Canadian context."
        ),
        output_type=ReviewOutput,
    )
    engineering = Agent(
        name="Engineering Agent",
        model=model_name,
        instructions=shared + (
            "Translate the product and interface contract into small implementation slices. Identify application components, data and API changes, agent-runtime changes, migration risks, "
            "and rollback strategy. Prefer deterministic software for deterministic work and model reasoning only where judgment is required."
        ),
        output_type=EngineeringPlanOutput,
    )
    cloud = Agent(
        name="Cloud Agent",
        model=model_name,
        instructions=shared + (
            "Review the engineering plan for AWS-first deployment, isolation, least privilege, observability, rollback, cost exposure, queues, persistence, secrets, and operational failure modes. "
            "Block changes that require shared privileged credentials, unbounded model spend, unobservable background work, or unsafe production mutation."
        ),
        output_type=ReviewOutput,
    )
    security = Agent(
        name="Security Agent",
        model=model_name,
        instructions=shared + (
            "Threat-model the engineering and cloud plan. Review authentication, authorization, agent identities, tool permissions, data boundaries, prompt injection, secrets, audit evidence, "
            "dependency risk, and destructive actions. Block any design that gives an agent broader authority than its task requires."
        ),
        output_type=ReviewOutput,
    )
    accessibility = Agent(
        name="Accessibility Agent",
        model=model_name,
        instructions=shared + (
            "Review the experience and interface specification for keyboard access, semantic structure, focus order, labels, status communication, contrast, zoom, responsive behavior, reduced motion, "
            "screen-reader interpretation, captions or transcripts where relevant, and low-bandwidth use. Block barriers that prevent core task completion."
        ),
        output_type=ReviewOutput,
    )
    quality = Agent(
        name="Quality Agent",
        model=model_name,
        instructions=shared + (
            "Create release-focused quality assurance from the product, engineering, security, and accessibility evidence. Cover functional acceptance, regression, browser behavior, agent evaluations, "
            "permission tests, failure recovery, observability, and negative cases. Block release when a critical user task, authority boundary, or safety condition lacks a test."
        ),
        output_type=ReviewOutput,
    )
    return ProductAgentSet(product, experience, interface, copy, brand, engineering, cloud, security, accessibility, quality)


class OpenAIProductDevelopmentProvider:
    def __init__(self, agents: ProductAgentSet | None = None, runner: RunnerLike | None = None, *, max_turns: int = 8) -> None:
        self.agents = agents or build_product_agents()
        if runner is None:
            from agents import Runner

            runner = Runner
        self.runner = runner
        self.max_turns = max_turns

    @staticmethod
    def normalize(request: dict[str, Any]) -> dict[str, Any]:
        problem = " ".join(str(request.get("problem", "")).split())
        if not problem:
            raise ValueError("product request requires a problem statement")
        normalized = dict(request)
        normalized["problem"] = problem
        normalized.setdefault("market", "Canada")
        normalized.setdefault("release_authority", "human")
        return normalized

    def _run(self, agent: Any, task: str, payload: dict[str, Any], expected: type[BaseModel]) -> dict[str, Any]:
        result = self.runner.run_sync(agent, _input(task, payload), max_turns=self.max_turns)
        output = result.final_output
        if not isinstance(output, expected):
            raise TypeError(f"agent {getattr(agent, 'name', 'unknown')} returned untyped output")
        return output.model_dump()

    def analyze_product(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._run(self.agents.product, "Analyze the product problem before solution design.", {"request": request}, ProductAnalysisOutput)

    def analyze_experience(self, request: dict[str, Any], product: dict[str, Any]) -> dict[str, Any]:
        return self._run(self.agents.experience, "Design the task-centered user experience.", {"request": request, "product": product}, ExperienceAnalysisOutput)

    def design_interface(self, request: dict[str, Any], product: dict[str, Any], experience: dict[str, Any]) -> dict[str, Any]:
        return self._run(self.agents.interface, "Create the interface design contract.", {"request": request, "product": product, "experience": experience}, InterfaceDesignOutput)

    def review_copy(self, request: dict[str, Any], product: dict[str, Any], interface: dict[str, Any]) -> dict[str, Any]:
        return self._run(self.agents.copy, "Review the product and interface copy boundary.", {"request": request, "product": product, "interface": interface}, ReviewOutput)

    def review_brand(self, request: dict[str, Any], interface: dict[str, Any], copy: dict[str, Any]) -> dict[str, Any]:
        return self._run(self.agents.brand, "Review brand coherence and distinctiveness.", {"request": request, "interface": interface, "copy": copy}, ReviewOutput)

    def plan_engineering(self, request: dict[str, Any], product: dict[str, Any], experience: dict[str, Any], interface: dict[str, Any]) -> dict[str, Any]:
        return self._run(
            self.agents.engineering,
            "Create the implementation contract without performing repository changes.",
            {"request": request, "product": product, "experience": experience, "interface": interface},
            EngineeringPlanOutput,
        )

    def review_cloud(self, request: dict[str, Any], engineering: dict[str, Any]) -> dict[str, Any]:
        return self._run(self.agents.cloud, "Review cloud readiness and operational risk.", {"request": request, "engineering": engineering}, ReviewOutput)

    def review_security(self, request: dict[str, Any], engineering: dict[str, Any], cloud: dict[str, Any]) -> dict[str, Any]:
        return self._run(self.agents.security, "Review security and agent authority boundaries.", {"request": request, "engineering": engineering, "cloud": cloud}, ReviewOutput)

    def review_accessibility(self, request: dict[str, Any], experience: dict[str, Any], interface: dict[str, Any]) -> dict[str, Any]:
        return self._run(self.agents.accessibility, "Review accessibility of the core user tasks.", {"request": request, "experience": experience, "interface": interface}, ReviewOutput)

    def plan_quality(
        self,
        request: dict[str, Any],
        product: dict[str, Any],
        engineering: dict[str, Any],
        security: dict[str, Any],
        accessibility: dict[str, Any],
    ) -> dict[str, Any]:
        return self._run(
            self.agents.quality,
            "Create the release quality and negative-test contract.",
            {
                "request": request,
                "product": product,
                "engineering": engineering,
                "security": security,
                "accessibility": accessibility,
            },
            ReviewOutput,
        )
