"""Reconcile non-human identity policy with live graphs and Agents SDK workers."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from runtime.agent_identity_registry import (
    AGENT_IDENTITIES,
    WORKFLOW_RUNTIME_BUDGETS,
    sdk_tool_labels,
)
from runtime.openai_business_operations_provider import OpenAIBusinessOperationsProvider, build_business_agents
from runtime.openai_career_mobility_provider import OpenAICareerMobilityProvider, build_career_agents
from runtime.openai_employer_workforce_provider import OpenAIEmployerWorkforceProvider, build_employer_workforce_agents
from runtime.openai_learner_provider import OpenAILearnerSupportProvider, build_learner_agents
from runtime.openai_outcomes_provider import OpenAIOutcomesIntelligenceProvider, build_outcomes_agents
from runtime.openai_platform_orchestrator import OpenAIPlatformOrchestrator, build_platform_orchestrator_agent
from runtime.openai_product_provider import OpenAIProductDevelopmentProvider, build_product_agents
from runtime.openai_research_provider import OpenAIResearchProvider, build_research_agents
from runtime.openai_runtime_assurance_provider import OpenAIRuntimeAssuranceProvider, build_runtime_assurance_agents
from runtime.platform_graph_registry import GRAPH_CONTRACTS


@dataclass(frozen=True)
class AgentPolicyIssue:
    identity_id: str
    rule: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class AgentPolicyAuditReport:
    passed: bool
    graph_agent_count: int
    registered_identity_count: int
    sdk_agent_count: int
    issues: tuple[AgentPolicyIssue, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "graph_agent_count": self.graph_agent_count,
            "registered_identity_count": self.registered_identity_count,
            "sdk_agent_count": self.sdk_agent_count,
            "issues": [item.as_dict() for item in self.issues],
        }


def _issue(identity_id: str, rule: str, detail: str) -> AgentPolicyIssue:
    return AgentPolicyIssue(identity_id, rule, detail)


def _sdk_inventory(model: str = "gpt-5.6-sol") -> tuple[dict[str, Any], dict[str, int]]:
    research = build_research_agents(model=model)
    product = build_product_agents(model=model)
    business = build_business_agents(model=model)
    learner = build_learner_agents(model=model)
    career = build_career_agents(model=model)
    employer = build_employer_workforce_agents(model=model)
    outcomes = build_outcomes_agents(model=model)
    runtime_assurance = build_runtime_assurance_agents(model=model)
    orchestrator = build_platform_orchestrator_agent(model=model)

    agents = {
        "research-director-agent": research.research_director,
        "evidence-agent": research.evidence_agent,
        "labour-market-agent": research.labour_market_agent,
        "technology-agent": research.technology_agent,
        "skills-agent": research.skills_agent,
        "contradiction-agent": research.contradiction_agent,
        "curriculum-impact-agent": research.curriculum_impact_agent,
        "product-agent": product.product,
        "experience-agent": product.experience,
        "ui-design-agent": product.interface,
        "copy-agent": product.copy,
        "brand-agent": product.brand,
        "engineering-agent": product.engineering,
        "cloud-agent": product.cloud,
        "security-agent": product.security,
        "accessibility-agent": product.accessibility,
        "quality-agent": product.quality,
        "growth-agent": business.growth,
        "marketing-agent": business.marketing,
        "partnership-agent": business.partnerships,
        "operations-agent": business.operations,
        "finance-agent": business.finance,
        "learning-coach-agent": learner.coach_agent,
        "learner-progress-agent": learner.progress_agent,
        "human-review-preparation-agent": learner.review_preparation_agent,
        "career-profile-agent": career.profile_agent,
        "role-transition-agent": career.role_transition_agent,
        "career-evidence-packaging-agent": career.evidence_packaging_agent,
        "interview-practice-agent": career.interview_practice_agent,
        "career-action-agent": career.action_plan_agent,
        "employer-workflow-agent": employer.workflow_agent,
        "ai-opportunity-agent": employer.ai_opportunity_agent,
        "workforce-impact-agent": employer.workforce_impact_agent,
        "employer-capability-demand-agent": employer.capability_demand_agent,
        "ai-adoption-risk-agent": employer.adoption_risk_agent,
        "ai-adoption-pilot-agent": employer.pilot_design_agent,
        "ai-adoption-measurement-agent": employer.measurement_agent,
        "outcomes-analysis-agent": outcomes.analysis_agent,
        "outcomes-challenge-agent": outcomes.challenge_agent,
        "runtime-reliability-agent": runtime_assurance.reliability_agent,
        "runtime-control-agent": runtime_assurance.control_agent,
        "platform-orchestrator-agent": orchestrator,
    }

    marker = object()
    provider_turns = {
        "research_intelligence": OpenAIResearchProvider(agents=research, runner=marker).max_turns,
        "product_development": OpenAIProductDevelopmentProvider(agents=product, runner=marker).max_turns,
        "business_operations": OpenAIBusinessOperationsProvider(agents=business, runner=marker).max_turns,
        "learner_execution": OpenAILearnerSupportProvider(agents=learner, runner=marker).max_turns,
        "career_mobility": OpenAICareerMobilityProvider(agents=career, runner=marker).max_turns,
        "employer_workforce": OpenAIEmployerWorkforceProvider(agents=employer, runner=marker).max_turns,
        "outcomes_intelligence": OpenAIOutcomesIntelligenceProvider(agents=outcomes, runner=marker).max_turns,
        "runtime_assurance": OpenAIRuntimeAssuranceProvider(agents=runtime_assurance, runner=marker).max_turns,
        "platform_orchestration": OpenAIPlatformOrchestrator(agent=orchestrator, runner=marker).max_turns,
    }
    return agents, provider_turns


def audit_agent_identity_policy(*, construct_sdk_agents: bool = True) -> AgentPolicyAuditReport:
    issues: list[AgentPolicyIssue] = []
    graph_agents: dict[str, tuple[str, str]] = {}

    for work_type, contract in GRAPH_CONTRACTS.items():
        definition = contract.definition()
        for node in definition.nodes:
            if node.actor.kind != "agent":
                continue
            actor_id = node.actor.actor_id
            if actor_id in graph_agents:
                issues.append(_issue(actor_id, "graph_actor", "agent actor ID is duplicated across graph definitions"))
            graph_agents[actor_id] = (work_type, definition.graph_id)

    graph_identity_ids = {actor_id for actor_id, identity in AGENT_IDENTITIES.items() if identity.graph_id is not None}
    missing = set(graph_agents) - graph_identity_ids
    extra = graph_identity_ids - set(graph_agents)
    for actor_id in sorted(missing):
        issues.append(_issue(actor_id, "identity_coverage", "graph agent has no non-human identity record"))
    for actor_id in sorted(extra):
        issues.append(_issue(actor_id, "identity_coverage", "identity record does not map to a live graph agent"))

    identity_ids: set[str] = set()
    sdk_names: set[str] = set()
    for actor_id, identity in AGENT_IDENTITIES.items():
        if identity.identity_id in identity_ids:
            issues.append(_issue(identity.identity_id, "identity_uniqueness", "non-human identity ID is duplicated"))
        identity_ids.add(identity.identity_id)
        if identity.sdk_name in sdk_names:
            issues.append(_issue(identity.identity_id, "sdk_name", f"SDK name is not unique: {identity.sdk_name}"))
        sdk_names.add(identity.sdk_name)
        if actor_id != identity.actor_id:
            issues.append(_issue(identity.identity_id, "identity_key", "registry key does not match actor_id"))
        if identity.authority != "A1":
            issues.append(_issue(identity.identity_id, "authority", f"model worker authority is {identity.authority}, expected A1"))
        if identity.secret_access:
            issues.append(_issue(identity.identity_id, "secret_access", "model worker identity must not receive secret access"))
        if identity.retry_limit != 0:
            issues.append(_issue(identity.identity_id, "retry_budget", "automatic model retries are not enabled in the launch policy"))
        if identity.max_calls_per_execution != 1:
            issues.append(_issue(identity.identity_id, "call_budget", "each specialist identity may run at most once per graph execution"))
        if identity.max_turns < 1:
            issues.append(_issue(identity.identity_id, "turn_budget", "max_turns must be positive"))

        graph_context = graph_agents.get(actor_id)
        if graph_context:
            work_type, graph_id = graph_context
            if identity.work_type != work_type or identity.graph_id != graph_id:
                issues.append(
                    _issue(
                        identity.identity_id,
                        "graph_binding",
                        f"identity binds to {identity.work_type}:{identity.graph_id}, graph uses {work_type}:{graph_id}",
                    )
                )
            contract = GRAPH_CONTRACTS[work_type]
            if not set(identity.model_data_classes).issubset(set(contract.model_data_classes)):
                issues.append(_issue(identity.identity_id, "model_data", "identity model data exceeds graph model-data contract"))

    for work_type, budget in WORKFLOW_RUNTIME_BUDGETS.items():
        if budget.max_model_calls_per_execution < 1:
            issues.append(_issue(work_type, "workflow_budget", "workflow model-call budget must be positive"))
        if budget.retry_limit_per_agent != 0:
            issues.append(_issue(work_type, "workflow_budget", "workflow automatic retry policy must remain zero"))
        if work_type in GRAPH_CONTRACTS:
            agent_count = sum(
                1 for node in GRAPH_CONTRACTS[work_type].definition().nodes if node.actor.kind == "agent"
            )
            if budget.max_model_calls_per_execution > agent_count:
                issues.append(
                    _issue(
                        work_type,
                        "workflow_budget",
                        f"model-call budget {budget.max_model_calls_per_execution} exceeds graph agent count {agent_count}",
                    )
                )

    sdk_agents: dict[str, Any] = {}
    if construct_sdk_agents:
        sdk_agents, provider_turns = _sdk_inventory()
        if set(sdk_agents) != set(AGENT_IDENTITIES):
            for actor_id in sorted(set(AGENT_IDENTITIES) - set(sdk_agents)):
                issues.append(_issue(actor_id, "sdk_coverage", "registered identity has no SDK worker in construction audit"))
            for actor_id in sorted(set(sdk_agents) - set(AGENT_IDENTITIES)):
                issues.append(_issue(actor_id, "sdk_coverage", "SDK worker has no registered identity"))

        for actor_id, agent in sdk_agents.items():
            identity = AGENT_IDENTITIES.get(actor_id)
            if identity is None:
                continue
            if getattr(agent, "name", None) != identity.sdk_name:
                issues.append(
                    _issue(
                        identity.identity_id,
                        "sdk_name",
                        f"actual SDK name {getattr(agent, 'name', None)!r} does not match {identity.sdk_name!r}",
                    )
                )
            actual_tools = sdk_tool_labels(agent)
            expected_tools = tuple(sorted(identity.allowed_tools))
            if actual_tools != expected_tools:
                issues.append(
                    _issue(
                        identity.identity_id,
                        "tool_policy",
                        f"actual tools {actual_tools!r} do not match registered tools {expected_tools!r}",
                    )
                )
            if getattr(agent, "output_type", None) is None:
                issues.append(_issue(identity.identity_id, "typed_output", "SDK worker has no typed output contract"))
            actual_turns = provider_turns[identity.work_type]
            if identity.max_turns != actual_turns:
                issues.append(
                    _issue(
                        identity.identity_id,
                        "turn_budget",
                        f"registered max_turns {identity.max_turns} does not match provider default {actual_turns}",
                    )
                )

    return AgentPolicyAuditReport(
        passed=not issues,
        graph_agent_count=len(graph_agents),
        registered_identity_count=len(AGENT_IDENTITIES),
        sdk_agent_count=len(sdk_agents),
        issues=tuple(issues),
    )
