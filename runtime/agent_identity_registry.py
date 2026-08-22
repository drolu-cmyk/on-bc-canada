"""Non-human identity, tool, and runtime-budget policy for model workers.

This registry gives every model worker a stable logical identity independent of a
particular model version. It contains no credentials. Runtime credentials remain
application-managed and are never exposed to an agent identity record.

The runtime guard is intentionally fail-closed: a disabled identity, unexpected
tool, widened model-data declaration, missing typed output, or turn budget above
the registered limit is rejected before Runner.run_sync is called.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Literal


BudgetClass = Literal["low", "standard", "research_web"]

DISABLED_AGENT_IDS_ENV = "SOZOROCK_DISABLED_AGENT_IDS"
DISABLED_WORK_TYPES_ENV = "SOZOROCK_DISABLED_WORK_TYPES"
MAX_AGENT_TURNS_ENV = "SOZOROCK_MAX_AGENT_TURNS"


@dataclass(frozen=True)
class WorkflowRuntimeBudget:
    work_type: str
    max_model_calls_per_execution: int
    retry_limit_per_agent: int
    budget_class: BudgetClass

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AgentIdentity:
    identity_id: str
    actor_id: str
    sdk_name: str
    work_type: str
    graph_id: str | None
    authority: str
    accountable_function: str
    model_data_classes: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    max_turns: int
    max_calls_per_execution: int
    retry_limit: int
    budget_class: BudgetClass
    enabled_by_default: bool = True
    secret_access: bool = False
    credential_boundary: str = "application_runtime_only"

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


RESEARCH_DATA = ("public_research", "attributable_evidence", "organization_aggregate")
PRODUCT_DATA = ("operational", "product_context", "public_research")
BUSINESS_DATA = ("operational", "business_context", "organization_aggregate", "financial_summary", "public_research")
LEARNER_DATA = ("deidentified_learning_metadata", "capability_standard")
CAREER_DATA = ("deidentified_accepted_capability_metadata", "work_intelligence")
EMPLOYER_DATA = ("organization_workflow", "aggregate_metrics", "public_research")
OUTCOMES_DATA = ("aggregate_outcomes", "measurement_metadata")
RUNTIME_ASSURANCE_DATA = ("aggregate_runtime_telemetry", "runtime_control_state", "telemetry_coverage")
LEARNING_DESIGN_DATA = ("active_capability_definition", "evidence_standard", "module_summary")
ORCHESTRATOR_DATA = ("orchestration_metadata",)


def _identity(
    actor_id: str,
    sdk_name: str,
    work_type: str,
    graph_id: str | None,
    accountable_function: str,
    model_data_classes: tuple[str, ...],
    *,
    tools: tuple[str, ...] = (),
    max_turns: int,
    budget_class: BudgetClass = "standard",
) -> AgentIdentity:
    return AgentIdentity(
        identity_id=f"nhi:canada-platform:{actor_id}",
        actor_id=actor_id,
        sdk_name=sdk_name,
        work_type=work_type,
        graph_id=graph_id,
        authority="A1",
        accountable_function=accountable_function,
        model_data_classes=model_data_classes,
        allowed_tools=tools,
        max_turns=max_turns,
        max_calls_per_execution=1,
        retry_limit=0,
        budget_class=budget_class,
    )


AGENT_IDENTITIES: dict[str, AgentIdentity] = {
    item.actor_id: item
    for item in (
        _identity(
            "research-director-agent",
            "Canadian Technical Work Research Director",
            "research_intelligence",
            "canadian-work-research",
            "research intelligence",
            RESEARCH_DATA,
            tools=("hosted_web_search",),
            max_turns=8,
            budget_class="research_web",
        ),
        _identity(
            "evidence-agent",
            "Evidence Agent",
            "research_intelligence",
            "canadian-work-research",
            "research evidence",
            RESEARCH_DATA,
            tools=("hosted_web_search",),
            max_turns=8,
            budget_class="research_web",
        ),
        _identity(
            "labour-market-agent",
            "Canadian Labour Market Agent",
            "research_intelligence",
            "canadian-work-research",
            "labour market intelligence",
            RESEARCH_DATA,
            max_turns=8,
        ),
        _identity(
            "technology-agent",
            "Technology Signal Agent",
            "research_intelligence",
            "canadian-work-research",
            "technology intelligence",
            RESEARCH_DATA,
            tools=("hosted_web_search",),
            max_turns=8,
            budget_class="research_web",
        ),
        _identity(
            "skills-agent",
            "Capability Extraction Agent",
            "research_intelligence",
            "canadian-work-research",
            "capability intelligence",
            RESEARCH_DATA,
            max_turns=8,
        ),
        _identity(
            "contradiction-agent",
            "Contradiction Agent",
            "research_intelligence",
            "canadian-work-research",
            "research challenge",
            RESEARCH_DATA,
            tools=("hosted_web_search",),
            max_turns=8,
            budget_class="research_web",
        ),
        _identity(
            "curriculum-impact-agent",
            "Curriculum Impact Agent",
            "research_intelligence",
            "canadian-work-research",
            "curriculum evidence analysis",
            RESEARCH_DATA,
            max_turns=8,
        ),
        _identity("product-agent", "Product Agent", "product_development", "product-development", "product", PRODUCT_DATA, max_turns=8),
        _identity("experience-agent", "Experience Agent", "product_development", "product-development", "experience design", PRODUCT_DATA, max_turns=8),
        _identity("ui-design-agent", "UI Design Agent", "product_development", "product-development", "interface design", PRODUCT_DATA, max_turns=8),
        _identity("copy-agent", "Copy Agent", "product_development", "product-development", "product copy", PRODUCT_DATA, max_turns=8),
        _identity("brand-agent", "Brand Agent", "product_development", "product-development", "brand", PRODUCT_DATA, max_turns=8),
        _identity("engineering-agent", "Engineering Agent", "product_development", "product-development", "engineering", PRODUCT_DATA, max_turns=8),
        _identity("cloud-agent", "Cloud Agent", "product_development", "product-development", "cloud operations", PRODUCT_DATA, max_turns=8),
        _identity("security-agent", "Security Agent", "product_development", "product-development", "security", PRODUCT_DATA, max_turns=8),
        _identity("accessibility-agent", "Accessibility Agent", "product_development", "product-development", "accessibility", PRODUCT_DATA, max_turns=8),
        _identity("quality-agent", "Quality Agent", "product_development", "product-development", "quality", PRODUCT_DATA, max_turns=8),
        _identity("growth-agent", "Growth Agent", "business_operations", "business-operations", "growth", BUSINESS_DATA, max_turns=8),
        _identity("marketing-agent", "Marketing Agent", "business_operations", "business-operations", "marketing", BUSINESS_DATA, max_turns=8),
        _identity("partnership-agent", "Partnership Agent", "business_operations", "business-operations", "partnerships", BUSINESS_DATA, max_turns=8),
        _identity("operations-agent", "Operations Agent", "business_operations", "business-operations", "operations", BUSINESS_DATA, max_turns=8),
        _identity("finance-agent", "Finance Agent", "business_operations", "business-operations", "finance", BUSINESS_DATA, max_turns=8),
        _identity("learning-coach-agent", "Learning Coach Agent", "learner_execution", "learner-execution", "learner support", LEARNER_DATA, max_turns=6),
        _identity("learner-progress-agent", "Learner Progress Agent", "learner_execution", "learner-execution", "learner support", LEARNER_DATA, max_turns=6),
        _identity("human-review-preparation-agent", "Human Review Preparation Agent", "learner_execution", "learner-execution", "learner evidence review support", LEARNER_DATA, max_turns=6),
        _identity("career-profile-agent", "Career Profile Agent", "career_mobility", "career-mobility", "career mobility", CAREER_DATA, max_turns=6),
        _identity("role-transition-agent", "Role Transition Agent", "career_mobility", "career-mobility", "career mobility", CAREER_DATA, max_turns=6),
        _identity("career-evidence-packaging-agent", "Career Evidence Packaging Agent", "career_mobility", "career-mobility", "career evidence", CAREER_DATA, max_turns=6),
        _identity("interview-practice-agent", "Interview Practice Agent", "career_mobility", "career-mobility", "career preparation", CAREER_DATA, max_turns=6),
        _identity("career-action-agent", "Career Action Agent", "career_mobility", "career-mobility", "career mobility", CAREER_DATA, max_turns=6),
        _identity("employer-workflow-agent", "Employer Workflow Agent", "employer_workforce", "employer-workforce", "employer workforce", EMPLOYER_DATA, max_turns=7),
        _identity("ai-opportunity-agent", "AI Opportunity Agent", "employer_workforce", "employer-workforce", "employer AI adoption", EMPLOYER_DATA, max_turns=7),
        _identity("workforce-impact-agent", "Workforce Impact Agent", "employer_workforce", "employer-workforce", "workforce impact", EMPLOYER_DATA, max_turns=7),
        _identity("employer-capability-demand-agent", "Employer Capability Demand Agent", "employer_workforce", "employer-workforce", "employer capability demand", EMPLOYER_DATA, max_turns=7),
        _identity("ai-adoption-risk-agent", "AI Adoption Risk Agent", "employer_workforce", "employer-workforce", "AI adoption risk", EMPLOYER_DATA, max_turns=7),
        _identity("ai-adoption-pilot-agent", "AI Adoption Pilot Agent", "employer_workforce", "employer-workforce", "AI adoption pilot", EMPLOYER_DATA, max_turns=7),
        _identity("ai-adoption-measurement-agent", "AI Adoption Measurement Agent", "employer_workforce", "employer-workforce", "AI adoption measurement", EMPLOYER_DATA, max_turns=7),
        _identity("outcomes-analysis-agent", "Outcomes Analysis Agent", "outcomes_intelligence", "outcomes-intelligence", "programme outcomes intelligence", OUTCOMES_DATA, max_turns=6),
        _identity("outcomes-challenge-agent", "Outcomes Challenge Agent", "outcomes_intelligence", "outcomes-intelligence", "programme outcomes challenge", OUTCOMES_DATA, max_turns=6),
        _identity("runtime-reliability-agent", "Runtime Reliability Agent", "runtime_assurance", "runtime-assurance", "runtime reliability assurance", RUNTIME_ASSURANCE_DATA, max_turns=6),
        _identity("runtime-control-agent", "Runtime Control Agent", "runtime_assurance", "runtime-assurance", "runtime control assurance", RUNTIME_ASSURANCE_DATA, max_turns=6),
        _identity("learning-design-agent", "Learning Graph Design Agent", "learning_design", None, "learning design", LEARNING_DESIGN_DATA, max_turns=8),
        _identity("platform-orchestrator-agent", "Platform Orchestrator Agent", "platform_orchestration", None, "platform orchestration", ORCHESTRATOR_DATA, max_turns=6, budget_class="low"),
    )
}


WORKFLOW_RUNTIME_BUDGETS: dict[str, WorkflowRuntimeBudget] = {
    "research_intelligence": WorkflowRuntimeBudget("research_intelligence", 7, 0, "research_web"),
    "product_development": WorkflowRuntimeBudget("product_development", 10, 0, "standard"),
    "business_operations": WorkflowRuntimeBudget("business_operations", 1, 0, "standard"),
    "learner_execution": WorkflowRuntimeBudget("learner_execution", 3, 0, "standard"),
    "career_mobility": WorkflowRuntimeBudget("career_mobility", 5, 0, "standard"),
    "employer_workforce": WorkflowRuntimeBudget("employer_workforce", 7, 0, "standard"),
    "outcomes_intelligence": WorkflowRuntimeBudget("outcomes_intelligence", 2, 0, "standard"),
    "runtime_assurance": WorkflowRuntimeBudget("runtime_assurance", 2, 0, "standard"),
    "learning_design": WorkflowRuntimeBudget("learning_design", 1, 0, "standard"),
    "platform_orchestration": WorkflowRuntimeBudget("platform_orchestration", 1, 0, "low"),
}


def identity_manifest() -> list[dict[str, object]]:
    return [AGENT_IDENTITIES[key].as_dict() for key in sorted(AGENT_IDENTITIES)]


def budget_manifest() -> list[dict[str, object]]:
    return [WORKFLOW_RUNTIME_BUDGETS[key].as_dict() for key in sorted(WORKFLOW_RUNTIME_BUDGETS)]


def identity_for_actor(actor_id: str) -> AgentIdentity:
    try:
        return AGENT_IDENTITIES[actor_id]
    except KeyError as exc:
        raise KeyError(f"agent identity not registered for actor: {actor_id}") from exc


def identity_for_sdk_name(sdk_name: str) -> AgentIdentity:
    matches = [item for item in AGENT_IDENTITIES.values() if item.sdk_name == sdk_name]
    if len(matches) != 1:
        raise KeyError(f"agent identity not uniquely registered for SDK name: {sdk_name}")
    return matches[0]


def _csv_env(name: str) -> set[str]:
    return {item.strip() for item in os.getenv(name, "").split(",") if item.strip()}


def disabled_agent_tokens() -> set[str]:
    return _csv_env(DISABLED_AGENT_IDS_ENV)


def disabled_work_types() -> set[str]:
    return _csv_env(DISABLED_WORK_TYPES_ENV)


def is_identity_enabled(identity: AgentIdentity) -> bool:
    if not identity.enabled_by_default:
        return False
    disabled = disabled_agent_tokens()
    if identity.identity_id in disabled or identity.actor_id in disabled or identity.sdk_name in disabled:
        return False
    if identity.work_type in disabled_work_types():
        return False
    return True


def effective_turn_limit(identity: AgentIdentity) -> int:
    raw = os.getenv(MAX_AGENT_TURNS_ENV, "").strip()
    if not raw:
        return identity.max_turns
    try:
        global_limit = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{MAX_AGENT_TURNS_ENV} must be an integer") from exc
    if global_limit < 1:
        raise RuntimeError(f"{MAX_AGENT_TURNS_ENV} must be at least 1")
    return min(identity.max_turns, global_limit)


def sdk_tool_labels(agent: Any) -> tuple[str, ...]:
    labels: list[str] = []
    for tool in getattr(agent, "tools", []) or []:
        class_name = type(tool).__name__
        if class_name == "WebSearchTool":
            labels.append("hosted_web_search")
        else:
            labels.append(f"sdk:{class_name}")
    return tuple(sorted(labels))


def assert_agent_runtime_allowed(
    agent: Any,
    *,
    requested_max_turns: int,
    declared_model_data_classes: tuple[str, ...] = (),
) -> AgentIdentity:
    """Fail closed before a model run when identity, tools, data, or budget drift."""

    sdk_name = str(getattr(agent, "name", "")).strip()
    if not sdk_name:
        raise RuntimeError("model worker has no registered SDK name")
    try:
        identity = identity_for_sdk_name(sdk_name)
    except KeyError as exc:
        raise RuntimeError(str(exc)) from exc

    if not is_identity_enabled(identity):
        raise RuntimeError(f"agent identity is disabled: {identity.identity_id}")
    if identity.authority != "A1":
        raise RuntimeError(f"model agent authority must remain A1: {identity.identity_id}")
    if identity.secret_access:
        raise RuntimeError(f"model agent identity cannot have secret access: {identity.identity_id}")

    actual_tools = sdk_tool_labels(agent)
    expected_tools = tuple(sorted(identity.allowed_tools))
    if actual_tools != expected_tools:
        raise RuntimeError(
            f"agent tool policy mismatch for {identity.identity_id}: actual={actual_tools!r} expected={expected_tools!r}"
        )

    if getattr(agent, "output_type", None) is None:
        raise RuntimeError(f"typed agent output is required: {identity.identity_id}")

    limit = effective_turn_limit(identity)
    if requested_max_turns < 1 or requested_max_turns > limit:
        raise RuntimeError(
            f"agent turn budget exceeded for {identity.identity_id}: requested={requested_max_turns} limit={limit}"
        )

    declared = set(declared_model_data_classes)
    allowed = set(identity.model_data_classes)
    if not declared.issubset(allowed):
        raise RuntimeError(
            f"agent model-data policy exceeded for {identity.identity_id}: {', '.join(sorted(declared - allowed))}"
        )
    from runtime.model_runtime_telemetry import install_model_runtime_telemetry

    install_model_runtime_telemetry()
    return identity


def runtime_status(identity_id: str) -> dict[str, object]:
    matches = [item for item in AGENT_IDENTITIES.values() if item.identity_id == identity_id or item.actor_id == identity_id]
    if len(matches) != 1:
        raise KeyError(f"agent identity not found: {identity_id}")
    identity = matches[0]
    return {
        "identity": identity.as_dict(),
        "enabled": is_identity_enabled(identity),
        "effective_max_turns": effective_turn_limit(identity),
        "disabled_agent_env": DISABLED_AGENT_IDS_ENV,
        "disabled_work_type_env": DISABLED_WORK_TYPES_ENV,
    }
