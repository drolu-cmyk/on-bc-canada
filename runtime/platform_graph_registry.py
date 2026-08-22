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


@dataclass(frozen=True)
class ProtectedStateChange:
    node_id: str
    effect: str
    required_human_authority: str


@dataclass(frozen=True)
class GraphContract:
    work_type: str
    graph_id: str
    purpose: str
    definition_factory: Callable[[], GraphDefinition] = field(repr=False, compare=False)
    model_data_classes: tuple[str, ...] = ()
    max_agent_authority: str = "A1"
    max_service_authority: str = "A1"
    human_gates: tuple[tuple[str, str], ...] = ()
    protected_state_changes: tuple[ProtectedStateChange, ...] = ()
    terminal_record: str = ""
    executes_external_effects: bool = False
    requires_openai_api_key: bool = True
    notes: tuple[str, ...] = ()

    def definition(self) -> GraphDefinition:
        return self.definition_factory()

    def manifest(self) -> dict[str, object]:
        definition = self.definition()
        return {
            "work_type": self.work_type,
            "graph_id": self.graph_id,
            "graph_version": definition.version,
            "purpose": self.purpose,
            "model_data_classes": list(self.model_data_classes),
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
            "terminal_record": self.terminal_record,
            "executes_external_effects": self.executes_external_effects,
            "requires_openai_api_key": self.requires_openai_api_key,
            "notes": list(self.notes),
        }


GRAPH_CONTRACTS: dict[str, GraphContract] = {
    "research_intelligence": GraphContract(
        work_type="research_intelligence",
        graph_id="canadian-work-research",
        purpose="Validate Canadian technical-work signals before they influence platform intelligence.",
        definition_factory=ResearchGraph.definition,
        model_data_classes=("public_research", "attributable_evidence"),
        human_gates=(("curriculum_review", "A3"),),
        terminal_record="finding",
        notes=(
            "Research agents recommend; curriculum authorization remains human.",
            "The graph itself does not write a curriculum or Work Intelligence relationship.",
        ),
    ),
    "product_development": GraphContract(
        work_type="product_development",
        graph_id="product-development",
        purpose="Coordinate product, experience, interface, copy, brand, engineering, cloud, security, accessibility, and quality analysis.",
        definition_factory=ProductDevelopmentGraph.definition,
        model_data_classes=("operational", "product_context"),
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
        purpose="Route bounded growth, marketing, partnerships, operations, and finance analysis through explicit action classes.",
        definition_factory=BusinessOperationsGraph.definition,
        model_data_classes=("operational", "business_context"),
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
        purpose="Provide deidentified coaching and evidence readiness before accountable human capability-evidence review.",
        definition_factory=LearnerExecutionGraph.definition,
        model_data_classes=("deidentified_learning_metadata",),
        human_gates=(("human_assessment", "A3"),),
        protected_state_changes=(
            ProtectedStateChange("accept_evidence", "write human-accepted learner capability evidence", "A3"),
        ),
        terminal_record="assessment_record",
        notes=("Raw learner submissions stay outside model context.",),
    ),
    "career_mobility": GraphContract(
        work_type="career_mobility",
        graph_id="career-mobility",
        purpose="Interpret human-accepted capability evidence against research-backed role relationships for learner-facing career guidance.",
        definition_factory=CareerMobilityGraph.definition,
        model_data_classes=("deidentified_accepted_capability_metadata", "work_intelligence"),
        terminal_record="career_packet",
        notes=(
            "Evidence alignment is not hiring likelihood.",
            "The graph performs no application, employer contact, publication, licensing, or immigration decision.",
        ),
    ),
    "employer_workforce": GraphContract(
        work_type="employer_workforce",
        graph_id="employer-workforce",
        purpose="Analyze organization-level workflows, bounded AI opportunities, role/task change, capability signals, risk, pilots, and measurement.",
        definition_factory=EmployerWorkforceGraph.definition,
        model_data_classes=("organization_workflow", "aggregate_metrics"),
        terminal_record="employer_workforce_packet",
        notes=(
            "The graph makes no individual employment decision.",
            "Employer capability signals require Research Intelligence validation before Work Intelligence can change.",
        ),
    ),
}


def get_graph_contract(work_type: str) -> GraphContract:
    try:
        return GRAPH_CONTRACTS[work_type]
    except KeyError as exc:
        supported = ", ".join(sorted(GRAPH_CONTRACTS))
        raise ValueError(f"unknown platform work type {work_type!r}; supported: {supported}") from exc


def graph_registry_manifest() -> list[dict[str, object]]:
    return [GRAPH_CONTRACTS[key].manifest() for key in sorted(GRAPH_CONTRACTS)]
