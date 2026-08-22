"""Typed OpenAI workers for the routed Business Operations Graph.

Workers receive no external-action tools. They analyze or prepare bounded work.
Deterministic graph policy decides whether a result can finish directly or must
stop at A3/A4 human authorization before any separate external execution.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from runtime.business_operations_graph import _ALLOWED_ACTIONS, _ALLOWED_COMBINATIONS, _ALLOWED_WORKSTREAMS


ReviewStatus = Literal["pass", "warn", "block"]


class GrowthOutput(BaseModel):
    status: ReviewStatus
    summary: str
    objective: str
    funnel_stages: list[str] = Field(min_length=1, max_length=12)
    hypotheses: list[str] = Field(default_factory=list, max_length=12)
    experiments: list[str] = Field(default_factory=list, max_length=12)
    measurements: list[str] = Field(default_factory=list, max_length=12)
    evidence_needed: list[str] = Field(default_factory=list, max_length=12)
    blockers: list[str] = Field(default_factory=list, max_length=10)
    warnings: list[str] = Field(default_factory=list, max_length=10)


class MarketingOutput(BaseModel):
    status: ReviewStatus
    summary: str
    audience: list[str] = Field(min_length=1, max_length=8)
    message: str
    proof_points: list[str] = Field(default_factory=list, max_length=12)
    claims_needing_evidence: list[str] = Field(default_factory=list, max_length=12)
    channels: list[str] = Field(default_factory=list, max_length=10)
    content_assets: list[str] = Field(default_factory=list, max_length=12)
    conversion_action: str
    blockers: list[str] = Field(default_factory=list, max_length=10)
    warnings: list[str] = Field(default_factory=list, max_length=10)


class PartnershipOutput(BaseModel):
    status: ReviewStatus
    summary: str
    partner_profile: str
    mutual_value: list[str] = Field(min_length=1, max_length=12)
    qualification_signals: list[str] = Field(default_factory=list, max_length=12)
    evidence_needed: list[str] = Field(default_factory=list, max_length=12)
    preparation_steps: list[str] = Field(default_factory=list, max_length=12)
    outreach_outline: list[str] = Field(default_factory=list, max_length=10)
    blockers: list[str] = Field(default_factory=list, max_length=10)
    warnings: list[str] = Field(default_factory=list, max_length=10)


class OperationsOutput(BaseModel):
    status: ReviewStatus
    summary: str
    process: list[str] = Field(min_length=1, max_length=20)
    bottlenecks: list[str] = Field(default_factory=list, max_length=12)
    automation_candidates: list[str] = Field(default_factory=list, max_length=12)
    human_controls: list[str] = Field(default_factory=list, max_length=12)
    service_measures: list[str] = Field(default_factory=list, max_length=12)
    data_boundaries: list[str] = Field(default_factory=list, max_length=12)
    blockers: list[str] = Field(default_factory=list, max_length=10)
    warnings: list[str] = Field(default_factory=list, max_length=10)


class FinanceOutput(BaseModel):
    status: ReviewStatus
    summary: str
    question: str
    supplied_metrics_used: list[str] = Field(default_factory=list, max_length=20)
    assumptions: list[str] = Field(default_factory=list, max_length=15)
    cost_drivers: list[str] = Field(default_factory=list, max_length=15)
    scenarios: list[str] = Field(default_factory=list, max_length=12)
    guardrails: list[str] = Field(default_factory=list, max_length=12)
    additional_data_required: list[str] = Field(default_factory=list, max_length=12)
    decision_notes: list[str] = Field(default_factory=list, max_length=12)
    blockers: list[str] = Field(default_factory=list, max_length=10)
    warnings: list[str] = Field(default_factory=list, max_length=10)


class RunnerLike(Protocol):
    def run_sync(self, agent: Any, input: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class BusinessAgentSet:
    growth: Any
    marketing: Any
    partnerships: Any
    operations: Any
    finance: Any


def _input(task: str, payload: dict[str, Any]) -> str:
    return f"{task}\n\nINPUT_JSON\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def build_business_agents(model: str | None = None) -> BusinessAgentSet:
    from agents import Agent

    model_name = model or os.getenv("SOZOROCK_BUSINESS_MODEL", "gpt-5.6-sol")
    shared = (
        "Work only from the supplied evidence, metrics, and constraints. Do not invent customers, partners, funding, revenue, learner outcomes, salaries, demand, placement rates, approvals, or performance data. "
        "The Canadian learner offering is CAD $0 at launch. The organization is not represented as a college, university, or degree-granting institution. "
        "Use precise natural language and avoid generic AI or career-marketing phrases. You may analyze or prepare work only. You have no authority to publish, contact an external party, spend money, commit funds, or alter learner records. "
    )

    growth = Agent(
        name="Growth Agent",
        model=model_name,
        instructions=shared + (
            "Analyze acquisition and conversion as an evidence problem. Define the smallest funnel, hypotheses, experiments, measurements, and missing evidence. "
            "Prefer diagnostic, research, referral, and pathway-interest signals over vanity traffic. Do not manufacture market demand."
        ),
        output_type=GrowthOutput,
    )
    marketing = Agent(
        name="Marketing Agent",
        model=model_name,
        instructions=shared + (
            "Prepare evidence-backed positioning, message, channels, content assets, and a concrete conversion action. Separate supported proof points from claims that still need evidence. "
            "Block unsupported outcome, salary, placement, accreditation, school-status, or partnership claims. Do not publish anything."
        ),
        output_type=MarketingOutput,
    )
    partnerships = Agent(
        name="Partnership Agent",
        model=model_name,
        instructions=shared + (
            "Assess a potential employer, sponsor, workforce, community, or institutional partnership. Define mutual value, qualification signals, evidence gaps, preparation steps, and an outreach outline. "
            "Do not claim a relationship exists and do not contact anyone."
        ),
        output_type=PartnershipOutput,
    )
    operations = Agent(
        name="Operations Agent",
        model=model_name,
        instructions=shared + (
            "Analyze an operating process such as registration, learner support, approvals, evidence review, partner intake, or platform administration. "
            "Separate deterministic automation from judgment, identify human controls, service measures, data boundaries, and failure points. Do not alter learner or partner records."
        ),
        output_type=OperationsOutput,
    )
    finance = Agent(
        name="Finance Agent",
        model=model_name,
        instructions=shared + (
            "Analyze only the financial question and numeric inputs supplied. Surface assumptions instead of inventing values. Examine cost drivers such as cloud, model use, learner support, delivery, sponsored access, and employer work when relevant. "
            "Prepare scenarios, decision guardrails, missing-data requirements, and implications. Do not transfer money, create a payment, approve spend, or represent a scenario as an audited forecast."
        ),
        output_type=FinanceOutput,
    )
    return BusinessAgentSet(growth, marketing, partnerships, operations, finance)


class OpenAIBusinessOperationsProvider:
    def __init__(self, agents: BusinessAgentSet | None = None, runner: RunnerLike | None = None, *, max_turns: int = 8) -> None:
        self.agents = agents or build_business_agents()
        if runner is None:
            from agents import Runner

            runner = Runner
        self.runner = runner
        self.max_turns = max_turns

    @staticmethod
    def normalize(request: dict[str, Any]) -> dict[str, Any]:
        workstream = str(request.get("workstream", "")).strip().lower()
        action_class = str(request.get("action_class", "analysis")).strip().lower()
        problem = " ".join(str(request.get("problem", "")).split())
        if workstream not in _ALLOWED_WORKSTREAMS:
            raise ValueError(f"unsupported business workstream: {workstream or 'missing'}")
        if action_class not in _ALLOWED_ACTIONS:
            raise ValueError(f"unsupported business action class: {action_class or 'missing'}")
        if action_class not in _ALLOWED_COMBINATIONS[workstream]:
            raise ValueError(f"action class {action_class} is not permitted for workstream {workstream}")
        if not problem:
            raise ValueError("business request requires a problem statement")
        normalized = dict(request)
        normalized.update(
            {
                "workstream": workstream,
                "action_class": action_class,
                "problem": problem,
                "market": "Canada",
            }
        )
        return normalized

    def _run(self, agent: Any, task: str, request: dict[str, Any], expected: type[BaseModel]) -> dict[str, Any]:
        result = self.runner.run_sync(agent, _input(task, {"request": request}), max_turns=self.max_turns)
        output = result.final_output
        if not isinstance(output, expected):
            raise TypeError(f"agent {getattr(agent, 'name', 'unknown')} returned untyped output")
        return output.model_dump()

    def analyze_growth(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._run(self.agents.growth, "Analyze the bounded growth question.", request, GrowthOutput)

    def analyze_marketing(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._run(self.agents.marketing, "Prepare the evidence-backed marketing work.", request, MarketingOutput)

    def analyze_partnerships(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._run(self.agents.partnerships, "Assess and prepare the partnership work.", request, PartnershipOutput)

    def analyze_operations(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._run(self.agents.operations, "Analyze the bounded operating process.", request, OperationsOutput)

    def analyze_finance(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._run(self.agents.finance, "Analyze the supplied financial question without executing a commitment.", request, FinanceOutput)
