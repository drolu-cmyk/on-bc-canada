"""Authoritative registry for GraphKernel workflows in the Canada platform."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from runtime.business_operations_graph import BusinessOperationsGraph
from runtime.career_mobility_graph import CareerMobilityGraph
from runtime.employer_workforce_graph import EmployerWorkforceGraph
from runtime.graph_kernel import GraphDefinition
from runtime.learner_execution_graph import LearnerExecutionGraph
from runtime.product_development_graph import ProductDevelopmentGraph
from runtime.research_graph import ResearchGraph


STORE_IDS = {
    "work-intelligence",
    "capability-graph",
    "learning-graph",
    "learner-progress",
}

EXTERNAL_EXECUTION_EFFECTS = {
    "external_publish",
    "external_contact",
    "financial_transaction",
    "production_mutation",
    "employment_decision",
    "credential_issue",
}

COMMON_FORBIDDEN_MODEL_DATA = (
    "raw_learner_submission",
    "learner_direct_identifier",
    "employee_individual",
    "payment_credential",
    "production_secret",
)


@dataclass(frozen=True)
class ProtectedStateChange:
    node_id: str
    effect: str
    required_human_authority: str


@dataclass(frozen=True)
class HandoffRule:
    target_kind: str
    target_id: str
    payload_data_classes: tuple[str, ...]
    prerequisite: str
    required_human_authority: str | None = None


@dataclass(frozen=True)
class GraphContract:
    work_type: str
    graph_id: str
    purpose: str
    definition_factory: Callable[[], GraphDefinition] = field(repr=False, compare=False)
    graph_version: str = ""
    runtime_data_classes: tuple[str, ...] = ()
    model_data_classes: tuple[str, ...] = ()
    forbidden_data_classes: tuple[str, ...] = ()
    autonomous_effects: tuple[str, ...] = ()
    authorization_effects: tuple[tuple[str, str], ...] = ()
    executable_effects: tuple[tuple[str, str], ...] = ()
    max_agent_authority: str = "A1"
    max_service_authority: str = "A1"
    human_gates: tuple[tuple[str, str], ...] = ()
    protected_state_changes: tuple[ProtectedStateChange, ...] = ()
    handoffs: tuple[HandoffRule, ...] = ()
    terminal_record: str = ""
    executes_external_effects: bool = False
    requires_openai_api_key: bool = True
    notes: tuple[str, ...] = ()

    def definition(self) -> GraphDefinition:
        return self.definition_factory()

    @property
    def authorization_map(self) -> dict[str, str]:
        return dict(self.authorization_effects)

    @property
    def executable_map(self) -> dict[str, str]:
        return dict(self.executable_effects)

    def manifest(self) -> dict[str, object]:
        definition = self.definition()
        return {
            "work_type": self.work_type,
            "graph_id": self.graph_id,
            "graph_version": definition.version,
            "registered_graph_version": self.graph_version or None,
            "purpose": self.purpose,
            "runtime_data_classes": list(self.runtime_data_classes),
            "model_data_classes": list(self.model_data_classes),
            "forbidden_data_classes": list(self.forbidden_data_classes),
            "autonomous_effects": list(self.autonomous_effects),
            "authorization_effects": [
                {"effect": effect, "authority": authority}
                for effect, authority in self.authorization_effects
            ],
            "executable_effects": [
                {"effect": effect, "authority": authority}
                for effect, authority in self.executable_effects
            ],
            "max_agent_authority": self.max_agent_authority,
            "max_service_authority": self.max_service_authority,
            "human_gates": [
                {"node_id": node_id, "authority": authority}
                for node_id, authority in self.human_gates
            ],
            "protected_state_changes": [
                {
                    "node_id": item.node_id,
                    "effect": item.effect,
                    "required_human_authority": item.required_human_authority,
                }
                for item in self.protected_state_changes
            ],
            "handoffs": [
                {
                    "target_kind": item.target_kind,
                    "target_id": item.target_id,
                    "payload_data_classes": list(item.payload_data_classes),
                    "prerequisite": item.prerequisite,
                    "required_human_authority": item.required_human_authority,
                }
                for item in self.handoffs
            ],
            "terminal_record": self.terminal_record,
            "executes_external_effects": self.executes_external_effects,
            "requires_openai_api_key": self.requires_openai_api_key,
            "notes": list(self.notes),
        }


GRAPH_CONTRACTS: dict[str, GraphContract] = {
    "research_intelligence": GraphContract(
        work_type="research_intelligence",
        graph_id="canadian-work-research",
        graph_version="0.2.0",
        purpose="Validate Canadian technical-work signals before they influence platform intelligence.",
        definition_factory=ResearchGraph.definition,
        runtime_data_classes=("public_research", "attributable_evidence", "organization_aggregate"),
        model_data_classes=("public_research", "attributable_evidence", "organization_aggregate"),
        forbidden_data_classes=COMMON_FORBIDDEN_MODEL_DATA,
        autonomous_effects=("analysis", "external_read", "internal_record"),
        authorization_effects=(("curriculum_change_authorization_record", "A3"),),
        human_gates=(("curriculum_review", "A3"),),
        handoffs=(
            HandoffRule(
                target_kind="store",
                target_id="work-intelligence",
                payload_data_classes=("validated_finding", "research_provenance"),
                prerequisite="Completed findings only; pathway-change findings must already carry the A3 curriculum authorization record.",
            ),
        ),
        terminal_record="finding",
        notes=(
            "Research agents recommend; curriculum authorization remains human.",
            "The graph itself does not write a curriculum or Work Intelligence relationship.",
        ),
    ),
    "product_development": GraphContract(
        work_type="product_development",
        graph_id="product-development",
        graph_version="0.1.0",
        purpose="Coordinate product, experience, interface, copy, brand, engineering, cloud, security, accessibility, and quality analysis.",
        definition_factory=ProductDevelopmentGraph.definition,
        runtime_data_classes=("operational", "product_context", "public_research"),
        model_data_classes=("operational", "product_context", "public_research"),
        forbidden_data_classes=COMMON_FORBIDDEN_MODEL_DATA,
        autonomous_effects=("analysis", "prepare", "internal_record"),
        authorization_effects=(("implementation_authorization_record", "A3"),),
        max_service_authority="A2",
        human_gates=(("release_review", "A3"),),
        protected_state_changes=(
            ProtectedStateChange("finalize_release", "record release authorization for later implementation", "A3"),
        ),
        terminal_record="release_record",
        notes=("Release authorization is not deployment or publication.",),
    ),
    "business_operations": GraphContract(
        work_type="business_operations",
        graph_id="business-operations",
        graph_version="0.1.0",
        purpose="Route bounded growth, marketing, partnerships, operations, and finance analysis through explicit action classes.",
        definition_factory=BusinessOperationsGraph.definition,
        runtime_data_classes=("operational", "business_context", "organization_aggregate", "financial_summary", "public_research"),
        model_data_classes=("operational", "business_context", "organization_aggregate", "financial_summary", "public_research"),
        forbidden_data_classes=COMMON_FORBIDDEN_MODEL_DATA,
        autonomous_effects=("analysis", "prepare", "internal_record"),
        authorization_effects=(
            ("external_action_authorization_record", "A3"),
            ("financial_commitment_authorization_record", "A4"),
        ),
        max_service_authority="A2",
        human_gates=(
            ("external_action_review", "A3"),
            ("financial_commitment_review", "A4"),
        ),
        protected_state_changes=(
            ProtectedStateChange("finalize_external", "record external-action authorization", "A3"),
            ProtectedStateChange("finalize_financial", "record financial-commitment authorization", "A4"),
        ),
        terminal_record="business_record",
        notes=("The graph authorizes but does not execute external contact, publication, or money movement.",),
    ),
    "learner_execution": GraphContract(
        work_type="learner_execution",
        graph_id="learner-execution",
        graph_version="0.1.0",
        purpose="Provide deidentified coaching and evidence readiness before accountable human capability-evidence review.",
        definition_factory=LearnerExecutionGraph.definition,
        runtime_data_classes=(
            "learner_private_reference",
            "learner_evidence_reference",
            "deidentified_learning_metadata",
            "capability_standard",
        ),
        model_data_classes=("deidentified_learning_metadata", "capability_standard"),
        forbidden_data_classes=COMMON_FORBIDDEN_MODEL_DATA,
        autonomous_effects=("analysis", "internal_record"),
        authorization_effects=(("learner_capability_evidence_write", "A3"),),
        executable_effects=(("learner_capability_evidence_write", "A3"),),
        human_gates=(("human_assessment", "A3"),),
        protected_state_changes=(
            ProtectedStateChange("accept_evidence", "write human-accepted learner capability evidence", "A3"),
        ),
        handoffs=(
            HandoffRule(
                target_kind="graph",
                target_id="career-mobility",
                payload_data_classes=("learner_private_reference",),
                prerequisite="The learner instance must contain capability evidence already accepted through the A3 evidence-review gate.",
                required_human_authority="A3",
            ),
        ),
        terminal_record="assessment_record",
        notes=("Raw learner submissions stay outside model context.",),
    ),
    "career_mobility": GraphContract(
        work_type="career_mobility",
        graph_id="career-mobility",
        graph_version="0.1.0",
        purpose="Interpret human-accepted capability evidence against research-backed role relationships for learner-facing career guidance.",
        definition_factory=CareerMobilityGraph.definition,
        runtime_data_classes=("learner_private_reference", "deidentified_accepted_capability_metadata", "work_intelligence"),
        model_data_classes=("deidentified_accepted_capability_metadata", "work_intelligence"),
        forbidden_data_classes=COMMON_FORBIDDEN_MODEL_DATA,
        autonomous_effects=("analysis", "prepare", "internal_record"),
        terminal_record="career_packet",
        notes=(
            "Evidence alignment is not hiring likelihood.",
            "The graph performs no application, employer contact, publication, licensing, or immigration decision.",
        ),
    ),
    "employer_workforce": GraphContract(
        work_type="employer_workforce",
        graph_id="employer-workforce",
        graph_version="0.1.0",
        purpose="Analyze organization-level workflows, bounded AI opportunities, role/task change, capability signals, risk, pilots, and measurement.",
        definition_factory=EmployerWorkforceGraph.definition,
        runtime_data_classes=("organization_local_reference", "organization_workflow", "aggregate_metrics", "public_research"),
        model_data_classes=("organization_workflow", "aggregate_metrics", "public_research"),
        forbidden_data_classes=COMMON_FORBIDDEN_MODEL_DATA,
        autonomous_effects=("analysis", "prepare", "internal_record"),
        handoffs=(
            HandoffRule(
                target_kind="graph",
                target_id="canadian-work-research",
                payload_data_classes=("organization_aggregate", "capability_signal"),
                prerequisite="Employer capability demand is a signal only and must be independently validated by Research Intelligence before Work Intelligence changes.",
            ),
        ),
        terminal_record="employer_workforce_packet",
        notes=(
            "The graph makes no individual employment decision.",
            "Employer capability signals require Research Intelligence validation before Work Intelligence can change.",
        ),
    ),
}

GRAPH_ID_TO_WORK_TYPE = {contract.graph_id: work_type for work_type, contract in GRAPH_CONTRACTS.items()}


def get_graph_contract(work_type: str) -> GraphContract:
    try:
        return GRAPH_CONTRACTS[work_type]
    except KeyError as exc:
        supported = ", ".join(sorted(GRAPH_CONTRACTS))
        raise ValueError(f"unknown platform work type {work_type!r}; supported: {supported}") from exc


def graph_registry_manifest() -> list[dict[str, object]]:
    return [GRAPH_CONTRACTS[key].manifest() for key in sorted(GRAPH_CONTRACTS)]
