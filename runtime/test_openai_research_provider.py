from __future__ import annotations

import importlib.util
import unittest
from types import SimpleNamespace

from runtime.openai_research_provider import (
    CapabilityFinding,
    ContradictionOutput,
    CurriculumImpactOutput,
    EvidenceOutput,
    EvidenceRecord,
    LabourMarketOutput,
    LabourMarketSignal,
    OpenAIResearchProvider,
    ResearchAgentSet,
    SkillsOutput,
    SourceCandidate,
    SourceDiscoveryOutput,
    TechnologyOutput,
    TechnologySignal,
    build_research_agents,
)


class FakeAgent:
    def __init__(self, name: str):
        self.name = name


class FakeRunner:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def run_sync(self, agent, input, **kwargs):
        self.calls.append((agent.name, input, kwargs))
        return SimpleNamespace(final_output=self.outputs.pop(0))


class OpenAIResearchProviderTests(unittest.TestCase):
    def setUp(self):
        self.agents = ResearchAgentSet(
            *[
                FakeAgent(name)
                for name in (
                    "director",
                    "evidence",
                    "labour",
                    "technology",
                    "skills",
                    "contradiction",
                    "impact",
                )
            ]
        )

    def test_typed_workers_feed_provider_contract(self):
        outputs = [
            SourceDiscoveryOutput(
                sources=[
                    SourceCandidate(
                        source_id="s1",
                        publisher="Canada Job Bank",
                        title="AI role",
                        url="https://example.invalid/1",
                        rationale="primary labour source",
                    )
                ]
            ),
            EvidenceOutput(
                evidence=[
                    EvidenceRecord(
                        source_id="s1",
                        publisher="Canada Job Bank",
                        source_url="https://example.invalid/1",
                        claim="Role requires agent evaluation",
                        fact_type="job_requirement",
                    )
                ]
            ),
            LabourMarketOutput(
                signals=[
                    LabourMarketSignal(
                        role="Applied AI Developer",
                        capability_hint="agent evaluation",
                        geography="Canada",
                        signal="repeated",
                        source_ids=["s1"],
                        note="fixture",
                    )
                ]
            ),
            TechnologyOutput(
                signals=[
                    TechnologySignal(
                        technology="agent evaluation harness",
                        relationship="supports reliable autonomous workflows",
                        maturity="growing",
                        source_ids=["s1"],
                        note="fixture",
                    )
                ]
            ),
            SkillsOutput(
                capabilities=[
                    CapabilityFinding(
                        capability="agent evaluation",
                        description="Evaluate an agent against defined tasks and failure conditions",
                        evidence_source_ids=["s1"],
                        relevant_roles=["Applied AI Developer"],
                        relevance="core",
                    )
                ]
            ),
            ContradictionOutput(
                status="challenged",
                limitations=["small fixture"],
                confidence_adjustment=-0.05,
            ),
            CurriculumImpactOutput(
                recommendation="increase",
                affected_capabilities=["agent evaluation"],
                reason="material requirement",
                requires_human_review=False,
            ),
        ]
        runner = FakeRunner(outputs)
        provider = OpenAIResearchProvider(agents=self.agents, runner=runner)
        research = provider.normalize("  What   work is changing? ")
        sources = provider.discover(research)
        evidence = provider.collect(research, sources)
        labour = provider.analyze_labour_market(research, evidence)
        technology = provider.analyze_technology(research, evidence)
        capabilities = provider.extract_capabilities(research, evidence, labour, technology)
        challenge = provider.challenge(research, capabilities, evidence)
        score = provider.score(research, evidence, challenge)
        impact = provider.assess_curriculum_impact(research, capabilities, score)

        self.assertEqual("What work is changing?", research["question"])
        self.assertEqual("s1", sources[0]["source_id"])
        self.assertEqual("repeated", labour["signals"][0]["signal"])
        self.assertEqual("agent evaluation", capabilities[0]["capability"])
        self.assertLess(score["confidence"], 0.50)
        self.assertTrue(impact["requires_human_review"])
        self.assertEqual(7, len(runner.calls))
        self.assertTrue(all(call[2]["max_turns"] == 8 for call in runner.calls))

    @unittest.skipUnless(importlib.util.find_spec("agents"), "openai-agents not installed")
    def test_live_sdk_agent_contracts_construct_without_api_call(self):
        agents = build_research_agents(model="gpt-5.6-sol")
        self.assertEqual("Canadian Technical Work Research Director", agents.research_director.name)
        self.assertEqual("Evidence Agent", agents.evidence_agent.name)
        self.assertEqual("Curriculum Impact Agent", agents.curriculum_impact_agent.name)
        self.assertTrue(agents.research_director.tools)
        self.assertTrue(agents.contradiction_agent.tools)

    def test_non_typed_output_fails_closed(self):
        runner = FakeRunner(["free-form text"])
        provider = OpenAIResearchProvider(agents=self.agents, runner=runner)
        with self.assertRaises(TypeError):
            provider.discover(provider.normalize("test"))


if __name__ == "__main__":
    unittest.main()
