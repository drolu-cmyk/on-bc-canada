"""First research graph for Canadian technical-work evidence.

The runtime is provider-neutral. Discovery, extraction, challenge, and scoring
handlers are injected so OpenAI agents, deterministic services, or future
providers can occupy the same graph without changing its authority model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from runtime.graph_kernel import ActorRef, GraphDefinition, GraphEdge, GraphKernel, GraphNode, NodeResult


class ResearchProvider(Protocol):
    def normalize(self, question: str) -> dict[str, Any]: ...
    def discover(self, research: dict[str, Any]) -> list[dict[str, Any]]: ...
    def collect(self, research: dict[str, Any], sources: list[dict[str, Any]]) -> list[dict[str, Any]]: ...
    def extract_capabilities(self, research: dict[str, Any], evidence: list[dict[str, Any]]) -> list[dict[str, Any]]: ...
    def challenge(
        self,
        research: dict[str, Any],
        capabilities: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]: ...
    def score(
        self,
        research: dict[str, Any],
        evidence: list[dict[str, Any]],
        challenge: dict[str, Any],
    ) -> dict[str, Any]: ...
    def assess_curriculum_impact(
        self,
        research: dict[str, Any],
        capabilities: list[dict[str, Any]],
        score: dict[str, Any],
    ) -> dict[str, Any]: ...


@dataclass
class ResearchGraph:
    kernel: GraphKernel
    provider: ResearchProvider

    @staticmethod
    def definition() -> GraphDefinition:
        def service(actor_id: str) -> ActorRef:
            return ActorRef(actor_id=actor_id, kind="service", authority="A1")

        def agent(actor_id: str) -> ActorRef:
            return ActorRef(actor_id=actor_id, kind="agent", authority="A1")

        return GraphDefinition(
            graph_id="canadian-work-research",
            version="0.1.0",
            start_node="normalize_question",
            nodes=(
                GraphNode("normalize_question", service("research-contract"), "research.normalize", "research.normalized"),
                GraphNode("discover_sources", agent("research-discovery-agent"), "research.discover", "research.sources"),
                GraphNode("collect_evidence", agent("evidence-agent"), "research.collect", "research.evidence"),
                GraphNode("extract_capabilities", agent("skills-agent"), "research.extract_capabilities", "research.capabilities"),
                GraphNode("challenge_conclusion", agent("contradiction-agent"), "research.challenge", "research.challenge"),
                GraphNode("score_evidence", service("evidence-scoring"), "research.score", "research.score"),
                GraphNode("assess_curriculum_impact", agent("curriculum-impact-agent"), "research.impact", "research.impact"),
                GraphNode(
                    "curriculum_review",
                    ActorRef("program-accountable-human", "human", authority="A3"),
                    approval_reason="Research suggests a pathway change. Human curriculum authorization is required.",
                ),
                GraphNode("finalize_finding", service("research-record"), "research.finalize", "research.final"),
            ),
            edges=(
                GraphEdge("normalize_question", "discover_sources"),
                GraphEdge("discover_sources", "collect_evidence"),
                GraphEdge("collect_evidence", "extract_capabilities"),
                GraphEdge("extract_capabilities", "challenge_conclusion"),
                GraphEdge("challenge_conclusion", "score_evidence"),
                GraphEdge("score_evidence", "assess_curriculum_impact"),
                GraphEdge("assess_curriculum_impact", "curriculum_review", route="review"),
                GraphEdge("assess_curriculum_impact", "finalize_finding", route="no_change"),
                GraphEdge("curriculum_review", "finalize_finding", route="approved"),
            ),
        )

    def register(self) -> None:
        self.kernel.register_handler("research.normalize", self._normalize)
        self.kernel.register_handler("research.discover", self._discover)
        self.kernel.register_handler("research.collect", self._collect)
        self.kernel.register_handler("research.extract_capabilities", self._extract)
        self.kernel.register_handler("research.challenge", self._challenge)
        self.kernel.register_handler("research.score", self._score)
        self.kernel.register_handler("research.impact", self._impact)
        self.kernel.register_handler("research.finalize", self._finalize)
        self.kernel.register_evaluator(
            "research.normalized",
            lambda state, result: (bool(result.patch.get("research", {}).get("question")), "question normalized"),
        )
        self.kernel.register_evaluator(
            "research.sources",
            lambda state, result: (len(result.patch.get("sources", [])) > 0, "at least one source required"),
        )
        self.kernel.register_evaluator(
            "research.evidence",
            lambda state, result: (len(result.patch.get("evidence", [])) > 0, "evidence required"),
        )
        self.kernel.register_evaluator(
            "research.capabilities",
            lambda state, result: (isinstance(result.patch.get("capabilities"), list), "capability output required"),
        )
        self.kernel.register_evaluator(
            "research.challenge",
            lambda state, result: ("challenge" in result.patch, "contradiction review required"),
        )
        self.kernel.register_evaluator(
            "research.score",
            lambda state, result: (
                0 <= result.patch.get("evidence_score", {}).get("confidence", -1) <= 1,
                "confidence must be between 0 and 1",
            ),
        )
        self.kernel.register_evaluator(
            "research.impact",
            lambda state, result: (result.route in {"review", "no_change"}, "impact route required"),
        )
        self.kernel.register_evaluator(
            "research.final",
            lambda state, result: ("finding" in result.patch, "finding required"),
        )

    def start(self, *, execution_id: str, question: str, geography: str = "Canada"):
        definition = self.definition()
        execution = self.kernel.start(
            definition,
            execution_id=execution_id,
            state={"question": question, "geography": geography, "research_status": "started"},
        )
        return definition, self.kernel.run(definition, execution)

    def _normalize(self, state: dict[str, Any]) -> NodeResult:
        research = self.provider.normalize(state["question"])
        research.setdefault("geography", state.get("geography", "Canada"))
        return NodeResult(
            patch={"research": research},
            evidence=[{"type": "research_contract", "question": research.get("question")}],
        )

    def _discover(self, state: dict[str, Any]) -> NodeResult:
        sources = self.provider.discover(state["research"])
        return NodeResult(
            patch={"sources": sources},
            evidence=[{"type": "source_index", "count": len(sources)}],
        )

    def _collect(self, state: dict[str, Any]) -> NodeResult:
        evidence = self.provider.collect(state["research"], state["sources"])
        return NodeResult(
            patch={"evidence": evidence},
            evidence=[{"type": "evidence_set", "count": len(evidence)}],
        )

    def _extract(self, state: dict[str, Any]) -> NodeResult:
        capabilities = self.provider.extract_capabilities(state["research"], state["evidence"])
        return NodeResult(
            patch={"capabilities": capabilities},
            evidence=[{"type": "capability_extraction", "count": len(capabilities)}],
        )

    def _challenge(self, state: dict[str, Any]) -> NodeResult:
        challenge = self.provider.challenge(state["research"], state["capabilities"], state["evidence"])
        return NodeResult(
            patch={"challenge": challenge},
            evidence=[{"type": "contradiction_review", "status": challenge.get("status", "unknown")}],
        )

    def _score(self, state: dict[str, Any]) -> NodeResult:
        score = self.provider.score(state["research"], state["evidence"], state["challenge"])
        return NodeResult(
            patch={"evidence_score": score},
            evidence=[{"type": "evidence_score", "confidence": score.get("confidence")}],
        )

    def _impact(self, state: dict[str, Any]) -> NodeResult:
        impact = self.provider.assess_curriculum_impact(
            state["research"],
            state["capabilities"],
            state["evidence_score"],
        )
        requires_review = bool(impact.get("requires_human_review"))
        return NodeResult(
            patch={"curriculum_impact": impact},
            evidence=[{"type": "curriculum_impact", "recommendation": impact.get("recommendation")}],
            route="review" if requires_review else "no_change",
        )

    @staticmethod
    def _finalize(state: dict[str, Any]) -> NodeResult:
        finding = {
            "question": state["research"]["question"],
            "geography": state["research"].get("geography", "Canada"),
            "capabilities": state["capabilities"],
            "confidence": state["evidence_score"]["confidence"],
            "contradiction_status": state["challenge"].get("status"),
            "curriculum_impact": state["curriculum_impact"],
            "source_count": len(state["sources"]),
            "evidence_count": len(state["evidence"]),
        }
        return NodeResult(
            patch={"finding": finding, "research_status": "complete"},
            evidence=[{"type": "validated_finding"}],
        )
