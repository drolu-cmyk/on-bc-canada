"""Platform-level registry and deterministic orchestration guardrails.

The harness sits above individual graphs. A manager may propose a workflow, but
this module decides whether the workflow, data classes, requested effect, and
handoff are actually permitted. It does not execute graph work or external side
effects.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from runtime.business_operations_graph import BusinessOperationsGraph
from runtime.career_mobility_graph import CareerMobilityGraph
from runtime.employer_workforce_graph import EmployerWorkforceGraph
from runtime.learner_execution_graph import LearnerExecutionGraph
from runtime.product_development_graph import ProductDevelopmentGraph
from runtime.research_graph import ResearchGraph


Authority = Literal["A1", "A2", "A3", "A4"]
DispatchMode = Literal["analyze", "authorize", "execute"]
TargetKind = Literal["graph", "store"]

_AUTHORITY_RANK = {"A1": 1, "A2": 2, "A3": 3, "A4": 4}

STORE_IDS = {
    "work-intelligence",
    "capability-graph",
    "learning-graph",
    "learner-progress",
}

SENSITIVE_DATA_CLASSES = {
    "raw_learner_submission",
    "learner_direct_identifier",
    "employee_individual",
    "payment_credential",
    "production_secret",
}

EXTERNAL_EFFECTS = {
    "external_publish",
    "external_contact",
    "financial_transaction",
    "production_mutation",
    "employment_decision",
    "credential_issue",
}


@dataclass(frozen=True)
class HandoffRule:
    target_kind: TargetKind
    target_id: str
    payload_data_classes: tuple[str, ...]
    prerequisite: str
    required_authority: Authority | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowContract:
    workflow_key: str
    graph_id: str
    graph_version: str
    purpose: str
    runtime_data_classes: tuple[str, ...]
    model_data_classes: tuple[str, ...]
    forbidden_data_classes: tuple[str, ...]
    autonomous_effects: tuple[str, ...]
    authorization_effects: tuple[tuple[str, Authority], ...]
    executable_effects: tuple[tuple[str, Authority], ...]
    expected_human_authorities: tuple[Authority, ...]
    handoffs: tuple[HandoffRule, ...] = ()

    @property
    def authorization_map(self) -> dict[str, Authority]:
        return dict(self.authorization_effects)

    @property
    def executable_map(self) -> dict[str, Authority]:
        return dict(self.executable_effects)

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["authorization_effects"] = dict(self.authorization_effects)
        value["executable_effects"] = dict(self.executable_effects)
        return value


@dataclass(frozen=True)
class DispatchRequest:
    workflow_key: str
    mode: DispatchMode
    requested_effect: str
    data_classes: tuple[str, ...]


@dataclass(frozen=True)
class DispatchDecision:
    allowed: bool
    workflow_key: str
    graph_id: str | None
    graph_version: str | None
    required_authority: Authority | None
    reason: str
    execution_boundary: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class HarnessCase:
    case_id: str
    request: DispatchRequest
    expected_allowed: bool
    expected_authority: Authority | None = None
    reason_contains: str | None = None


WORKFLOW_CONTRACTS: dict[str, WorkflowContract] = {
    "research_evidence": WorkflowContract(
        workflow_key="research_evidence",
        graph_id="canadian-work-research",
        graph_version="0.2.0",
        purpose="Validate Canadian technical-work evidence and propose evidence-backed pathway changes.",
        runtime_data_classes=("public_research", "internal_operational", "organization_aggregate"),
        model_data_classes=("public_research", "internal_operational", "organization_aggregate"),
        forbidden_data_classes=(
            "raw_learner_submission",
            "learner_direct_identifier",
            "employee_individual",
            "payment_credential",
            "production_secret",
        ),
        autonomous_effects=("analysis", "external_read", "internal_record"),
        authorization_effects=(("curriculum_change_authorization_record", "A3"),),
        executable_effects=(),
        expected_human_authorities=("A3",),
        handoffs=(
            HandoffRule(
                target_kind="store",
                target_id="work-intelligence",
                payload_data_classes=("validated_finding", "research_provenance"),
                prerequisite="Completed findings only; pathway-change findings must carry the A3 curriculum authorization record.",
            ),
        ),
    ),
    "product_change": WorkflowContract(
        workflow_key="product_change",
        graph_id="product-development",
        graph_version="0.1.0",
        purpose="Coordinate product, experience, design, copy, engineering, cloud, security, accessibility, and quality analysis.",
        runtime_data_classes=("public_research", "internal_operational"),
        model_data_classes=("public_research", "internal_operational"),
        forbidden_data_classes=(
            "raw_learner_submission",
            "learner_direct_identifier",
            "employee_individual",
            "payment_credential",
            "production_secret",
        ),
        autonomous_effects=("analysis", "prepare", "internal_record"),
        authorization_effects=(("implementation_authorization_record", "A3"),),
        executable_effects=(),
        expected_human_authorities=("A3",),
    ),
    "business_operations": WorkflowContract(
        workflow_key="business_operations",
        graph_id="business-operations",
        graph_version="0.1.0",
        purpose="Analyze growth, marketing, partnerships, operations, and finance while separating authorization from execution.",
        runtime_data_classes=("public_research", "internal_operational", "organization_aggregate", "financial_summary"),
        model_data_classes=("public_research", "internal_operational", "organization_aggregate", "financial_summary"),
        forbidden_data_classes=(
            "raw_learner_submission",
            "learner_direct_identifier",
            "employee_individual",
            "payment_credential",
            "production_secret",
        ),
        autonomous_effects=("analysis", "prepare", "internal_record"),
        authorization_effects=(
            ("external_action_authorization_record", "A3"),
            ("financial_commitment_authorization_record", "A4"),
        ),
        executable_effects=(),
        expected_human_authorities=("A3", "A4"),
    ),
    "learner_support": WorkflowContract(
        workflow_key="learner_support",
        graph_id="learner-execution",
        graph_version="0.1.0",
        purpose="Coach from deidentified readiness metadata and route substantive capability evidence to accountable human review.",
        runtime_data_classes=(
            "learner_private_reference",
            "learner_evidence_reference",
            "learner_deidentified",
            "capability_standard",
        ),
        model_data_classes=("learner_deidentified", "capability_standard"),
        forbidden_data_classes=(
            "raw_learner_submission",
            "learner_direct_identifier",
            "employee_individual",
            "payment_credential",
            "production_secret",
        ),
        autonomous_effects=("analysis", "internal_record"),
        authorization_effects=(("learner_capability_evidence_write", "A3"),),
        executable_effects=(("learner_capability_evidence_write", "A3"),),
        expected_human_authorities=("A3",),
        handoffs=(
            HandoffRule(
                target_kind="graph",
                target_id="career-mobility",
                payload_data_classes=("accepted_capability_metadata", "learner_deidentified"),
                prerequisite="Capability evidence must already have been accepted through the A3 learner evidence-review gate.",
            ),
        ),
    ),
    "career_mobility": WorkflowContract(
        workflow_key="career_mobility",
        graph_id="career-mobility",
        graph_version="0.1.0",
        purpose="Interpret human-accepted capability evidence against research-backed role requirements for learner guidance.",
        runtime_data_classes=(
            "learner_private_reference",
            "learner_deidentified",
            "accepted_capability_metadata",
            "work_intelligence",
        ),
        model_data_classes=("learner_deidentified", "accepted_capability_metadata", "work_intelligence"),
        forbidden_data_classes=(
            "raw_learner_submission",
            "learner_direct_identifier",
            "employee_individual",
            "payment_credential",
            "production_secret",
        ),
        autonomous_effects=("analysis", "prepare", "internal_record"),
        authorization_effects=(),
        executable_effects=(),
        expected_human_authorities=(),
    ),
    "employer_workforce": WorkflowContract(
        workflow_key="employer_workforce",
        graph_id="employer-workforce",
        graph_version="0.1.0",
        purpose="Analyze organization-level workflows, bounded AI opportunities, role/task impact, capability demand, adoption risk, pilots, and measurement.",
        runtime_data_classes=("organization_local_reference", "organization_aggregate", "public_research"),
        model_data_classes=("organization_aggregate", "public_research"),
        forbidden_data_classes=(
            "raw_learner_submission",
            "learner_direct_identifier",
            "employee_individual",
            "payment_credential",
            "production_secret",
        ),
        autonomous_effects=("analysis", "prepare", "internal_record"),
        authorization_effects=(),
        executable_effects=(),
        expected_human_authorities=(),
        handoffs=(
            HandoffRule(
                target_kind="graph",
                target_id="canadian-work-research",
                payload_data_classes=("organization_aggregate", "capability_signal"),
                prerequisite="Employer capability demand is a signal only and must be independently validated by Research Intelligence before Work Intelligence changes.",
            ),
        ),
    ),
}

_GRAPH_DEFINITIONS = {
    "research_evidence": ResearchGraph.definition,
    "product_change": ProductDevelopmentGraph.definition,
    "business_operations": BusinessOperationsGraph.definition,
    "learner_support": LearnerExecutionGraph.definition,
    "career_mobility": CareerMobilityGraph.definition,
    "employer_workforce": EmployerWorkforceGraph.definition,
}

GRAPH_ID_TO_WORKFLOW = {contract.graph_id: key for key, contract in WORKFLOW_CONTRACTS.items()}


class PlatformHarness:
    """Deterministically validate graph routing and cross-graph handoffs."""

    def list_contracts(self) -> list[dict[str, object]]:
        return [WORKFLOW_CONTRACTS[key].as_dict() for key in sorted(WORKFLOW_CONTRACTS)]

    def contract(self, workflow_key: str) -> WorkflowContract:
        try:
            return WORKFLOW_CONTRACTS[workflow_key]
        except KeyError as exc:
            raise KeyError(f"platform workflow not registered: {workflow_key}") from exc

    def validate_dispatch(self, request: DispatchRequest) -> DispatchDecision:
        try:
            contract = self.contract(request.workflow_key)
        except KeyError as exc:
            return DispatchDecision(
                False,
                request.workflow_key,
                None,
                None,
                None,
                str(exc),
                "No graph may run until the workflow is registered.",
            )

        declared = set(request.data_classes)
        forbidden = declared & set(contract.forbidden_data_classes)
        if forbidden:
            return self._blocked(contract, f"forbidden data classes: {', '.join(sorted(forbidden))}")
        unsupported = declared - set(contract.runtime_data_classes)
        if unsupported:
            return self._blocked(contract, f"unsupported data classes: {', '.join(sorted(unsupported))}")

        if request.mode == "analyze":
            if request.requested_effect not in contract.autonomous_effects:
                return self._blocked(contract, f"effect is not autonomous in this graph: {request.requested_effect}")
            return self._allowed(contract, "A1", "Analysis may run inside the registered graph boundary.")

        if request.mode == "authorize":
            authority = contract.authorization_map.get(request.requested_effect)
            if authority is None:
                return self._blocked(contract, f"effect has no authorization route in this graph: {request.requested_effect}")
            return self._allowed(
                contract,
                authority,
                f"The graph may prepare this decision but must stop at the {authority} human gate.",
            )

        if request.mode == "execute":
            authority = contract.executable_map.get(request.requested_effect)
            if authority is None:
                if request.requested_effect in EXTERNAL_EFFECTS:
                    return self._blocked(contract, "no current graph is allowed to execute this external or consequential effect")
                return self._blocked(contract, f"effect is not executable in this graph: {request.requested_effect}")
            return self._allowed(
                contract,
                authority,
                f"Execution is permitted only after the in-graph {authority} authorization boundary is satisfied.",
            )

        return self._blocked(contract, f"unsupported dispatch mode: {request.mode}")

    def validate_model_context(self, workflow_key: str, data_classes: tuple[str, ...]) -> DispatchDecision:
        try:
            contract = self.contract(workflow_key)
        except KeyError as exc:
            return DispatchDecision(False, workflow_key, None, None, None, str(exc), "No model call is permitted.")
        declared = set(data_classes)
        forbidden = declared & set(contract.forbidden_data_classes)
        if forbidden:
            return self._blocked(contract, f"model context contains forbidden data classes: {', '.join(sorted(forbidden))}")
        unsupported = declared - set(contract.model_data_classes)
        if unsupported:
            return self._blocked(contract, f"model context contains data classes outside the model contract: {', '.join(sorted(unsupported))}")
        return self._allowed(contract, "A1", "Model context is inside the declared data boundary.")

    def validate_handoff(
        self,
        *,
        source_workflow_key: str,
        target_kind: TargetKind,
        target_id: str,
        payload_data_classes: tuple[str, ...],
    ) -> dict[str, object]:
        contract = self.contract(source_workflow_key)
        target_exists = target_id in GRAPH_ID_TO_WORKFLOW if target_kind == "graph" else target_id in STORE_IDS
        if not target_exists:
            return {"allowed": False, "reason": f"handoff target is not registered: {target_kind}:{target_id}"}
        for rule in contract.handoffs:
            if rule.target_kind == target_kind and rule.target_id == target_id:
                declared = set(payload_data_classes)
                allowed = set(rule.payload_data_classes)
                if not declared.issubset(allowed):
                    return {
                        "allowed": False,
                        "reason": f"handoff payload exceeds contract: {', '.join(sorted(declared - allowed))}",
                    }
                return {
                    "allowed": True,
                    "reason": rule.prerequisite,
                    "required_authority": rule.required_authority,
                    "target": f"{target_kind}:{target_id}",
                }
        return {
            "allowed": False,
            "reason": f"direct handoff is not registered from {source_workflow_key} to {target_kind}:{target_id}",
        }

    def audit_registry(self) -> dict[str, object]:
        errors: list[str] = []
        for key, contract in WORKFLOW_CONTRACTS.items():
            definition = _GRAPH_DEFINITIONS[key]()
            if definition.graph_id != contract.graph_id:
                errors.append(f"{key}: graph_id drift: {definition.graph_id} != {contract.graph_id}")
            if definition.version != contract.graph_version:
                errors.append(f"{key}: graph_version drift: {definition.version} != {contract.graph_version}")

            agent_nodes = [node for node in definition.nodes if node.actor.kind == "agent"]
            overpowered = [node.node_id for node in agent_nodes if _AUTHORITY_RANK.get(node.actor.authority, 99) > 1]
            if overpowered:
                errors.append(f"{key}: agent authority exceeds A1: {', '.join(sorted(overpowered))}")

            actual_human_authorities = tuple(
                sorted({node.actor.authority for node in definition.nodes if node.actor.kind == "human"}, key=_AUTHORITY_RANK.get)
            )
            expected_human_authorities = tuple(sorted(set(contract.expected_human_authorities), key=_AUTHORITY_RANK.get))
            if actual_human_authorities != expected_human_authorities:
                errors.append(
                    f"{key}: human authority drift: {actual_human_authorities} != {expected_human_authorities}"
                )

            model_allowed = set(contract.model_data_classes)
            runtime_allowed = set(contract.runtime_data_classes)
            forbidden = set(contract.forbidden_data_classes)
            if not model_allowed.issubset(runtime_allowed):
                errors.append(f"{key}: model data classes exceed runtime data contract")
            overlap = model_allowed & forbidden
            if overlap:
                errors.append(f"{key}: model data contract includes forbidden classes: {', '.join(sorted(overlap))}")
            if set(contract.executable_map) & EXTERNAL_EFFECTS:
                errors.append(f"{key}: registry grants an external execution effect")

            for handoff in contract.handoffs:
                exists = handoff.target_id in GRAPH_ID_TO_WORKFLOW if handoff.target_kind == "graph" else handoff.target_id in STORE_IDS
                if not exists:
                    errors.append(f"{key}: handoff target missing: {handoff.target_kind}:{handoff.target_id}")

        return {
            "passed": not errors,
            "workflow_count": len(WORKFLOW_CONTRACTS),
            "store_count": len(STORE_IDS),
            "errors": errors,
        }

    @staticmethod
    def _blocked(contract: WorkflowContract, reason: str) -> DispatchDecision:
        return DispatchDecision(
            False,
            contract.workflow_key,
            contract.graph_id,
            contract.graph_version,
            None,
            reason,
            "Blocked before graph execution.",
        )

    @staticmethod
    def _allowed(contract: WorkflowContract, authority: Authority, reason: str) -> DispatchDecision:
        return DispatchDecision(
            True,
            contract.workflow_key,
            contract.graph_id,
            contract.graph_version,
            authority,
            reason,
            "The selected graph remains responsible for its own evaluators, human gates, and persistence boundaries.",
        )


HARNESS_CASES: tuple[HarnessCase, ...] = (
    HarnessCase(
        "research-public-analysis",
        DispatchRequest("research_evidence", "analyze", "analysis", ("public_research",)),
        True,
        "A1",
    ),
    HarnessCase(
        "product-production-mutation-blocked",
        DispatchRequest("product_change", "execute", "production_mutation", ("internal_operational",)),
        False,
        reason_contains="no current graph",
    ),
    HarnessCase(
        "business-financial-authorization",
        DispatchRequest(
            "business_operations",
            "authorize",
            "financial_commitment_authorization_record",
            ("financial_summary",),
        ),
        True,
        "A4",
    ),
    HarnessCase(
        "business-financial-transaction-blocked",
        DispatchRequest("business_operations", "execute", "financial_transaction", ("financial_summary",)),
        False,
        reason_contains="no current graph",
    ),
    HarnessCase(
        "learner-deidentified-analysis",
        DispatchRequest("learner_support", "analyze", "analysis", ("learner_deidentified", "capability_standard")),
        True,
        "A1",
    ),
    HarnessCase(
        "learner-raw-submission-blocked",
        DispatchRequest("learner_support", "analyze", "analysis", ("raw_learner_submission",)),
        False,
        reason_contains="forbidden data classes",
    ),
    HarnessCase(
        "learner-evidence-write-gated",
        DispatchRequest(
            "learner_support",
            "execute",
            "learner_capability_evidence_write",
            ("learner_private_reference", "learner_evidence_reference", "capability_standard"),
        ),
        True,
        "A3",
    ),
    HarnessCase(
        "career-guidance-from-accepted-evidence",
        DispatchRequest(
            "career_mobility",
            "analyze",
            "analysis",
            ("accepted_capability_metadata", "work_intelligence"),
        ),
        True,
        "A1",
    ),
    HarnessCase(
        "employer-aggregate-analysis",
        DispatchRequest("employer_workforce", "analyze", "analysis", ("organization_aggregate",)),
        True,
        "A1",
    ),
    HarnessCase(
        "employer-individual-data-blocked",
        DispatchRequest("employer_workforce", "analyze", "analysis", ("employee_individual",)),
        False,
        reason_contains="forbidden data classes",
    ),
)


def evaluate_harness_cases(harness: PlatformHarness | None = None) -> dict[str, object]:
    active = harness or PlatformHarness()
    results: list[dict[str, object]] = []
    for case in HARNESS_CASES:
        decision = active.validate_dispatch(case.request)
        passed = decision.allowed == case.expected_allowed
        if case.expected_authority is not None:
            passed = passed and decision.required_authority == case.expected_authority
        if case.reason_contains is not None:
            passed = passed and case.reason_contains in decision.reason
        results.append(
            {
                "case_id": case.case_id,
                "passed": passed,
                "decision": decision.as_dict(),
            }
        )
    return {
        "passed": all(item["passed"] for item in results),
        "case_count": len(results),
        "results": results,
    }
