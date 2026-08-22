"""Outcomes Intelligence graph over privacy-released aggregate learner metrics.

The graph interprets programme outcomes and can prepare a research signal. It does
not rank learners, change learner records, change curriculum, or write Work
Intelligence directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from runtime.graph_kernel import ActorRef, GraphDefinition, GraphEdge, GraphKernel, GraphNode, NodeResult


_FORBIDDEN_KEYS = {
    "learner_ref",
    "learner_id",
    "instance_id",
    "cohort_id",
    "submission_id",
    "artifact_ref",
    "artifact_refs",
    "accepted_by",
    "email",
    "name",
}


class OutcomesIntelligenceProvider(Protocol):
    def analyze_outcomes(self, snapshot: dict[str, Any]) -> dict[str, Any]: ...
    def challenge_outcomes(self, snapshot: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class OutcomesIntelligenceGraph:
    kernel: GraphKernel
    provider: OutcomesIntelligenceProvider

    @staticmethod
    def definition() -> GraphDefinition:
        def service(actor_id: str) -> ActorRef:
            return ActorRef(actor_id, "service", authority="A1")

        def agent(actor_id: str) -> ActorRef:
            return ActorRef(actor_id, "agent", authority="A1")

        return GraphDefinition(
            graph_id="outcomes-intelligence",
            version="0.1.0",
            start_node="load_aggregate_snapshot",
            nodes=(
                GraphNode("load_aggregate_snapshot", service("outcomes-context-service"), "outcomes.load", "outcomes.privacy"),
                GraphNode("analyse_outcomes", agent("outcomes-analysis-agent"), "outcomes.analyse", "outcomes.analysis"),
                GraphNode("challenge_outcomes", agent("outcomes-challenge-agent"), "outcomes.challenge", "outcomes.challenge"),
                GraphNode("route_signal", service("outcomes-signal-policy"), "outcomes.route"),
                GraphNode("prepare_research_signal", service("outcomes-research-signal-service"), "outcomes.prepare_signal", "outcomes.signal"),
                GraphNode("assure_outcomes", service("outcomes-assurance"), "outcomes.assure", "outcomes.assurance"),
                GraphNode("finalize_outcomes", service("outcomes-record"), "outcomes.finalize", "outcomes.final"),
            ),
            edges=(
                GraphEdge("load_aggregate_snapshot", "analyse_outcomes"),
                GraphEdge("analyse_outcomes", "challenge_outcomes"),
                GraphEdge("challenge_outcomes", "route_signal"),
                GraphEdge("route_signal", "prepare_research_signal", route="research_signal"),
                GraphEdge("route_signal", "assure_outcomes", route="no_signal"),
                GraphEdge("prepare_research_signal", "assure_outcomes"),
                GraphEdge("assure_outcomes", "finalize_outcomes"),
            ),
        )

    def register(self) -> None:
        self.kernel.register_handler("outcomes.load", self._load)
        self.kernel.register_handler("outcomes.analyse", self._analyse)
        self.kernel.register_handler("outcomes.challenge", self._challenge)
        self.kernel.register_handler("outcomes.route", self._route)
        self.kernel.register_handler("outcomes.prepare_signal", self._prepare_signal)
        self.kernel.register_handler("outcomes.assure", self._assure)
        self.kernel.register_handler("outcomes.finalize", self._finalize)
        self.kernel.register_evaluator("outcomes.privacy", self._evaluate_privacy)
        self.kernel.register_evaluator(
            "outcomes.analysis",
            lambda state, result: (
                result.patch.get("outcomes_analysis", {}).get("status")
                in {"material_signal", "no_material_signal", "insufficient_evidence"},
                "typed outcomes analysis status required",
            ),
        )
        self.kernel.register_evaluator(
            "outcomes.challenge",
            lambda state, result: (
                result.patch.get("outcomes_challenge", {}).get("status")
                in {"supports", "narrows", "rejects", "insufficient"},
                "typed outcomes challenge status required",
            ),
        )
        self.kernel.register_evaluator(
            "outcomes.signal",
            lambda state, result: (
                bool(result.patch.get("research_signal", {}).get("questions")),
                "research signal requires at least one question",
            ),
        )
        self.kernel.register_evaluator(
            "outcomes.assurance",
            lambda state, result: (
                result.patch.get("outcomes_assurance", {}).get("passed") is True,
                "outcomes assurance required",
            ),
        )
        self.kernel.register_evaluator(
            "outcomes.final",
            lambda state, result: ("outcomes_packet" in result.patch, "outcomes packet required"),
        )

    def start(self, *, execution_id: str, snapshot: dict[str, Any]):
        definition = self.definition()
        execution = self.kernel.start(
            definition,
            execution_id=execution_id,
            state={"aggregate_outcomes_snapshot": snapshot, "outcomes_status": "started"},
        )
        return definition, self.kernel.run(definition, execution)

    @staticmethod
    def _contains_forbidden(value: Any) -> bool:
        if isinstance(value, dict):
            for key, item in value.items():
                lowered = str(key).casefold()
                if lowered in _FORBIDDEN_KEYS or lowered.startswith("learner_") and lowered not in {
                    "learner_count",
                    "learners_with_accepted_capability_evidence",
                }:
                    return True
                if OutcomesIntelligenceGraph._contains_forbidden(item):
                    return True
        elif isinstance(value, list):
            return any(OutcomesIntelligenceGraph._contains_forbidden(item) for item in value)
        return False

    def _load(self, state: dict[str, Any]) -> NodeResult:
        snapshot = state["aggregate_outcomes_snapshot"]
        return NodeResult(
            patch={"outcomes_context": snapshot},
            evidence=[{"type": "aggregate_outcomes", "released_group_count": len(snapshot.get("groups", []))}],
        )

    def _analyse(self, state: dict[str, Any]) -> NodeResult:
        output = self.provider.analyze_outcomes(state["outcomes_context"])
        return NodeResult(patch={"outcomes_analysis": output})

    def _challenge(self, state: dict[str, Any]) -> NodeResult:
        output = self.provider.challenge_outcomes(state["outcomes_context"], state["outcomes_analysis"])
        return NodeResult(patch={"outcomes_challenge": output})

    @staticmethod
    def _route(state: dict[str, Any]) -> NodeResult:
        analysis = state["outcomes_analysis"]
        challenge = state["outcomes_challenge"]
        route = "research_signal" if analysis.get("status") == "material_signal" and challenge.get("status") in {"supports", "narrows"} else "no_signal"
        return NodeResult(route=route, patch={"outcomes_route": route})

    @staticmethod
    def _prepare_signal(state: dict[str, Any]) -> NodeResult:
        analysis = state["outcomes_analysis"]
        challenge = state["outcomes_challenge"]
        questions = []
        for finding in analysis.get("findings", []):
            question = str(finding.get("research_question", "")).strip()
            if question:
                questions.append(question)
        for question in challenge.get("surviving_questions", []):
            if question and question not in questions:
                questions.append(question)
        return NodeResult(
            patch={
                "research_signal": {
                    "source": "outcomes-intelligence",
                    "questions": questions,
                    "data_classes": ["aggregate_outcomes", "outcome_signal"],
                    "requires_independent_research_validation": True,
                }
            }
        )

    @staticmethod
    def _assure(state: dict[str, Any]) -> NodeResult:
        context = state["outcomes_context"]
        passed = (
            context.get("model_boundary", {}).get("contains_direct_learner_identity") is False
            and context.get("model_boundary", {}).get("contains_cohort_id") is False
            and context.get("model_boundary", {}).get("contains_submission_or_artifact_reference") is False
            and not OutcomesIntelligenceGraph._contains_forbidden(context)
        )
        return NodeResult(
            patch={
                "outcomes_assurance": {
                    "passed": passed,
                    "privacy_aggregation": context.get("aggregation"),
                    "direct_curriculum_write": False,
                    "learner_level_decision": False,
                }
            }
        )

    @staticmethod
    def _finalize(state: dict[str, Any]) -> NodeResult:
        return NodeResult(
            patch={
                "outcomes_packet": {
                    "analysis": state["outcomes_analysis"],
                    "challenge": state["outcomes_challenge"],
                    "research_signal": state.get("research_signal"),
                    "assurance": state["outcomes_assurance"],
                    "boundary": "aggregate programme intelligence only",
                },
                "outcomes_status": "completed",
            }
        )

    @staticmethod
    def _evaluate_privacy(state: dict[str, Any], result: NodeResult) -> tuple[bool, str]:
        context = result.patch.get("outcomes_context", {})
        boundary = context.get("model_boundary", {})
        if OutcomesIntelligenceGraph._contains_forbidden(context):
            return False, "aggregate outcome context contains a prohibited learner-level field"
        if boundary.get("contains_direct_learner_identity") is not False:
            return False, "direct learner identity must be absent"
        if boundary.get("contains_cohort_id") is not False:
            return False, "cohort IDs are not released to Outcomes Intelligence agents"
        return True, "aggregate outcome privacy boundary satisfied"
