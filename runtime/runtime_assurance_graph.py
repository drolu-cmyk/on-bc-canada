"""Runtime Assurance graph over aggregate execution and control telemetry.

The graph identifies reliability and governance concerns. It cannot disable an
agent, change authority, mutate production, or change runtime policy directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from runtime.graph_kernel import ActorRef, GraphDefinition, GraphEdge, GraphKernel, GraphNode, NodeResult


class RuntimeAssuranceProvider(Protocol):
    def analyze_reliability(self, snapshot: dict[str, Any]) -> dict[str, Any]: ...
    def analyze_controls(self, snapshot: dict[str, Any], reliability: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class RuntimeAssuranceGraph:
    kernel: GraphKernel
    provider: RuntimeAssuranceProvider

    @staticmethod
    def definition() -> GraphDefinition:
        def service(actor_id: str) -> ActorRef:
            return ActorRef(actor_id, "service", authority="A1")

        def agent(actor_id: str) -> ActorRef:
            return ActorRef(actor_id, "agent", authority="A1")

        return GraphDefinition(
            graph_id="runtime-assurance",
            version="0.1.0",
            start_node="load_runtime_snapshot",
            nodes=(
                GraphNode("load_runtime_snapshot", service("runtime-assurance-context"), "runtime_assurance.load", "runtime_assurance.context"),
                GraphNode("analyse_reliability", agent("runtime-reliability-agent"), "runtime_assurance.reliability", "runtime_assurance.reliability"),
                GraphNode("analyse_controls", agent("runtime-control-agent"), "runtime_assurance.controls", "runtime_assurance.controls"),
                GraphNode("assure_runtime_analysis", service("runtime-assurance-policy"), "runtime_assurance.assure", "runtime_assurance.assurance"),
                GraphNode("finalize_runtime_assurance", service("runtime-assurance-record"), "runtime_assurance.finalize", "runtime_assurance.final"),
            ),
            edges=(
                GraphEdge("load_runtime_snapshot", "analyse_reliability"),
                GraphEdge("analyse_reliability", "analyse_controls"),
                GraphEdge("analyse_controls", "assure_runtime_analysis"),
                GraphEdge("assure_runtime_analysis", "finalize_runtime_assurance"),
            ),
        )

    def register(self) -> None:
        self.kernel.register_handler("runtime_assurance.load", self._load)
        self.kernel.register_handler("runtime_assurance.reliability", self._reliability)
        self.kernel.register_handler("runtime_assurance.controls", self._controls)
        self.kernel.register_handler("runtime_assurance.assure", self._assure)
        self.kernel.register_handler("runtime_assurance.finalize", self._finalize)
        self.kernel.register_evaluator("runtime_assurance.context", self._evaluate_context)
        self.kernel.register_evaluator(
            "runtime_assurance.reliability",
            lambda state, result: (
                result.patch.get("runtime_reliability", {}).get("status") in {"healthy", "watch", "degraded", "insufficient_telemetry"},
                "runtime reliability status required",
            ),
        )
        self.kernel.register_evaluator(
            "runtime_assurance.controls",
            lambda state, result: (
                result.patch.get("runtime_controls_analysis", {}).get("status") in {"pass", "watch", "intervention_recommended", "insufficient_telemetry"},
                "runtime control status required",
            ),
        )
        self.kernel.register_evaluator(
            "runtime_assurance.assurance",
            lambda state, result: (
                result.patch.get("runtime_assurance", {}).get("passed") is True,
                "runtime assurance boundary required",
            ),
        )
        self.kernel.register_evaluator(
            "runtime_assurance.final",
            lambda state, result: ("runtime_assurance_packet" in result.patch, "runtime assurance packet required"),
        )

    def start(self, *, execution_id: str, snapshot: dict[str, Any]):
        definition = self.definition()
        execution = self.kernel.start(
            definition,
            execution_id=execution_id,
            state={"runtime_assurance_snapshot": snapshot, "runtime_assurance_status": "started"},
        )
        return definition, self.kernel.run(definition, execution)

    @staticmethod
    def _load(state: dict[str, Any]) -> NodeResult:
        snapshot = state["runtime_assurance_snapshot"]
        return NodeResult(
            patch={"runtime_assurance_context": snapshot},
            evidence=[{"type": "aggregate_runtime_telemetry", "graph_count": len(snapshot.get("graphs", []))}],
        )

    def _reliability(self, state: dict[str, Any]) -> NodeResult:
        return NodeResult(
            patch={"runtime_reliability": self.provider.analyze_reliability(state["runtime_assurance_context"])}
        )

    def _controls(self, state: dict[str, Any]) -> NodeResult:
        return NodeResult(
            patch={
                "runtime_controls_analysis": self.provider.analyze_controls(
                    state["runtime_assurance_context"],
                    state["runtime_reliability"],
                )
            }
        )

    @staticmethod
    def _assure(state: dict[str, Any]) -> NodeResult:
        context = state["runtime_assurance_context"]
        boundary = context.get("model_boundary", {})
        passed = (
            boundary.get("contains_learner_identity") is False
            and boundary.get("contains_raw_graph_state") is False
            and boundary.get("contains_prompts_or_model_outputs") is False
            and boundary.get("contains_credentials") is False
        )
        return NodeResult(
            patch={
                "runtime_assurance": {
                    "passed": passed,
                    "agent_self_modification": False,
                    "runtime_policy_mutation": False,
                    "production_mutation": False,
                    "human_change_required_for_authority_or_disable_controls": True,
                }
            }
        )

    @staticmethod
    def _finalize(state: dict[str, Any]) -> NodeResult:
        controls = state["runtime_controls_analysis"]
        intervention = controls.get("status") == "intervention_recommended"
        return NodeResult(
            patch={
                "runtime_assurance_packet": {
                    "reliability": state["runtime_reliability"],
                    "controls": controls,
                    "assurance": state["runtime_assurance"],
                    "human_runtime_action_recommended": intervention,
                    "boundary": "assurance and recommendation only; no runtime mutation",
                },
                "runtime_assurance_status": "completed",
            }
        )

    @staticmethod
    def _evaluate_context(state: dict[str, Any], result: NodeResult) -> tuple[bool, str]:
        context = result.patch.get("runtime_assurance_context", {})
        boundary = context.get("model_boundary", {})
        required_false = (
            "contains_learner_identity",
            "contains_raw_graph_state",
            "contains_prompts_or_model_outputs",
            "contains_credentials",
        )
        if any(boundary.get(key) is not False for key in required_false):
            return False, "runtime assurance model context exceeded aggregate telemetry boundary"
        return True, "aggregate runtime assurance boundary satisfied"
