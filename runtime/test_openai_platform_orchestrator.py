from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from runtime.agent_identity_registry import DISABLED_AGENT_IDS_ENV
from runtime.openai_platform_orchestrator import (
    OpenAIPlatformOrchestrator,
    OrchestrationEnvelope,
    PlatformRouteOutput,
    build_platform_orchestrator_agent,
)
from runtime.platform_graph_harness import DispatchRequest, PlatformGraphHarness


class FakeAgent:
    name = "Platform Orchestrator Agent"
    tools = []
    output_type = PlatformRouteOutput


class FakeRunner:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def run_sync(self, agent, input, **kwargs):
        self.calls.append((agent, input, kwargs))
        return SimpleNamespace(final_output=self.output)


class OpenAIPlatformOrchestratorTests(unittest.TestCase):
    def test_typed_route_proposal_is_still_subject_to_deterministic_harness(self):
        output = PlatformRouteOutput(
            work_type="employer_workforce",
            reason="The objective concerns an organization-level workflow and bounded AI adoption.",
            required_inputs=["aggregate workflow tasks"],
            risk_flags=[],
        )
        runner = FakeRunner(output)
        orchestrator = OpenAIPlatformOrchestrator(agent=FakeAgent(), runner=runner)
        proposal = orchestrator.propose(
            OrchestrationEnvelope(
                objective="Assess whether an intake workflow has a justified AI opportunity.",
                mode="analyze",
                requested_effect="analysis",
                declared_data_classes=("organization_workflow", "aggregate_metrics"),
            )
        )
        self.assertEqual("employer_workforce", proposal["work_type"])
        decision = PlatformGraphHarness().validate_dispatch(
            DispatchRequest(
                proposal["work_type"],
                "analyze",
                "analysis",
                ("organization_workflow", "aggregate_metrics"),
            )
        )
        self.assertTrue(decision.allowed)
        self.assertEqual("employer-workforce", decision.graph_id)
        self.assertIn("INPUT_JSON", runner.calls[0][1])

    def test_manager_cannot_make_forbidden_execution_allowed(self):
        output = PlatformRouteOutput(
            work_type="product_development",
            reason="The objective concerns product implementation.",
            required_inputs=[],
            risk_flags=["production action requested"],
        )
        orchestrator = OpenAIPlatformOrchestrator(agent=FakeAgent(), runner=FakeRunner(output))
        proposal = orchestrator.propose(
            OrchestrationEnvelope(
                objective="Change the production product.",
                mode="execute",
                requested_effect="production_mutation",
                declared_data_classes=("operational",),
            )
        )
        decision = PlatformGraphHarness().validate_dispatch(
            DispatchRequest(
                proposal["work_type"],
                "execute",
                "production_mutation",
                ("operational",),
            )
        )
        self.assertFalse(decision.allowed)
        self.assertIn("no current graph", decision.reason)

    def test_disabled_manager_fails_before_runner_call(self):
        runner = FakeRunner(
            PlatformRouteOutput(
                work_type="research_intelligence",
                reason="fixture",
            )
        )
        orchestrator = OpenAIPlatformOrchestrator(agent=FakeAgent(), runner=runner)
        with patch.dict(os.environ, {DISABLED_AGENT_IDS_ENV: "platform-orchestrator-agent"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "disabled"):
                orchestrator.propose(
                    OrchestrationEnvelope(
                        objective="Research a technical-work signal.",
                        mode="analyze",
                        requested_effect="analysis",
                        declared_data_classes=("public_research",),
                    )
                )
        self.assertEqual([], runner.calls)

    def test_untyped_output_fails_closed(self):
        orchestrator = OpenAIPlatformOrchestrator(agent=FakeAgent(), runner=FakeRunner({"work_type": "research_intelligence"}))
        with self.assertRaisesRegex(TypeError, "untyped"):
            orchestrator.propose(
                OrchestrationEnvelope(
                    objective="Research an emerging capability.",
                    mode="analyze",
                    requested_effect="analysis",
                    declared_data_classes=("public_research",),
                )
            )

    def test_empty_objective_is_rejected_before_model_call(self):
        runner = FakeRunner(None)
        orchestrator = OpenAIPlatformOrchestrator(agent=FakeAgent(), runner=runner)
        with self.assertRaisesRegex(ValueError, "objective"):
            orchestrator.propose(
                OrchestrationEnvelope(
                    objective="   ",
                    mode="analyze",
                    requested_effect="analysis",
                    declared_data_classes=("public_research",),
                )
            )
        self.assertEqual([], runner.calls)

    def test_current_sdk_agent_constructs_without_tools_or_api_call(self):
        agent = build_platform_orchestrator_agent(model="gpt-5.6-sol")
        self.assertIsNotNone(agent.output_type)
        self.assertEqual([], agent.tools)


if __name__ == "__main__":
    unittest.main()
