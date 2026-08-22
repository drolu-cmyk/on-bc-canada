"""OpenAI Agents SDK workers for the Canadian technical-work Research Graph.

The graph remains the workflow authority. This module supplies typed reasoning
workers for selected graph nodes. Agents may research and recommend. They do not
authorize curriculum changes or production side effects.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from runtime.research_domain_packs import ResearchDomainPack


class SourceCandidate(BaseModel):
    source_id: str
    publisher: str
    title: str
    url: str
    observed_date: str | None = None
    geography: str = "Canada"
    source_type: Literal["government", "employer", "labour_market", "industry", "academic", "other"] = "other"
    rationale: str


class SourceDiscoveryOutput(BaseModel):
    sources: list[SourceCandidate] = Field(min_length=1, max_length=24)
    search_notes: list[str] = Field(default_factory=list, max_length=8)


class EvidenceRecord(BaseModel):
    source_id: str
    publisher: str
    source_url: str
    claim: str
    geography: str = "Canada"
    observed_date: str | None = None
    fact_type: Literal[
        "job_requirement",
        "market_signal",
        "technology_signal",
        "policy_signal",
        "counterevidence",
        "other",
    ] = "other"
    limitations: list[str] = Field(default_factory=list, max_length=6)


class EvidenceOutput(BaseModel):
    evidence: list[EvidenceRecord] = Field(min_length=1, max_length=40)
    rejected_sources: list[str] = Field(default_factory=list, max_length=20)


class LabourMarketSignal(BaseModel):
    role: str
    capability_hint: str
    geography: str
    signal: Literal["emerging", "repeated", "established", "uncertain"]
    source_ids: list[str] = Field(min_length=1, max_length=12)
    note: str


class LabourMarketOutput(BaseModel):
    signals: list[LabourMarketSignal] = Field(default_factory=list, max_length=30)
    concentration_risks: list[str] = Field(default_factory=list, max_length=8)


class TechnologySignal(BaseModel):
    technology: str
    relationship: str
    maturity: Literal["emerging", "growing", "established", "uncertain"]
    source_ids: list[str] = Field(default_factory=list, max_length=12)
    note: str


class TechnologyOutput(BaseModel):
    signals: list[TechnologySignal] = Field(default_factory=list, max_length=30)
    substitution_notes: list[str] = Field(default_factory=list, max_length=8)


class CapabilityFinding(BaseModel):
    capability: str
    description: str
    evidence_source_ids: list[str] = Field(min_length=1, max_length=20)
    relevant_roles: list[str] = Field(default_factory=list, max_length=12)
    relevance: Literal["core", "important", "adjacent", "uncertain"]
    tool_neutral: bool = True


class SkillsOutput(BaseModel):
    capabilities: list[CapabilityFinding] = Field(default_factory=list, max_length=30)


class ContradictionOutput(BaseModel):
    status: Literal["challenged", "material_conflict", "insufficient_evidence"]
    contradictions: list[str] = Field(default_factory=list, max_length=10)
    limitations: list[str] = Field(default_factory=list, max_length=10)
    confidence_adjustment: float = Field(default=0.0, ge=-0.30, le=0.0)


class CurriculumImpactOutput(BaseModel):
    recommendation: Literal["increase", "add", "reduce", "retire", "no_change"]
    affected_capabilities: list[str] = Field(default_factory=list, max_length=20)
    reason: str
    requires_human_review: bool


class RunnerLike(Protocol):
    def run_sync(self, agent: Any, input: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class ResearchAgentSet:
    research_director: Any
    evidence_agent: Any
    labour_market_agent: Any
    technology_agent: Any
    skills_agent: Any
    contradiction_agent: Any
    curriculum_impact_agent: Any


def _json_input(task: str, payload: dict[str, Any]) -> str:
    return f"{task}\n\nINPUT_JSON\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def build_research_agents(model: str | None = None) -> ResearchAgentSet:
    """Build live SDK agents without performing an API call."""

    from agents import Agent, WebSearchTool

    model_name = model or os.getenv("SOZOROCK_RESEARCH_MODEL", "gpt-5.6-sol")
    domain_rule = (
        "When INPUT_JSON includes research.domain, treat its source priorities, evidence rules, capability focus, "
        "technology focus, and contradiction tests as binding research context. Do not widen the pathway merely to find more material. "
    )

    research_director = Agent(
        name="Canadian Technical Work Research Director",
        model=model_name,
        instructions=(
            domain_rule
            + "Find a compact, high-quality source set for a Canadian technical-work research question. "
            "Prefer official Canadian government and Job Bank material, direct employer postings, reputable labour-market sources, "
            "and primary technology documentation. Avoid listicles and copied job-board duplicates when a primary source exists. "
            "Do not treat one posting as market demand. Return only sources that were actually found."
        ),
        tools=[WebSearchTool(search_context_size="high", external_web_access=True)],
        output_type=SourceDiscoveryOutput,
    )

    evidence_agent = Agent(
        name="Evidence Agent",
        model=model_name,
        instructions=(
            domain_rule
            + "Verify the supplied source candidates and extract only claims relevant to the research question. "
            "Use web search to confirm source content and recency. Paraphrase evidence rather than reproducing long passages. "
            "Reject sources that cannot be verified or are materially stale for the question."
        ),
        tools=[WebSearchTool(search_context_size="high", external_web_access=True)],
        output_type=EvidenceOutput,
    )

    labour_market_agent = Agent(
        name="Canadian Labour Market Agent",
        model=model_name,
        instructions=(
            domain_rule
            + "Analyze the supplied evidence for repeated Canadian work requirements, role patterns, geography, and concentration risk. "
            "Do not convert frequency in a small sample into a national trend. Distinguish emerging, repeated, established, and uncertain signals."
        ),
        output_type=LabourMarketOutput,
    )

    technology_agent = Agent(
        name="Technology Signal Agent",
        model=model_name,
        instructions=(
            domain_rule
            + "Identify technologies that materially change the work being studied. Separate durable capabilities from replaceable products, "
            "frameworks, and model vendors. Use web search only to verify current technology status or documentation when needed."
        ),
        tools=[WebSearchTool(search_context_size="medium", external_web_access=True)],
        output_type=TechnologyOutput,
    )

    skills_agent = Agent(
        name="Capability Extraction Agent",
        model=model_name,
        instructions=(
            domain_rule
            + "Translate market and technology evidence into observable, tool-neutral capabilities. A capability must describe work a person can "
            "demonstrate, not a course topic or product name. Preserve source IDs so every capability remains traceable."
        ),
        output_type=SkillsOutput,
    )

    contradiction_agent = Agent(
        name="Contradiction Agent",
        model=model_name,
        instructions=(
            domain_rule
            + "Try to disprove or narrow the emerging conclusion. Search for counterevidence, regional differences, obsolete requirements, "
            "vendor-specific noise, weak samples, and evidence that the supposed trend is not durable. Execute the domain contradiction tests "
            "explicitly. Never increase confidence."
        ),
        tools=[WebSearchTool(search_context_size="medium", external_web_access=True)],
        output_type=ContradictionOutput,
    )

    curriculum_impact_agent = Agent(
        name="Curriculum Impact Agent",
        model=model_name,
        instructions=(
            domain_rule
            + "Compare validated capabilities with the supplied pathway context. Recommend no change unless the evidence supports a material gap. "
            "Any add, increase, reduce, or retire recommendation requires human review. You may recommend; you may not authorize or publish a change."
        ),
        output_type=CurriculumImpactOutput,
    )

    return ResearchAgentSet(
        research_director=research_director,
        evidence_agent=evidence_agent,
        labour_market_agent=labour_market_agent,
        technology_agent=technology_agent,
        skills_agent=skills_agent,
        contradiction_agent=contradiction_agent,
        curriculum_impact_agent=curriculum_impact_agent,
    )


class OpenAIResearchProvider:
    """ResearchProvider implementation backed by typed Agents SDK workers."""

    def __init__(
        self,
        agents: ResearchAgentSet | None = None,
        runner: RunnerLike | None = None,
        *,
        max_turns: int = 8,
        domain_pack: ResearchDomainPack | None = None,
    ) -> None:
        if agents is None:
            agents = build_research_agents()
        if runner is None:
            from agents import Runner

            runner = Runner
        self.agents = agents
        self.runner = runner
        self.max_turns = max_turns
        self.domain_pack = domain_pack

    def normalize(self, question: str) -> dict[str, Any]:
        normalized = " ".join(question.split())
        if not normalized:
            raise ValueError("research question is required")
        research: dict[str, Any] = {
            "question": normalized,
            "geography": "Canada",
            "scope": "technical work",
            "evidence_standard": "current, attributable, traceable",
        }
        if self.domain_pack is not None:
            research["domain"] = self.domain_pack.as_context()
            research["scope"] = self.domain_pack.research_goal
        return research

    def _run(self, agent: Any, task: str, payload: dict[str, Any]) -> BaseModel:
        result = self.runner.run_sync(
            agent,
            _json_input(task, payload),
            max_turns=self.max_turns,
        )
        output = result.final_output
        if not isinstance(output, BaseModel):
            raise TypeError(f"agent {getattr(agent, 'name', 'unknown')} returned untyped output")
        return output

    def discover(self, research: dict[str, Any]) -> list[dict[str, Any]]:
        output = self._run(
            self.agents.research_director,
            "Build the source set for this Canadian technical-work research question using the domain pack when supplied.",
            {"research": research},
        )
        assert isinstance(output, SourceDiscoveryOutput)
        return [item.model_dump() for item in output.sources]

    def collect(self, research: dict[str, Any], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output = self._run(
            self.agents.evidence_agent,
            "Verify these sources and extract relevant evidence under the domain-specific evidence rules.",
            {"research": research, "sources": sources},
        )
        assert isinstance(output, EvidenceOutput)
        return [item.model_dump() for item in output.evidence]

    def analyze_labour_market(self, research: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
        output = self._run(
            self.agents.labour_market_agent,
            "Identify labour-market signals without overstating the sample or crossing the domain boundary.",
            {"research": research, "evidence": evidence},
        )
        assert isinstance(output, LabourMarketOutput)
        return output.model_dump()

    def analyze_technology(self, research: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
        output = self._run(
            self.agents.technology_agent,
            "Separate durable technical capabilities from replaceable technologies and identify material technology shifts for this domain.",
            {"research": research, "evidence": evidence},
        )
        assert isinstance(output, TechnologyOutput)
        return output.model_dump()

    def extract_capabilities(
        self,
        research: dict[str, Any],
        evidence: list[dict[str, Any]],
        labour_market: dict[str, Any],
        technology: dict[str, Any],
    ) -> list[dict[str, Any]]:
        output = self._run(
            self.agents.skills_agent,
            "Extract observable, tool-neutral capabilities from the validated evidence and analyses, using the domain capability focus as a boundary rather than a quota.",
            {
                "research": research,
                "evidence": evidence,
                "labour_market": labour_market,
                "technology": technology,
            },
        )
        assert isinstance(output, SkillsOutput)
        return [item.model_dump() for item in output.capabilities]

    def challenge(
        self,
        research: dict[str, Any],
        capabilities: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        output = self._run(
            self.agents.contradiction_agent,
            "Challenge the current conclusion, execute the domain contradiction tests, and look for evidence that should reduce confidence or narrow scope.",
            {"research": research, "capabilities": capabilities, "evidence": evidence},
        )
        assert isinstance(output, ContradictionOutput)
        return output.model_dump()

    @staticmethod
    def score(
        research: dict[str, Any],
        evidence: list[dict[str, Any]],
        challenge: dict[str, Any],
    ) -> dict[str, Any]:
        del research
        publishers = {item.get("publisher") for item in evidence if item.get("publisher")}
        base = 0.40
        base += min(len(evidence), 20) * 0.015
        base += min(len(publishers), 8) * 0.035
        adjustment = float(challenge.get("confidence_adjustment", 0.0))
        confidence = round(max(0.0, min(0.95, base + adjustment)), 2)
        return {
            "confidence": confidence,
            "source_diversity": len(publishers),
            "evidence_count": len(evidence),
            "method": "deterministic-v1",
        }

    def assess_curriculum_impact(
        self,
        research: dict[str, Any],
        capabilities: list[dict[str, Any]],
        score: dict[str, Any],
    ) -> dict[str, Any]:
        output = self._run(
            self.agents.curriculum_impact_agent,
            "Assess whether the evidence warrants a pathway review inside the named domain. The graph, not the agent, owns the approval decision.",
            {"research": research, "capabilities": capabilities, "evidence_score": score},
        )
        assert isinstance(output, CurriculumImpactOutput)
        payload = output.model_dump()
        if payload["recommendation"] != "no_change":
            payload["requires_human_review"] = True
        return payload
