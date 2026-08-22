from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from runtime.agent_identity_audit import audit_agent_identity_policy
from runtime.agent_identity_registry import (
    AGENT_IDENTITIES,
    BUSINESS_DATA,
    DISABLED_AGENT_IDS_ENV,
    DISABLED_WORK_TYPES_ENV,
    MAX_AGENT_TURNS_ENV,
    assert_agent_runtime_allowed,
    identity_for_actor,
    identity_manifest,
    runtime_status,
)
from runtime.graph_kernel import ActorRef, GraphDefinition, GraphKernel, GraphNode, NodeResult


class FakeTypedAgent:
    def __init__(self, name: str, tools=None):
        self.name = name
        self.tools = list(tools or [])
        self.output_type = object


class UnexpectedTool:
    pass


class AgentIdentityPolicyTests(unittest.TestCase):
    def test_every_current_worker_has_unique_nonhuman_identity(self):
        self.assertEqual(38, len(AGENT_IDENTITIES))
        manifest = identity_manifest()
        self.assertEqual(38, len({item["identity_id"] for item in manifest}))
        self.assertEqual(38, len({item["sdk_name"] for item in manifest}))
        self.assertTrue(all(item["authority"] == "A1" for item in manifest))
        self.assertTrue(all(item["secret_access"] is False for item in manifest))
        self.assertTrue(all(item["retry_limit"] == 0 for item in manifest))

    def test_only_four_research_identities_receive_hosted_web_search(self):
        web_enabled = {
            item.actor_id
            for item in AGENT_IDENTITIES.values()
            if item.allowed_tools == ("hosted_web_search",)
        }
        self.assertEqual(
            {
                "research-director-agent",
                "evidence-agent",
                "technology-agent",
                "contradiction-agent",
            },
            web_enabled,
        )
        self.assertTrue(all(item.work_type == "research_intelligence" for item in AGENT_IDENTITIES.values() if item.allowed_tools))

    def test_full_graph_and_sdk_identity_audit_passes(self):
        report = audit_agent_identity_policy()
        self.assertTrue(report.passed, report.issues)
        self.assertEqual(37, report.graph_agent_count)
        self.assertEqual(38, report.registered_identity_count)
        self.assertEqual(38, report.sdk_agent_count)

    def test_runtime_guard_allows_registered_tool_free_worker(self):
        agent = FakeTypedAgent("Marketing Agent")
        identity = assert_agent_runtime_allowed(
            agent,
            requested_max_turns=8,
            declared_model_data_classes=BUSINESS_DATA,
        )
        self.assertEqual("marketing-agent", identity.actor_id)

    def test_runtime_guard_rejects_unexpected_tool(self):
        agent = FakeTypedAgent("Marketing Agent", tools=[UnexpectedTool()])
        with self.assertRaisesRegex(RuntimeError, "tool policy mismatch"):
            assert_agent_runtime_allowed(
                agent,
                requested_max_turns=8,
                declared_model_data_classes=BUSINESS_DATA,
            )

    def test_runtime_guard_rejects_model_data_expansion(self):
        agent = FakeTypedAgent("Marketing Agent")
        with self.assertRaisesRegex(RuntimeError, "model-data policy exceeded"):
            assert_agent_runtime_allowed(
                agent,
                requested_max_turns=8,
                declared_model_data_classes=("raw_learner_submission",),
            )

    def test_emergency_agent_disable_is_read_from_runtime_environment(self):
        identity = identity_for_actor("marketing-agent")
        with patch.dict(os.environ, {DISABLED_AGENT_IDS_ENV: identity.identity_id}, clear=True):
            status = runtime_status(identity.identity_id)
            self.assertFalse(status["enabled"])
            with self.assertRaisesRegex(RuntimeError, "disabled"):
                assert_agent_runtime_allowed(
                    FakeTypedAgent("Marketing Agent"),
                    requested_max_turns=8,
                    declared_model_data_classes=BUSINESS_DATA,
                )

    def test_emergency_work_type_disable_blocks_all_workers_in_work_type(self):
        with patch.dict(os.environ, {DISABLED_WORK_TYPES_ENV: "business_operations"}, clear=True):
            self.assertFalse(runtime_status("marketing-agent")["enabled"])
            self.assertFalse(runtime_status("finance-agent")["enabled"])
            self.assertTrue(runtime_status("career-action-agent")["enabled"])

    def test_global_turn_cap_contraction_fails_closed(self):
        with patch.dict(os.environ, {MAX_AGENT_TURNS_ENV: "4"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "turn budget exceeded"):
                assert_agent_runtime_allowed(
                    FakeTypedAgent("Marketing Agent"),
                    requested_max_turns=8,
                    declared_model_data_classes=BUSINESS_DATA,
                )

    def test_graph_kernel_blocks_disabled_registered_agent_before_handler(self):
        calls: list[str] = []
        definition = GraphDefinition(
            graph_id="fixture-graph",
            version="1",
            start_node="agent",
            nodes=(GraphNode("agent", ActorRef("marketing-agent", "agent", authority="A1"), "fixture.run"),),
            edges=(),
        )
        kernel = GraphKernel()
        kernel.register_handler("fixture.run", lambda state: (calls.append("ran") or NodeResult()))
        execution = kernel.start(definition, execution_id="disabled-agent-fixture", state={})
        with patch.dict(os.environ, {DISABLED_AGENT_IDS_ENV: "marketing-agent"}, clear=True):
            result = kernel.run(definition, execution)
        self.assertEqual("failed", result.status)
        self.assertIn("agent runtime policy blocked", result.failure)
        self.assertEqual([], calls)

    def test_generic_unregistered_graph_agent_remains_supported(self):
        definition = GraphDefinition(
            graph_id="extension-fixture",
            version="1",
            start_node="agent",
            nodes=(GraphNode("agent", ActorRef("extension-agent", "agent", authority="A1"), "fixture.run"),),
            edges=(),
        )
        kernel = GraphKernel()
        kernel.register_handler("fixture.run", lambda state: NodeResult(patch={"ok": True}))
        result = kernel.run(definition, kernel.start(definition, execution_id="extension-fixture", state={}))
        self.assertEqual("completed", result.status)
        self.assertTrue(result.state["ok"])


if __name__ == "__main__":
    unittest.main()
