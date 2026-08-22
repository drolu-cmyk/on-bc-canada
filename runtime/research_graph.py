"""Research graph for Canadian technical-work evidence.

The graph owns sequencing and authority. Specialist providers occupy selected
nodes, but no model worker can bypass the graph's evaluation or human-review
boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from runtime.graph_kernel import ActorRef, GraphDefinition, GraphEdge, GraphKernel, GraphNode, NodeResult


class ResearchProvider(Protocol):
    def normalize(self, question: str) -> dict[str, Any]: ...
    def discover(self, research: dict[str, Any]) -> list[dict[str, Any]]: ...
    def collect(self, research: dict[str, Any], sources: list[dict[str, Any]]) -> list[dict[str, Any]]: ...
    def analyze_labour_market(self, research: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]: ...
    def analyze_technology(self, research: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]: ...
    def extract_capabilities(
        self,
        research: dict[str, Any],
        evidence: list[dict[str, Any]],
        labour_market: dict[str, Any],
        technology: dict[str, Any],
    ) -> list[dict[str, Any]]: ...
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
            version="0.2.0",
            start_node="normalize_question",
            nodes=(
                GraphNode("normalize_question", service("research-contract"), "research.normalize", "research.normalized"),
                GraphNode("discover_sources", agent("research-director-agent"), "research.discover", "research.sources"),
                GraphNode("collect_evidence", agent("evidence-agent"), "research.collect", "research.evidence"),
                GraphNode(
                    "analyse_labour_market",
                    agent("labour-market-agent"),
                    "research.labour_market",
                    "research.labour_market",
                ),
                GraphNode(
                    "analyse_technology",
                    agent("technology-agent"),
                    "research.technology",
                    "research.technology",
                ),
                GraphNode(
                    "extract_capabilities",
                    agent("skills-agent"),
                    "research.extract_capabilities",
                    "research.capabilities",
                ),
                GraphNode("challenge_conclusion", agent("contradiction-agent"), "research.challenge", "research.challenge"),
                GraphNode("score_evidence", service("evidence-scoring"), "research.score", "research.score"),
                GraphNode(
                    "assess_curriculum_impact",
                    agent("curriculum-impact-agent"),
                    "research.impact",
                    "research.impact",
                ),
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
                GraphEdge("collect_evidence", "analyse_labour_market"),
                GraphEdge("analyse_labour_market", "analyse_technology"),
                GraphEdge("analyse_technology", "extract_capabilities"),
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
        self.kernel.register_handler("research.labour_market", self._labour_market)
        self.kernel.register_handler("research.technology", self._technology)
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
            "research.labour_market",
            lambda state, result: ("labour_market" in result.patch, "labour-market analysis required"),
        )
        self.kernel.register_evaluator(
            "research.technology",
            lambda state, result: ("technology" in result.patch, "technology analysis required"),
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

    def _labour_market(self, state: dict[str, Any]) -> NodeResult:
        analysis = self.provider.analyze_labour_market(state["research"], state["evidence"])
        return NodeResult(
            patch={"labour_market": analysis},
            evidence=[{"type": "labour_market_analysis"}],
        )

    def _technology(self, state: dict[str, Any]) -> NodeResult:
        analysis = self.provider.analyze_technology(state["research"], state["evidence"])
        return NodeResult(
            patch={"technology": analysis},
            evidence=[{"type": "technology_analysis"}],
        )

    def _extract(self, state: dict[str, Any]) -> NodeResult:
        capabilities = self.provider.extract_capabilities(
            state["research"],
            state["evidence"],
            state["labour_market"],
            state["technology"],
        )
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
        domain = state["research"].get("domain") or {}
        finding = {
            "question": state["research"]["question"],
            "geography": state["research"].get("geography", "Canada"),
            "domain_id": domain.get("domain_id"),
            "pathway_name": domain.get("pathway_name"),
            "labour_market": state["labour_market"],
            "technology": state["technology"],
            "capabilities": state["capabilities"],
            "confidence": state["evidence_score"]["confidence"],
            "contradiction_status": state["challenge"].get("status"),
            "curriculum_impact": state["curriculum_impact"],
            "source_count": len(state["sources"]),
            "evidence_count": len(state["evidence"]),
        }
        return NodeResult(
            patch={"finding": finding, "research_status": "complete"},
            evidence=[{"type": "validated_finding", "domain_id": domain.get("domain_id")}],
        )
