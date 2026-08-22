from __future__ import annotations

import unittest
from types import SimpleNamespace

from runtime.openai_business_operations_provider import (
    BusinessAgentSet,
    FinanceOutput,
    MarketingOutput,
    OpenAIBusinessOperationsProvider,
    build_business_agents,
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


def fake_agents() -> BusinessAgentSet:
    return BusinessAgentSet(*[FakeAgent(name) for name in ("growth", "marketing", "partnerships", "operations", "finance")])


class OpenAIBusinessOperationsProviderTests(unittest.TestCase):
    def test_normalize_enforces_workstream_action_policy(self):
        provider = OpenAIBusinessOperationsProvider(agents=fake_agents(), runner=FakeRunner(None))
        normalized = provider.normalize(
            {"workstream": "marketing", "action_class": "external_publish", "problem": "  Prepare campaign  "}
        )
        self.assertEqual("marketing", normalized["workstream"])
        self.assertEqual("external_publish", normalized["action_class"])
        self.assertEqual("Prepare campaign", normalized["problem"])
        self.assertEqual("Canada", normalized["market"])

        with self.assertRaisesRegex(ValueError, "not permitted"):
            provider.normalize(
                {"workstream": "growth", "action_class": "financial_commitment", "problem": "Commit funds"}
            )

    def test_marketing_output_separates_proof_from_unverified_claims(self):
        output = MarketingOutput(
            status="warn",
            summary="Campaign can be prepared but one outcome claim lacks evidence.",
            audience=["Canadian career-transition learner"],
            message="Build technical capability through work-like practice.",
            proof_points=["Learner access is CAD $0 at launch."],
            claims_needing_evidence=["employment outcome claim"],
            channels=["research insight"],
            content_assets=["pathway explainer"],
            conversion_action="Register interest",
            warnings=["Do not publish the outcome claim."],
        )
        runner = FakeRunner(output)
        provider = OpenAIBusinessOperationsProvider(agents=fake_agents(), runner=runner)
        result = provider.analyze_marketing(
            {
                "workstream": "marketing",
                "action_class": "prepare",
                "problem": "Prepare launch messaging.",
                "evidence": ["CAD $0 launch"],
            }
        )
        self.assertEqual(["employment outcome claim"], result["claims_needing_evidence"])
        self.assertIn("CAD $0", result["proof_points"][0])
        self.assertIn("Prepare launch messaging", runner.calls[0][1])

    def test_finance_output_cannot_execute_commitment(self):
        output = FinanceOutput(
            status="pass",
            summary="Budget scenario prepared from supplied inputs.",
            question="Whether the defined model budget is acceptable.",
            supplied_metrics_used=["monthly model budget CAD 500"],
            assumptions=[],
            cost_drivers=["model use"],
            scenarios=["Hold spend at supplied ceiling."],
            guardrails=["No spend above the supplied ceiling without A4 authorization."],
            decision_notes=["Separate authorization from payment execution."],
        )
        provider = OpenAIBusinessOperationsProvider(agents=fake_agents(), runner=FakeRunner(output))
        result = provider.analyze_finance(
            {
                "workstream": "finance",
                "action_class": "financial_commitment",
                "problem": "Evaluate a CAD 500 monthly model ceiling.",
                "metrics": ["monthly model budget CAD 500"],
            }
        )
        self.assertIn("Separate authorization", result["decision_notes"][0])

    def test_untyped_worker_output_fails_closed(self):
        provider = OpenAIBusinessOperationsProvider(agents=fake_agents(), runner=FakeRunner({"status": "pass"}))
        with self.assertRaisesRegex(TypeError, "untyped"):
            provider.analyze_operations(
                {"workstream": "operations", "action_class": "analysis", "problem": "Review intake."}
            )

    def test_live_agent_contracts_construct_without_tools_or_api_call(self):
        agents = build_business_agents(model="gpt-5.6-sol")
        workers = (agents.growth, agents.marketing, agents.partnerships, agents.operations, agents.finance)
        self.assertEqual(5, len(workers))
        self.assertTrue(all(worker.output_type is not None for worker in workers))
        self.assertTrue(all(worker.tools == [] for worker in workers))


if __name__ == "__main__":
    unittest.main()
