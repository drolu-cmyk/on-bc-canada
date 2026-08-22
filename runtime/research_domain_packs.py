"""Domain-specific research packs for the first three Canadian pathways.

A research pack narrows the shared Research Graph with source priorities,
evidence rules, capability focus, technology focus, and contradiction tests.
The graph kernel still owns sequencing and authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ResearchDomainPack:
    domain_id: str
    pathway_name: str
    research_goal: str
    source_priorities: tuple[str, ...]
    evidence_rules: tuple[str, ...]
    capability_focus: tuple[str, ...]
    technology_focus: tuple[str, ...]
    contradiction_tests: tuple[str, ...]
    geography: str = "Canada"

    def as_context(self) -> dict[str, object]:
        return {
            "domain_id": self.domain_id,
            "pathway_name": self.pathway_name,
            "research_goal": self.research_goal,
            "source_priorities": list(self.source_priorities),
            "evidence_rules": list(self.evidence_rules),
            "capability_focus": list(self.capability_focus),
            "technology_focus": list(self.technology_focus),
            "contradiction_tests": list(self.contradiction_tests),
            "geography": self.geography,
        }


APPLIED_AI_SYSTEMS = ResearchDomainPack(
    domain_id="applied-ai-systems",
    pathway_name="Applied AI Systems",
    research_goal=(
        "Identify the work Canadian employers expect practitioners to perform when "
        "building, evaluating, securing, deploying, and operating agentic AI systems."
    ),
    source_priorities=(
        "current Canadian employer job postings and role descriptions",
        "official vendor documentation for agent, model, tool, evaluation, and deployment capabilities",
        "Canadian government and public-sector AI guidance",
        "credible engineering documentation and production case studies",
        "current technical standards and security guidance",
    ),
    evidence_rules=(
        "Separate named technology requirements from durable work capabilities.",
        "Do not infer employer demand from vendor marketing alone.",
        "Prefer evidence that describes work performed, systems owned, or outcomes expected.",
        "Record seniority, geography, industry, and whether a requirement is essential or preferred when available.",
        "Treat a single employer cluster as local evidence, not broad Canadian demand.",
    ),
    capability_focus=(
        "model selection and structured model interaction",
        "tool and function integration",
        "agent loops and task decomposition",
        "graph engineering and conditional orchestration",
        "harness engineering, retries, checkpoints, and failure recovery",
        "memory and state design",
        "subagent delegation and context isolation",
        "MCP and external system integration",
        "agent identity, permissions, and human approval",
        "agent evaluation and trace-based quality assurance",
        "observability, cost, latency, and reliability",
        "cloud deployment and production operations",
        "AI application and agent security",
    ),
    technology_focus=(
        "OpenAI Agents SDK",
        "Responses API",
        "MCP",
        "agent evaluation frameworks",
        "workflow and graph runtimes",
        "vector and retrieval systems",
        "cloud AI services",
        "observability and tracing tools",
    ),
    contradiction_tests=(
        "Is the signal actually a software engineering requirement rather than an AI-specific capability?",
        "Is the named framework temporary while the underlying capability is durable?",
        "Is demand concentrated in senior roles rather than realistic entry or transition roles?",
        "Do employers ask for autonomous systems, or only conventional LLM application development?",
        "Is a capability appearing because of vendor terminology rather than work performed?",
    ),
)


CYBERSECURITY_GRC = ResearchDomainPack(
    domain_id="cybersecurity-grc",
    pathway_name="Cybersecurity GRC",
    research_goal=(
        "Identify the governance, risk, controls, evidence, assurance, and compliance work "
        "Canadian employers expect GRC practitioners to perform."
    ),
    source_priorities=(
        "current Canadian employer job postings and role descriptions",
        "Canadian Centre for Cyber Security guidance",
        "federal and provincial regulatory or oversight material",
        "recognized control, risk, and assurance standards",
        "credible audit, cloud security, and compliance implementation guidance",
    ),
    evidence_rules=(
        "Prioritize evidence of work products and decisions over certification names.",
        "Map frameworks to the capability required to apply them rather than teaching framework memorization.",
        "Distinguish security governance work from legal advice and licensed professional activity.",
        "Record sector-specific requirements when finance, health, government, or critical infrastructure materially changes the work.",
        "Separate control design, control operation, evidence collection, testing, and reporting as different capabilities.",
    ),
    capability_focus=(
        "risk identification and risk assessment",
        "control design and control mapping",
        "control evidence collection and validation",
        "control testing and assurance",
        "policy and standard development",
        "third-party and vendor risk",
        "identity and access governance",
        "cloud governance and security controls",
        "audit readiness and evidence management",
        "exceptions and risk acceptance",
        "incident governance and post-incident evidence",
        "GRC automation and continuous control monitoring",
        "executive and regulator-facing risk communication",
    ),
    technology_focus=(
        "GRC platforms",
        "cloud security posture tools",
        "identity governance systems",
        "security evidence automation",
        "continuous control monitoring",
        "ticketing and workflow systems",
        "SIEM and security telemetry used as control evidence",
    ),
    contradiction_tests=(
        "Is the requirement primarily audit, security engineering, privacy, or legal work rather than GRC?",
        "Is a certification listed as a proxy for experience rather than a capability to teach?",
        "Is the framework requirement sector-specific and therefore unsuitable as a universal pathway requirement?",
        "Does the role require years of organizational authority that an entry learner cannot realistically demonstrate?",
        "Is the employer asking for evidence production or merely familiarity with compliance terminology?",
    ),
)


AI_GOVERNANCE_ASSURANCE = ResearchDomainPack(
    domain_id="ai-governance-assurance",
    pathway_name="AI Governance & Assurance",
    research_goal=(
        "Identify the technical and organizational work Canadian employers need to govern, "
        "evaluate, authorize, monitor, and assure AI and autonomous systems."
    ),
    source_priorities=(
        "current Canadian employer job postings and role descriptions",
        "Government of Canada AI governance, privacy, security, and procurement guidance",
        "Canadian and international AI risk and assurance standards used by Canadian organizations",
        "model and agent evaluation documentation",
        "credible AI incident, assurance, and risk management practice",
    ),
    evidence_rules=(
        "Separate policy awareness from the ability to evaluate a real AI system.",
        "Require technical evidence when a capability claims to assess model, agent, tool, data, or permission behavior.",
        "Distinguish governance recommendations from legal conclusions.",
        "Record whether the work concerns predictive models, generative AI, autonomous agents, or all three.",
        "Prefer evidence that links governance decisions to measurable controls, evaluations, monitoring, or approval boundaries.",
    ),
    capability_focus=(
        "AI system inventory and use-case classification",
        "AI risk assessment and risk tiering",
        "data and model governance",
        "agent authority and permission review",
        "human oversight and escalation design",
        "model and agent evaluation",
        "AI security and misuse assessment",
        "third-party model and AI supplier assessment",
        "AI documentation and evidence requirements",
        "monitoring, incident response, and change governance",
        "assurance testing and control validation",
        "governance automation and evidence collection",
        "decision records for approval, restriction, or rejection of AI use",
    ),
    technology_focus=(
        "model evaluation platforms",
        "agent tracing and observability",
        "AI inventory and governance tooling",
        "policy-as-code and control automation",
        "model cards and system documentation",
        "red-team and adversarial evaluation tools",
        "identity and authorization systems for autonomous agents",
    ),
    contradiction_tests=(
        "Is the signal a policy or legal role with little responsibility for technical assurance?",
        "Does the requirement describe responsible-AI communication rather than operational governance work?",
        "Is a control borrowed from conventional GRC without evidence that AI changes the work?",
        "Is a named governance framework being requested while employers actually assess broader judgment and evidence skills?",
        "Does the role require authority to approve systems that should remain a human accountability boundary in training?",
    ),
)


DOMAIN_PACKS: Mapping[str, ResearchDomainPack] = {
    APPLIED_AI_SYSTEMS.domain_id: APPLIED_AI_SYSTEMS,
    CYBERSECURITY_GRC.domain_id: CYBERSECURITY_GRC,
    AI_GOVERNANCE_ASSURANCE.domain_id: AI_GOVERNANCE_ASSURANCE,
}


def get_domain_pack(domain_id: str) -> ResearchDomainPack:
    try:
        return DOMAIN_PACKS[domain_id]
    except KeyError as exc:
        supported = ", ".join(sorted(DOMAIN_PACKS))
        raise ValueError(f"unknown research domain {domain_id!r}; supported: {supported}") from exc
