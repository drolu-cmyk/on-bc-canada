"""Typed organization-level Employer Workforce agents.

Workers analyze supplied workflow data only. They do not make employee-level
performance, hiring, termination, compensation, promotion, or scheduling
decisions and have no external-action tools.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field


class WorkflowFinding(BaseModel):
    task_id: str
    issue: str
    decision_points: list[str] = Field(default_factory=list, max_length=6)
    human_accountability_points: list[str] = Field(default_factory=list, max_length=6)


class WorkflowAnalysisOutput(BaseModel):
    workflow_summary: str
    findings: list[WorkflowFinding] = Field(min_length=1, max_length=30)
    cross_task_constraints: list[str] = Field(default_factory=list, max_length=10)


class AIOpportunity(BaseModel):
    opportunity_id: str
    task_ids: list[str] = Field(min_length=1, max_length=12)
    pattern: Literal[
        "assist",
        "retrieve",
        "classify",
        "generate",
        "monitor",
        "bounded_automation",
        "agentic_coordination",
    ]
    value_hypothesis: str
    automation_boundary: str
    evidence_needed: list[str] = Field(min_length=1, max_length=8)


class AIOpportunityOutput(BaseModel):
    opportunities: list[AIOpportunity] = Field(default_factory=list, max_length=20)
    no_change_reasons: list[str] = Field(default_factory=list, max_length=8)


class RoleImpact(BaseModel):
    role_label: str
    affected_task_ids: list[str] = Field(min_length=1, max_length=12)
    change_type: Literal["assist", "task_shift", "new_task", "control_requirement", "no_material_change"]
    work_change: str
    human_decisions_preserved: list[str] = Field(default_factory=list, max_length=8)


class WorkforceImpactOutput(BaseModel):
    role_impacts: list[RoleImpact] = Field(default_factory=list, max_length=30)
    organization_notes: list[str] = Field(default_factory=list, max_length=8)


class CapabilityDemand(BaseModel):
    capability_name: str
    observable_work: str
    source_task_ids: list[str] = Field(min_length=1, max_length=12)
    priority: Literal["core", "important", "adjacent"]
    research_validation_required: bool = True


class CapabilityDemandOutput(BaseModel):
    demands: list[CapabilityDemand] = Field(default_factory=list, max_length=30)
    note: str


class AdoptionRisk(BaseModel):
    opportunity_id: str
    risk_type: Literal[
        "privacy",
        "security",
        "reliability",
        "human_oversight",
        "compliance",
        "change_management",
        "cost",
        "data_quality",
    ]
    risk: str
    mitigation: str
    stop_condition: str


class AdoptionRiskOutput(BaseModel):
    risks: list[AdoptionRisk] = Field(default_factory=list, max_length=40)
    cross_cutting_controls: list[str] = Field(default_factory=list, max_length=12)


class PilotDesignOutput(BaseModel):
    pilot_id: str
    opportunity_ids: list[str] = Field(min_length=1, max_length=12)
    task_ids: list[str] = Field(min_length=1, max_length=16)
    pilot_scope: str
    success_measures: list[str] = Field(min_length=1, max_length=12)
    stop_conditions: list[str] = Field(min_length=1, max_length=12)
    required_human_approvals: list[str] = Field(default_factory=list, max_length=10)


class MeasurementItem(BaseModel):
    measure_id: str
    definition: str
    baseline_metric_id: str | None = None
    interpretation: str


class AdoptionMeasurementOutput(BaseModel):
    measures: list[MeasurementItem] = Field(min_length=1, max_length=20)
    decision_rules: list[str] = Field(min_length=1, max_length=12)
    evidence_collection_notes: list[str] = Field(default_factory=list, max_length=10)


class RunnerLike(Protocol):
    def run_sync(self, agent: Any, input: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class EmployerWorkforceAgentSet:
    workflow_agent: Any
    ai_opportunity_agent: Any
    workforce_impact_agent: Any
    capability_demand_agent: Any
    adoption_risk_agent: Any
    pilot_design_agent: Any
    measurement_agent: Any


def build_employer_workforce_agents(model: str | None = None) -> EmployerWorkforceAgentSet:
    """Construct workers without performing an API call."""

    from agents import Agent

    model_name = model or os.getenv("SOZOROCK_EMPLOYER_MODEL", "gpt-5.6-sol")
    boundary = (
        "Use only the organization-level workflow information in INPUT_JSON. The input uses role labels, not employee identities. "
        "Do not infer individual performance, protected characteristics, compensation, promotion, discipline, termination, hiring suitability, or employee ranking. "
        "Do not recommend replacing a named person. Do not contact anyone or execute changes."
    )
    workflow = Agent(
        name="Employer Workflow Agent",
        model=model_name,
        instructions=(
            boundary
            + " Map the supplied tasks, friction, decision points, and human accountability. Every finding must reference an existing task_id. "
            "Separate process friction from problems that actually need AI."
        ),
        output_type=WorkflowAnalysisOutput,
    )
    ai_opportunity = Agent(
        name="AI Opportunity Agent",
        model=model_name,
        instructions=(
            boundary
            + " Identify bounded AI opportunities only where the workflow evidence supports them. Prefer assistance and reversible automation before higher autonomy. "
            "Every opportunity must reference supplied task IDs, define the automation boundary, and list evidence needed before adoption."
        ),
        output_type=AIOpportunityOutput,
    )
    workforce = Agent(
        name="Workforce Impact Agent",
        model=model_name,
        instructions=(
            boundary
            + " Describe how supplied role labels and tasks may change if the bounded opportunities are adopted. Focus on task change, new responsibilities, controls, and human decisions preserved. "
            "Do not recommend layoffs, hiring decisions, performance scores, or individual actions."
        ),
        output_type=WorkforceImpactOutput,
    )
    capability = Agent(
        name="Employer Capability Demand Agent",
        model=model_name,
        instructions=(
            boundary
            + " Translate the work changes into observable capabilities an organization may need. Capability names are organization-specific signals, not approved curriculum. "
            "Every demand must cite source task IDs and set research_validation_required=true."
        ),
        output_type=CapabilityDemandOutput,
    )
    risk = Agent(
        name="AI Adoption Risk Agent",
        model=model_name,
        instructions=(
            boundary
            + " Challenge the AI opportunities for privacy, security, reliability, human oversight, compliance, change-management, cost, and data-quality risk. "
            "Tie opportunity-specific risks to supplied opportunity IDs and give concrete stop conditions."
        ),
        output_type=AdoptionRiskOutput,
    )
    pilot = Agent(
        name="AI Adoption Pilot Agent",
        model=model_name,
        instructions=(
            boundary
            + " Design one bounded, reversible pilot using supplied opportunity and task IDs. Define success measures, stop conditions, and human approvals. "
            "Do not authorize production deployment or workforce decisions."
        ),
        output_type=PilotDesignOutput,
    )
    measurement = Agent(
        name="AI Adoption Measurement Agent",
        model=model_name,
        instructions=(
            boundary
            + " Define organization-level measures and decision rules for evaluating a pilot. Use baseline_metric_id only when it exists in INPUT_JSON. "
            "Do not create individual employee productivity scores or worker rankings."
        ),
        output_type=AdoptionMeasurementOutput,
    )
    return EmployerWorkforceAgentSet(
        workflow,
        ai_opportunity,
        workforce,
        capability,
        risk,
        pilot,
        measurement,
    )


class OpenAIEmployerWorkforceProvider:
    def __init__(
        self,
        agents: EmployerWorkforceAgentSet | None = None,
        runner: RunnerLike | None = None,
        *,
        max_turns: int = 7,
    ) -> None:
        self.agents = agents or build_employer_workforce_agents()
        if runner is None:
            from agents import Runner

            runner = Runner
        self.runner = runner
        self.max_turns = max_turns

    @staticmethod
    def _message(task: str, payload: dict[str, Any]) -> str:
        return task + "\n\nINPUT_JSON\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _run(self, agent: Any, task: str, payload: dict[str, Any], expected: type[BaseModel]) -> BaseModel:
        result = self.runner.run_sync(
            agent,
            self._message(task, payload),
            max_turns=self.max_turns,
        )
        output = result.final_output
        if not isinstance(output, expected):
            raise TypeError(f"employer workforce agent {getattr(agent, 'name', 'unknown')} returned untyped output")
        return output

    def analyze_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run(self.agents.workflow_agent, "Analyze the organization workflow.", payload, WorkflowAnalysisOutput).model_dump()

    def identify_ai_opportunities(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run(self.agents.ai_opportunity_agent, "Identify bounded AI opportunities.", payload, AIOpportunityOutput).model_dump()

    def analyze_workforce_impact(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run(self.agents.workforce_impact_agent, "Analyze role and task change without employee decisions.", payload, WorkforceImpactOutput).model_dump()

    def identify_capability_demand(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run(self.agents.capability_demand_agent, "Identify observable organization capability demand signals.", payload, CapabilityDemandOutput).model_dump()

    def analyze_adoption_risk(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run(self.agents.adoption_risk_agent, "Challenge the bounded opportunities and define controls.", payload, AdoptionRiskOutput).model_dump()

    def design_pilot(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run(self.agents.pilot_design_agent, "Design one bounded reversible pilot.", payload, PilotDesignOutput).model_dump()

    def define_measurement(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run(self.agents.measurement_agent, "Define organization-level pilot measurement and decision rules.", payload, AdoptionMeasurementOutput).model_dump()
