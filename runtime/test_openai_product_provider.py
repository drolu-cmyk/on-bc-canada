from __future__ import annotations

import unittest
from types import SimpleNamespace

from runtime.openai_product_provider import (
    OpenAIProductDevelopmentProvider,
    ProductAgentSet,
    ReviewOutput,
    build_product_agents,
)


class FakeAgent:
    def __init__(self, name: str):
        self.name = name


class FakeRunner:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def run_sync(self, agent, input, **kwargs):
        self.calls.append((agent.name, input, kwargs))
        return SimpleNamespace(final_output=self.output)


def fake_agents() -> ProductAgentSet:
    return ProductAgentSet(*[FakeAgent(name) for name in (
        "product",
        "experience",
        "interface",
        "copy",
        "brand",
        "engineering",
        "cloud",
        "security",
        "accessibility",
        "quality",
    )])


class OpenAIProductProviderTests(unittest.TestCase):
    def test_normalize_requires_problem_and_sets_canadian_boundary(self):
        provider = OpenAIProductDevelopmentProvider(agents=fake_agents(), runner=FakeRunner(None))
        normalized = provider.normalize({"problem": "  Improve learner home  "})
        self.assertEqual("Improve learner home", normalized["problem"])
        self.assertEqual("Canada", normalized["market"])
        self.assertEqual("human", normalized["release_authority"])
        with self.assertRaisesRegex(ValueError, "problem statement"):
            provider.normalize({})

    def test_typed_review_preserves_release_blocker(self):
        output = ReviewOutput(
            status="block",
            summary="Security review found an authority violation.",
            release_blockers=["shared administrator credential"],
        )
        runner = FakeRunner(output)
        provider = OpenAIProductDevelopmentProvider(agents=fake_agents(), runner=runner)
        review = provider.review_security(
            {"problem": "autonomous maintenance"},
            {"architecture_summary": "agent action"},
            {"status": "warn"},
        )
        self.assertEqual("block", review["status"])
        self.assertEqual(["shared administrator credential"], review["release_blockers"])
        self.assertIn("autonomous maintenance", runner.calls[0][1])

    def test_untyped_worker_output_fails_closed(self):
        provider = OpenAIProductDevelopmentProvider(agents=fake_agents(), runner=FakeRunner({"status": "pass"}))
        with self.assertRaisesRegex(TypeError, "untyped"):
            provider.review_brand({"problem": "x"}, {"surface": "home"}, {"status": "pass"})

    def test_live_specialist_agent_contracts_construct_without_api_call(self):
        agents = build_product_agents(model="gpt-5.6-sol")
        workers = (
            agents.product,
            agents.experience,
            agents.interface,
            agents.copy,
            agents.brand,
            agents.engineering,
            agents.cloud,
            agents.security,
            agents.accessibility,
            agents.quality,
        )
        self.assertEqual(10, len(workers))
        self.assertTrue(all(worker.output_type is not None for worker in workers))
        self.assertTrue(all(worker.tools == [] for worker in workers))


if __name__ == "__main__":
    unittest.main()
