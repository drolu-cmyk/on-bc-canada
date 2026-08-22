"""Static harness for platform graph authority and topology contracts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from runtime.graph_kernel import GraphDefinition
from runtime.platform_graph_registry import GRAPH_CONTRACTS, GraphContract, ProtectedStateChange, get_graph_contract


_AUTHORITY_RANK = {"A0": 0, "A1": 1, "A2": 2, "A3": 3, "A4": 4}
_EXTERNAL_HANDLER_TOKENS = (".deploy", ".publish", ".send", ".transfer", ".payment", ".message", ".email")


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


class PlatformGraphHarness:
    def validate_contract(self, contract: GraphContract) -> HarnessReport:
        definition = contract.definition()
        issues: list[HarnessIssue] = []

        if definition.graph_id != contract.graph_id:
            issues.append(self._issue(definition, "graph_identity", f"registry graph_id is {contract.graph_id!r}"))

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

    @staticmethod
    def _issue(definition: GraphDefinition, rule: str, detail: str) -> HarnessIssue:
        return HarnessIssue(definition.graph_id, rule, detail)

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


def harness_manifest() -> dict[str, object]:
    harness = PlatformGraphHarness()
    reports = harness.validate_registry()
    return {
        "passed": all(report.passed for report in reports),
        "graphs": [report.as_dict() for report in reports],
    }
