"""Platform harness for graph authority, data, effect, and handoff contracts."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Literal

from runtime.graph_kernel import GraphDefinition
from runtime.platform_graph_registry import (
    EXTERNAL_EXECUTION_EFFECTS,
    GRAPH_CONTRACTS,
    GRAPH_ID_TO_WORK_TYPE,
    STORE_IDS,
    GraphContract,
    ProtectedStateChange,
    get_graph_contract,
)


_AUTHORITY_RANK = {"A0": 0, "A1": 1, "A2": 2, "A3": 3, "A4": 4}
_EXTERNAL_HANDLER_TOKENS = (".deploy", ".publish", ".send", ".transfer", ".payment", ".message", ".email")
DispatchMode = Literal["analyze", "authorize", "execute"]
TargetKind = Literal["graph", "store"]


def authority_rank(value: str) -> int:
    try:
        return _AUTHORITY_RANK[value]
    except KeyError as exc:
        raise ValueError(f"unknown authority level: {value}") from exc


@dataclass(frozen=True)
class HarnessIssue:
    graph_id: str
    rule: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"graph_id": self.graph_id, "rule": self.rule, "detail": self.detail}


@dataclass(frozen=True)
class HarnessReport:
    graph_id: str
    graph_version: str
    passed: bool
    issues: tuple[HarnessIssue, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "graph_id": self.graph_id,
            "graph_version": self.graph_version,
            "passed": self.passed,
            "issues": [item.as_dict() for item in self.issues],
        }


@dataclass(frozen=True)
class DispatchRequest:
    work_type: str
    mode: DispatchMode
    requested_effect: str
    data_classes: tuple[str, ...]


@dataclass(frozen=True)
class DispatchDecision:
    allowed: bool
    work_type: str
    graph_id: str | None
    graph_version: str | None
    required_authority: str | None
    reason: str
    execution_boundary: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class HarnessCase:
    case_id: str
    request: DispatchRequest
    expected_allowed: bool
    expected_authority: str | None = None
    reason_contains: str | None = None


class PlatformGraphHarness:
    def validate_contract(self, contract: GraphContract) -> HarnessReport:
        definition = contract.definition()
        issues: list[HarnessIssue] = []

        if definition.graph_id != contract.graph_id:
            issues.append(self._issue(definition, "graph_identity", f"registry graph_id is {contract.graph_id!r}"))
        if contract.graph_version and definition.version != contract.graph_version:
            issues.append(
                self._issue(
                    definition,
                    "graph_version",
                    f"actual version {definition.version!r} does not match registry {contract.graph_version!r}",
                )
            )

        node_ids = {node.node_id for node in definition.nodes}
        if not contract.terminal_record.strip():
            issues.append(self._issue(definition, "terminal_record", "registry terminal record is empty"))

        for node in definition.nodes:
            try:
                rank = authority_rank(node.actor.authority)
            except ValueError as exc:
                issues.append(self._issue(definition, "authority_level", f"{node.node_id}: {exc}"))
                continue
            if node.actor.kind == "agent" and rank > authority_rank(contract.max_agent_authority):
                issues.append(
                    self._issue(
                        definition,
                        "agent_authority",
                        f"agent node {node.node_id} has {node.actor.authority}, above {contract.max_agent_authority}",
                    )
                )
            if node.actor.kind == "service" and rank > authority_rank(contract.max_service_authority):
                issues.append(
                    self._issue(
                        definition,
                        "service_authority",
                        f"service node {node.node_id} has {node.actor.authority}, above {contract.max_service_authority}",
                    )
                )
            if not contract.executes_external_effects and node.handler:
                lowered = node.handler.casefold()
                if any(token in lowered for token in _EXTERNAL_HANDLER_TOKENS):
                    issues.append(
                        self._issue(
                            definition,
                            "external_effect_handler",
                            f"handler {node.handler!r} looks like an external effect but the graph contract forbids execution",
                        )
                    )

        declared_gates = dict(contract.human_gates)
        actual_gates = {node.node_id: node.actor.authority for node in definition.nodes if node.actor.kind == "human"}
        if actual_gates != declared_gates:
            issues.append(
                self._issue(
                    definition,
                    "human_gates",
                    f"actual human gates {actual_gates!r} do not match registry {declared_gates!r}",
                )
            )

        model_allowed = set(contract.model_data_classes)
        runtime_allowed = set(contract.runtime_data_classes)
        forbidden = set(contract.forbidden_data_classes)
        if not model_allowed.issubset(runtime_allowed):
            issues.append(self._issue(definition, "model_data", "model data classes exceed the runtime data contract"))
        overlap = model_allowed & forbidden
        if overlap:
            issues.append(
                self._issue(
                    definition,
                    "model_data",
                    f"model data contract contains forbidden classes: {', '.join(sorted(overlap))}",
                )
            )

        human_authorities = set(declared_gates.values())
        for effect, required_authority in contract.authorization_effects:
            if required_authority not in human_authorities:
                issues.append(
                    self._issue(
                        definition,
                        "authorization_effect",
                        f"authorization effect {effect!r} requires {required_authority} but no matching human gate is registered",
                    )
                )
        for effect, required_authority in contract.executable_effects:
            if effect in EXTERNAL_EXECUTION_EFFECTS and not contract.executes_external_effects:
                issues.append(
                    self._issue(
                        definition,
                        "execution_effect",
                        f"registry grants external execution effect {effect!r} while external execution is disabled",
                    )
                )
            if authority_rank(required_authority) > authority_rank("A1") and required_authority not in human_authorities:
                issues.append(
                    self._issue(
                        definition,
                        "execution_effect",
                        f"execution effect {effect!r} requires {required_authority} but no matching human gate is registered",
                    )
                )

        for change in contract.protected_state_changes:
            if change.node_id not in node_ids:
                issues.append(
                    self._issue(
                        definition,
                        "protected_state_change",
                        f"protected node {change.node_id!r} does not exist",
                    )
                )
                continue
            path_authorities = self._human_authorities_on_paths(definition, change.node_id)
            if not path_authorities:
                issues.append(
                    self._issue(
                        definition,
                        "protected_state_change",
                        f"no path reaches protected node {change.node_id!r}",
                    )
                )
                continue
            required = authority_rank(change.required_human_authority)
            if any(value < required for value in path_authorities):
                issues.append(
                    self._issue(
                        definition,
                        "protected_state_change",
                        f"not every path to {change.node_id!r} passes human authority {change.required_human_authority} or higher; observed {path_authorities}",
                    )
                )

        for handoff in contract.handoffs:
            if handoff.target_kind == "graph":
                exists = handoff.target_id in GRAPH_ID_TO_WORK_TYPE
            elif handoff.target_kind == "store":
                exists = handoff.target_id in STORE_IDS
            else:
                exists = False
            if not exists:
                issues.append(
                    self._issue(
                        definition,
                        "handoff",
                        f"handoff target is not registered: {handoff.target_kind}:{handoff.target_id}",
                    )
                )
            if handoff.required_human_authority and handoff.required_human_authority not in human_authorities:
                issues.append(
                    self._issue(
                        definition,
                        "handoff",
                        f"handoff requires {handoff.required_human_authority} but the graph has no matching human gate",
                    )
                )

        return HarnessReport(
            graph_id=definition.graph_id,
            graph_version=definition.version,
            passed=not issues,
            issues=tuple(issues),
        )

    def validate_registry(self) -> list[HarnessReport]:
        reports = [self.validate_contract(GRAPH_CONTRACTS[key]) for key in sorted(GRAPH_CONTRACTS)]
        graph_ids = [report.graph_id for report in reports]
        if len(graph_ids) != len(set(graph_ids)):
            duplicate = HarnessIssue("platform-registry", "graph_identity", "graph IDs must be unique across registered work types")
            reports.append(HarnessReport("platform-registry", "1", False, (duplicate,)))
        return reports

    def require_valid_registry(self) -> list[HarnessReport]:
        reports = self.validate_registry()
        failures = [issue for report in reports for issue in report.issues]
        if failures:
            detail = "; ".join(f"{item.graph_id}:{item.rule}:{item.detail}" for item in failures)
            raise ValueError(f"platform graph harness failed: {detail}")
        return reports

    @staticmethod
    def route(work_type: str) -> dict[str, object]:
        """Return the explicit graph contract for a work type without model classification."""
        return get_graph_contract(work_type).manifest()

    def validate_dispatch(self, request: DispatchRequest) -> DispatchDecision:
        try:
            contract = get_graph_contract(request.work_type)
        except ValueError as exc:
            return DispatchDecision(False, request.work_type, None, None, None, str(exc), "Blocked before graph execution.")

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
                if request.requested_effect in EXTERNAL_EXECUTION_EFFECTS:
                    return self._blocked(contract, "no current graph is allowed to execute this external or consequential effect")
                return self._blocked(contract, f"effect is not executable in this graph: {request.requested_effect}")
            return self._allowed(
                contract,
                authority,
                f"Execution is permitted only after the in-graph {authority} authorization boundary is satisfied.",
            )

        return self._blocked(contract, f"unsupported dispatch mode: {request.mode}")

    def validate_model_context(self, work_type: str, data_classes: tuple[str, ...]) -> DispatchDecision:
        try:
            contract = get_graph_contract(work_type)
        except ValueError as exc:
            return DispatchDecision(False, work_type, None, None, None, str(exc), "No model call is permitted.")
        declared = set(data_classes)
        forbidden = declared & set(contract.forbidden_data_classes)
        if forbidden:
            return self._blocked(contract, f"model context contains forbidden data classes: {', '.join(sorted(forbidden))}")
        unsupported = declared - set(contract.model_data_classes)
        if unsupported:
            return self._blocked(contract, f"model context contains data classes outside the model contract: {', '.join(sorted(unsupported))}")
        return self._allowed(contract, "A1", "Model context is inside the registered data boundary.")

    def validate_handoff(
        self,
        *,
        source_work_type: str,
        target_kind: TargetKind,
        target_id: str,
        payload_data_classes: tuple[str, ...],
    ) -> dict[str, object]:
        contract = get_graph_contract(source_work_type)
        target_exists = target_id in GRAPH_ID_TO_WORK_TYPE if target_kind == "graph" else target_id in STORE_IDS
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
                    "required_human_authority": rule.required_human_authority,
                    "target": f"{target_kind}:{target_id}",
                }
        return {
            "allowed": False,
            "reason": f"direct handoff is not registered from {source_work_type} to {target_kind}:{target_id}",
        }

    @staticmethod
    def _issue(definition: GraphDefinition, rule: str, detail: str) -> HarnessIssue:
        return HarnessIssue(definition.graph_id, rule, detail)

    @staticmethod
    def _blocked(contract: GraphContract, reason: str) -> DispatchDecision:
        definition = contract.definition()
        return DispatchDecision(
            False,
            contract.work_type,
            contract.graph_id,
            definition.version,
            None,
            reason,
            "Blocked before graph execution.",
        )

    @staticmethod
    def _allowed(contract: GraphContract, authority: str, reason: str) -> DispatchDecision:
        definition = contract.definition()
        return DispatchDecision(
            True,
            contract.work_type,
            contract.graph_id,
            definition.version,
            authority,
            reason,
            "The selected graph remains responsible for its own evaluators, human gates, and persistence boundaries.",
        )

    @staticmethod
    def _human_authorities_on_paths(definition: GraphDefinition, target_node: str) -> list[int]:
        outgoing: dict[str, list[str]] = {}
        for edge in definition.edges:
            outgoing.setdefault(edge.source, []).append(edge.target)
        nodes = {node.node_id: node for node in definition.nodes}
        observed: list[int] = []

        def walk(node_id: str, highest_human: int, path: tuple[str, ...]) -> None:
            if node_id in path:
                return
            node = nodes[node_id]
            next_highest = highest_human
            if node.actor.kind == "human":
                next_highest = max(next_highest, authority_rank(node.actor.authority))
            if node_id == target_node:
                observed.append(next_highest)
                return
            for target in outgoing.get(node_id, []):
                walk(target, next_highest, (*path, node_id))

        walk(definition.start_node, 0, ())
        return observed


HARNESS_CASES: tuple[HarnessCase, ...] = (
    HarnessCase(
        "research-public-analysis",
        DispatchRequest("research_intelligence", "analyze", "analysis", ("public_research",)),
        True,
        "A1",
    ),
    HarnessCase(
        "product-production-mutation-blocked",
        DispatchRequest("product_development", "execute", "production_mutation", ("operational",)),
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
        DispatchRequest("learner_execution", "analyze", "analysis", ("deidentified_learning_metadata", "capability_standard")),
        True,
        "A1",
    ),
    HarnessCase(
        "learner-raw-submission-blocked",
        DispatchRequest("learner_execution", "analyze", "analysis", ("raw_learner_submission",)),
        False,
        reason_contains="forbidden data classes",
    ),
    HarnessCase(
        "learner-evidence-write-gated",
        DispatchRequest(
            "learner_execution",
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
            ("deidentified_accepted_capability_metadata", "work_intelligence"),
        ),
        True,
        "A1",
    ),
    HarnessCase(
        "employer-aggregate-analysis",
        DispatchRequest("employer_workforce", "analyze", "analysis", ("organization_workflow", "aggregate_metrics")),
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


def evaluate_harness_cases(harness: PlatformGraphHarness | None = None) -> dict[str, object]:
    active = harness or PlatformGraphHarness()
    results: list[dict[str, object]] = []
    for case in HARNESS_CASES:
        decision = active.validate_dispatch(case.request)
        passed = decision.allowed == case.expected_allowed
        if case.expected_authority is not None:
            passed = passed and decision.required_authority == case.expected_authority
        if case.reason_contains is not None:
            passed = passed and case.reason_contains in decision.reason
        results.append({"case_id": case.case_id, "passed": passed, "decision": decision.as_dict()})
    return {
        "passed": all(item["passed"] for item in results),
        "case_count": len(results),
        "results": results,
    }


def harness_manifest() -> dict[str, object]:
    harness = PlatformGraphHarness()
    reports = harness.validate_registry()
    cases = evaluate_harness_cases(harness)
    return {
        "passed": all(report.passed for report in reports) and cases["passed"],
        "graphs": [report.as_dict() for report in reports],
        "dispatch_cases": cases,
    }
