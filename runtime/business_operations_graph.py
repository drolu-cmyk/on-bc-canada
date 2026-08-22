"""Routed Business Operations Graph for bounded autonomous operating work.

The request explicitly selects a workstream. Deterministic policy decides whether
an output can finish as analysis/preparation, must stop at an A3 external-action
gate, must stop at an A4 financial-commitment gate, or is blocked.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from runtime.graph_kernel import ActorRef, GraphDefinition, GraphEdge, GraphKernel, GraphNode, NodeResult


Workstream = Literal["growth", "marketing", "partnerships", "operations", "finance"]
ActionClass = Literal["analysis", "prepare", "external_publish", "external_contact", "financial_commitment"]

_ALLOWED_WORKSTREAMS = {"growth", "marketing", "partnerships", "operations", "finance"}
_ALLOWED_ACTIONS = {"analysis", "prepare", "external_publish", "external_contact", "financial_commitment"}
_ALLOWED_COMBINATIONS = {
    "growth": {"analysis", "prepare", "external_publish"},
    "marketing": {"analysis", "prepare", "external_publish"},
    "partnerships": {"analysis", "prepare", "external_contact"},
    "operations": {"analysis", "prepare", "external_contact"},
    "finance": {"analysis", "prepare", "external_contact", "financial_commitment"},
}


class BusinessOperationsProvider(Protocol):
    def normalize(self, request: dict[str, Any]) -> dict[str, Any]: ...
    def analyze_growth(self, request: dict[str, Any]) -> dict[str, Any]: ...
    def analyze_marketing(self, request: dict[str, Any]) -> dict[str, Any]: ...
    def analyze_partnerships(self, request: dict[str, Any]) -> dict[str, Any]: ...
    def analyze_operations(self, request: dict[str, Any]) -> dict[str, Any]: ...
    def analyze_finance(self, request: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class BusinessOperationsGraph:
    kernel: GraphKernel
    provider: BusinessOperationsProvider

    @staticmethod
    def definition() -> GraphDefinition:
        def service(actor_id: str, authority: str = "A1") -> ActorRef:
            return ActorRef(actor_id=actor_id, kind="service", authority=authority)

        def agent(actor_id: str) -> ActorRef:
            return ActorRef(actor_id=actor_id, kind="agent", authority="A1")

        return GraphDefinition(
            graph_id="business-operations",
            version="0.1.0",
            start_node="normalize_request",
            nodes=(
                GraphNode("normalize_request", service("business-contract"), "business.normalize", "business.request"),
                GraphNode("growth_analysis", agent("growth-agent"), "business.growth", "business.output"),
                GraphNode("marketing_analysis", agent("marketing-agent"), "business.marketing", "business.output"),
                GraphNode("partnership_analysis", agent("partnership-agent"), "business.partnerships", "business.output"),
                GraphNode("operations_analysis", agent("operations-agent"), "business.operations", "business.output"),
                GraphNode("finance_analysis", agent("finance-agent"), "business.finance", "business.output"),
                GraphNode("operating_assurance", service("business-assurance"), "business.assure", "business.assurance"),
                GraphNode(
                    "external_action_review",
                    ActorRef("external-action-accountable-human", "human", authority="A3"),
                    approval_reason="External publication or contact requires accountable human authorization.",
                ),
                GraphNode(
                    "financial_commitment_review",
                    ActorRef("financial-accountable-human", "human", authority="A4"),
                    approval_reason="Financial commitment requires accountable human authorization.",
                ),
                GraphNode("finalize_direct", service("business-record"), "business.finalize_direct", "business.final"),
                GraphNode("finalize_external", service("business-record", authority="A2"), "business.finalize_external", "business.final"),
                GraphNode("finalize_financial", service("business-record", authority="A2"), "business.finalize_financial", "business.final"),
                GraphNode("finalize_blocked", service("business-blocked-record"), "business.finalize_blocked", "business.final"),
            ),
            edges=(
                GraphEdge("normalize_request", "growth_analysis", route="growth"),
                GraphEdge("normalize_request", "marketing_analysis", route="marketing"),
                GraphEdge("normalize_request", "partnership_analysis", route="partnerships"),
                GraphEdge("normalize_request", "operations_analysis", route="operations"),
                GraphEdge("normalize_request", "finance_analysis", route="finance"),
                GraphEdge("growth_analysis", "operating_assurance"),
                GraphEdge("marketing_analysis", "operating_assurance"),
                GraphEdge("partnership_analysis", "operating_assurance"),
                GraphEdge("operations_analysis", "operating_assurance"),
                GraphEdge("finance_analysis", "operating_assurance"),
                GraphEdge("operating_assurance", "finalize_direct", route="direct"),
                GraphEdge("operating_assurance", "external_action_review", route="a3"),
                GraphEdge("operating_assurance", "financial_commitment_review", route="a4"),
                GraphEdge("operating_assurance", "finalize_blocked", route="blocked"),
                GraphEdge("external_action_review", "finalize_external", route="approved"),
                GraphEdge("financial_commitment_review", "finalize_financial", route="approved"),
            ),
        )

    def register(self) -> None:
        handlers = {
            "business.normalize": self._normalize,
            "business.growth": self._growth,
            "business.marketing": self._marketing,
            "business.partnerships": self._partnerships,
            "business.operations": self._operations,
            "business.finance": self._finance,
            "business.assure": self._assure,
            "business.finalize_direct": self._finalize_direct,
            "business.finalize_external": self._finalize_external,
            "business.finalize_financial": self._finalize_financial,
            "business.finalize_blocked": self._finalize_blocked,
        }
        for name, handler in handlers.items():
            self.kernel.register_handler(name, handler)

        self.kernel.register_evaluator(
            "business.request",
            lambda state, result: (
                bool(result.patch.get("request", {}).get("problem"))
                and result.route in _ALLOWED_WORKSTREAMS,
                "validated business request and workstream required",
            ),
        )
        self.kernel.register_evaluator(
            "business.output",
            lambda state, result: (
                isinstance(result.patch.get("work_output"), dict)
                and result.patch.get("work_output", {}).get("status") in {"pass", "warn", "block"},
                "typed workstream output required",
            ),
        )
        self.kernel.register_evaluator(
            "business.assurance",
            lambda state, result: (
                "operating_assurance" in result.patch and result.route in {"direct", "a3", "a4", "blocked"},
                "operating assurance route required",
            ),
        )
        self.kernel.register_evaluator(
            "business.final",
            lambda state, result: ("business_record" in result.patch, "business terminal record required"),
        )

    def start(self, *, execution_id: str, request: dict[str, Any]):
        definition = self.definition()
        execution = self.kernel.start(
            definition,
            execution_id=execution_id,
            state={"input_request": request, "business_status": "started"},
        )
        return definition, self.kernel.run(definition, execution)

    def _normalize(self, state: dict[str, Any]) -> NodeResult:
        request = self.provider.normalize(state["input_request"])
        workstream = request["workstream"]
        return NodeResult(
            patch={"request": request},
            evidence=[{"type": "business_request", "workstream": workstream, "action_class": request["action_class"]}],
            route=workstream,
        )

    def _growth(self, state: dict[str, Any]) -> NodeResult:
        return self._work_result("growth", self.provider.analyze_growth(state["request"]))

    def _marketing(self, state: dict[str, Any]) -> NodeResult:
        return self._work_result("marketing", self.provider.analyze_marketing(state["request"]))

    def _partnerships(self, state: dict[str, Any]) -> NodeResult:
        return self._work_result("partnerships", self.provider.analyze_partnerships(state["request"]))

    def _operations(self, state: dict[str, Any]) -> NodeResult:
        return self._work_result("operations", self.provider.analyze_operations(state["request"]))

    def _finance(self, state: dict[str, Any]) -> NodeResult:
        return self._work_result("finance", self.provider.analyze_finance(state["request"]))

    @staticmethod
    def _work_result(workstream: str, output: dict[str, Any]) -> NodeResult:
        return NodeResult(
            patch={"work_output": output, "executed_workstream": workstream},
            evidence=[{"type": "business_workstream_analysis", "workstream": workstream, "status": output.get("status")}],
        )

    @staticmethod
    def _assure(state: dict[str, Any]) -> NodeResult:
        request = state["request"]
        output = state["work_output"]
        action_class = request["action_class"]
        blockers = list(output.get("blockers", []))
        if output.get("status") == "block" and not blockers:
            blockers = ["workstream analysis returned blocking status"]

        if blockers:
            route = "blocked"
            authority = None
        elif action_class in {"analysis", "prepare"}:
            route = "direct"
            authority = "A1"
        elif action_class in {"external_publish", "external_contact"}:
            route = "a3"
            authority = "A3"
        elif action_class == "financial_commitment":
            route = "a4"
            authority = "A4"
        else:
            route = "blocked"
            authority = None
            blockers = ["unsupported action class"]

        assurance = {
            "status": "blocked" if blockers else "ready",
            "required_authority": authority,
            "action_class": action_class,
            "blockers": blockers,
            "warnings": list(output.get("warnings", [])),
        }
        return NodeResult(
            patch={"operating_assurance": assurance},
            evidence=[{"type": "business_assurance", "required_authority": authority, "blocker_count": len(blockers)}],
            route=route,
        )

    @staticmethod
    def _record(state: dict[str, Any], status: str) -> dict[str, Any]:
        return {
            "status": status,
            "workstream": state["request"]["workstream"],
            "action_class": state["request"]["action_class"],
            "request": state["request"],
            "output": state["work_output"],
            "assurance": state["operating_assurance"],
        }

    @classmethod
    def _finalize_direct(cls, state: dict[str, Any]) -> NodeResult:
        status = "analysis_complete" if state["request"]["action_class"] == "analysis" else "prepared"
        record = cls._record(state, status)
        return NodeResult(
            patch={"business_record": record, "business_status": status},
            evidence=[{"type": "business_terminal_record", "status": status}],
        )

    @classmethod
    def _finalize_external(cls, state: dict[str, Any]) -> NodeResult:
        record = cls._record(state, "authorized_for_external_execution")
        return NodeResult(
            patch={"business_record": record, "business_status": record["status"]},
            evidence=[{"type": "business_terminal_record", "status": record["status"]}],
        )

    @classmethod
    def _finalize_financial(cls, state: dict[str, Any]) -> NodeResult:
        record = cls._record(state, "authorized_for_financial_execution")
        return NodeResult(
            patch={"business_record": record, "business_status": record["status"]},
            evidence=[{"type": "business_terminal_record", "status": record["status"]}],
        )

    @classmethod
    def _finalize_blocked(cls, state: dict[str, Any]) -> NodeResult:
        record = cls._record(state, "blocked")
        return NodeResult(
            patch={"business_record": record, "business_status": "blocked"},
            evidence=[{"type": "business_terminal_record", "status": "blocked"}],
        )
