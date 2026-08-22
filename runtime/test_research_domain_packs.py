from __future__ import annotations

import unittest
from types import SimpleNamespace

from runtime.openai_research_provider import (
    OpenAIResearchProvider,
    ResearchAgentSet,
    SourceCandidate,
    SourceDiscoveryOutput,
)
from runtime.research_domain_packs import (
    AI_GOVERNANCE_ASSURANCE,
    APPLIED_AI_SYSTEMS,
    CYBERSECURITY_GRC,
    DOMAIN_PACKS,
    get_domain_pack,
)


class FakeAgent:
    def __init__(self, name: str):
        self.name = name


class CapturingRunner:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def run_sync(self, agent, input, **kwargs):
        self.calls.append((agent.name, input, kwargs))
        return SimpleNamespace(final_output=self.output)


def fake_agents() -> ResearchAgentSet:
    return ResearchAgentSet(*[FakeAgent(name) for name in ("director", "evidence", "labour", "technology", "skills", "contradiction", "impact")])


class ResearchDomainPackTests(unittest.TestCase):
    def test_launch_has_exactly_three_research_domains(self):
        self.assertEqual(
            {"applied-ai-systems", "cybersecurity-grc", "ai-governance-assurance"},
            set(DOMAIN_PACKS),
        )

    def test_applied_ai_pack_contains_graph_and_harness_capabilities(self):
        focus = " ".join(APPLIED_AI_SYSTEMS.capability_focus).lower()
        self.assertIn("graph engineering", focus)
        self.assertIn("harness engineering", focus)
        self.assertIn("agent evaluation", focus)
        self.assertIn("agent identity", focus)

    def test_grc_pack_separates_control_work(self):
        focus = " ".join(CYBERSECURITY_GRC.capability_focus).lower()
        self.assertIn("control design", focus)
        self.assertIn("control evidence", focus)
        self.assertIn("control testing", focus)
        self.assertIn("third-party", focus)

    def test_ai_governance_pack_requires_technical_assurance(self):
        focus = " ".join(AI_GOVERNANCE_ASSURANCE.capability_focus).lower()
        self.assertIn("agent authority", focus)
        self.assertIn("model and agent evaluation", focus)
        self.assertIn("assurance testing", focus)
        self.assertIn("decision records", focus)

    def test_unknown_domain_fails_closed(self):
        with self.assertRaises(ValueError):
            get_domain_pack("cloud")

    def test_provider_embeds_domain_pack_in_every_agent_payload(self):
        output = SourceDiscoveryOutput(
            sources=[
                SourceCandidate(
                    source_id="s1",
                    publisher="Example Employer",
                    title="Applied AI role",
                    url="https://example.invalid/role",
                    rationale="fixture",
                )
            ]
        )
        runner = CapturingRunner(output)
        provider = OpenAIResearchProvider(
            agents=fake_agents(),
            runner=runner,
            domain_pack=APPLIED_AI_SYSTEMS,
        )
        research = provider.normalize("What work is changing?")
        provider.discover(research)

        self.assertEqual("applied-ai-systems", research["domain"]["domain_id"])
        self.assertEqual("Applied AI Systems", research["domain"]["pathway_name"])
        self.assertIn("graph engineering and conditional orchestration", research["domain"]["capability_focus"])
        self.assertIn('"domain_id": "applied-ai-systems"', runner.calls[0][1])
        self.assertIn('"pathway_name": "Applied AI Systems"', runner.calls[0][1])


if __name__ == "__main__":
    unittest.main()
