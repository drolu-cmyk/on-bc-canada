from __future__ import annotations

import unittest

from runtime.graph_kernel import ActorRef, GraphDefinition, GraphEdge, GraphNode
from runtime.platform_graph_harness import (
    DispatchRequest,
    PlatformGraphHarness,
    evaluate_harness_cases,
    harness_manifest,
)
from runtime.platform_graph_registry import GRAPH_CONTRACTS, GraphContract, ProtectedStateChange, get_graph_contract


class PlatformGraphHarnessTests(unittest.TestCase):
    def test_all_registered_graphs_pass_current_contracts(self):
        reports = PlatformGraphHarness().require_valid_registry()
        self.assertEqual(6, len(reports))
        self.assertEqual(
            {
                "canadian-work-research",
                "product-development",
                "business-operations",
                "learner-execution",
                "career-mobility",
                "employer-workforce",
            },
            {report.graph_id for report in reports},
        )
        self.assertTrue(all(report.passed for report in reports))

    def test_registry_manifest_is_machine_readable_and_denies_external_execution(self):
        manifest = harness_manifest()
        self.assertTrue(manifest["passed"])
        self.assertTrue(all(graph["passed"] for graph in manifest["graphs"]))
        self.assertTrue(manifest["dispatch_cases"]["passed"])
        self.assertTrue(all(not contract.executes_external_effects for contract in GRAPH_CONTRACTS.values()))

    def test_dispatch_case_matrix_passes(self):
        result = evaluate_harness_cases()
        self.assertTrue(result["passed"], result["results"])
        self.assertGreaterEqual(result["case_count"], 10)

    def test_router_requires_explicit_supported_work_type(self):
        route = PlatformGraphHarness.route("career_mobility")
        self.assertEqual("career-mobility", route["graph_id"])
        with self.assertRaisesRegex(ValueError, "unknown platform work type"):
            PlatformGraphHarness.route("guess_for_me")
        with self.assertRaisesRegex(ValueError, "unknown platform work type"):
            get_graph_contract("deploy_everything")

    def test_agent_authority_above_contract_fails(self):
        graph = GraphDefinition(
            graph_id="unsafe-agent-authority",
            version="1",
            start_node="agent",
            nodes=(GraphNode("agent", ActorRef("worker", "agent", authority="A3"), "test.handler"),),
            edges=(),
        )
        contract = GraphContract(
            work_type="unsafe",
            graph_id=graph.graph_id,
            purpose="fixture",
            definition_factory=lambda: graph,
            terminal_record="result",
        )
        report = PlatformGraphHarness().validate_contract(contract)
        self.assertFalse(report.passed)
        self.assertTrue(any(issue.rule == "agent_authority" for issue in report.issues))

    def test_unregistered_human_gate_fails(self):
        graph = GraphDefinition(
            graph_id="hidden-human-gate",
            version="1",
            start_node="start",
            nodes=(
                GraphNode("start", ActorRef("service", "service"), "test.start"),
                GraphNode("review", ActorRef("human", "human", authority="A3"), approval_reason="review"),
            ),
            edges=(GraphEdge("start", "review"),),
        )
        contract = GraphContract(
            work_type="hidden",
            graph_id=graph.graph_id,
            purpose="fixture",
            definition_factory=lambda: graph,
            terminal_record="result",
        )
        report = PlatformGraphHarness().validate_contract(contract)
        self.assertFalse(report.passed)
        self.assertTrue(any(issue.rule == "human_gates" for issue in report.issues))

    def test_protected_state_change_without_required_human_predecessor_fails(self):
        graph = GraphDefinition(
            graph_id="unguarded-write",
            version="1",
            start_node="prepare",
            nodes=(
                GraphNode("prepare", ActorRef("worker", "agent", authority="A1"), "test.prepare"),
                GraphNode("write", ActorRef("writer", "service", authority="A1"), "test.write"),
            ),
            edges=(GraphEdge("prepare", "write"),),
        )
        contract = GraphContract(
            work_type="unguarded",
            graph_id=graph.graph_id,
            purpose="fixture",
            definition_factory=lambda: graph,
            protected_state_changes=(ProtectedStateChange("write", "sensitive record", "A3"),),
            terminal_record="result",
        )
        report = PlatformGraphHarness().validate_contract(contract)
        self.assertFalse(report.passed)
        issue = next(issue for issue in report.issues if issue.rule == "protected_state_change")
        self.assertIn("not every path", issue.detail)

    def test_protected_state_change_accepts_all_paths_through_required_gate(self):
        graph = GraphDefinition(
            graph_id="guarded-write",
            version="1",
            start_node="prepare",
            nodes=(
                GraphNode("prepare", ActorRef("worker", "agent", authority="A1"), "test.prepare"),
                GraphNode("review", ActorRef("human", "human", authority="A3"), approval_reason="review"),
                GraphNode("write", ActorRef("writer", "service", authority="A1"), "test.write"),
            ),
            edges=(
                GraphEdge("prepare", "review"),
                GraphEdge("review", "write", route="approved"),
            ),
        )
        contract = GraphContract(
            work_type="guarded",
            graph_id=graph.graph_id,
            purpose="fixture",
            definition_factory=lambda: graph,
            runtime_data_classes=("operational",),
            model_data_classes=("operational",),
            human_gates=(("review", "A3"),),
            protected_state_changes=(ProtectedStateChange("write", "sensitive record", "A3"),),
            terminal_record="result",
        )
        self.assertTrue(PlatformGraphHarness().validate_contract(contract).passed)

    def test_business_and_learner_sensitive_nodes_have_declared_authority(self):
        business = GRAPH_CONTRACTS["business_operations"]
        learner = GRAPH_CONTRACTS["learner_execution"]
        self.assertEqual(
            {"external_action_review": "A3", "financial_commitment_review": "A4"},
            dict(business.human_gates),
        )
        self.assertEqual(
            {"finalize_external": "A3", "finalize_financial": "A4"},
            {item.node_id: item.required_human_authority for item in business.protected_state_changes},
        )
        self.assertEqual({"human_assessment": "A3"}, dict(learner.human_gates))
        self.assertEqual("A3", learner.protected_state_changes[0].required_human_authority)

    def test_model_context_rejects_raw_learner_submission(self):
        decision = PlatformGraphHarness().validate_model_context("learner_execution", ("raw_learner_submission",))
        self.assertFalse(decision.allowed)
        self.assertIn("forbidden", decision.reason)

    def test_career_model_context_excludes_private_learner_reference(self):
        harness = PlatformGraphHarness()
        accepted = harness.validate_model_context(
            "career_mobility",
            ("deidentified_accepted_capability_metadata", "work_intelligence"),
        )
        self.assertTrue(accepted.allowed)
        rejected = harness.validate_model_context("career_mobility", ("learner_private_reference",))
        self.assertFalse(rejected.allowed)
        self.assertIn("outside the model contract", rejected.reason)

    def test_employer_model_context_rejects_employee_level_data(self):
        decision = PlatformGraphHarness().validate_model_context("employer_workforce", ("employee_individual",))
        self.assertFalse(decision.allowed)
        self.assertIn("forbidden", decision.reason)

    def test_product_graph_cannot_execute_production_mutation(self):
        decision = PlatformGraphHarness().validate_dispatch(
            DispatchRequest("product_development", "execute", "production_mutation", ("operational",))
        )
        self.assertFalse(decision.allowed)
        self.assertIn("no current graph", decision.reason)

    def test_business_graph_can_authorize_financial_commitment_but_not_move_money(self):
        harness = PlatformGraphHarness()
        authorization = harness.validate_dispatch(
            DispatchRequest(
                "business_operations",
                "authorize",
                "financial_commitment_authorization_record",
                ("financial_summary",),
            )
        )
        self.assertTrue(authorization.allowed)
        self.assertEqual("A4", authorization.required_authority)
        execution = harness.validate_dispatch(
            DispatchRequest("business_operations", "execute", "financial_transaction", ("financial_summary",))
        )
        self.assertFalse(execution.allowed)

    def test_learner_evidence_write_requires_a3(self):
        decision = PlatformGraphHarness().validate_dispatch(
            DispatchRequest(
                "learner_execution",
                "execute",
                "learner_capability_evidence_write",
                ("learner_private_reference", "learner_evidence_reference", "capability_standard"),
            )
        )
        self.assertTrue(decision.allowed)
        self.assertEqual("A3", decision.required_authority)
        self.assertEqual("learner-execution", decision.graph_id)

    def test_employer_signal_may_handoff_to_research_not_work_intelligence(self):
        harness = PlatformGraphHarness()
        research = harness.validate_handoff(
            source_work_type="employer_workforce",
            target_kind="graph",
            target_id="canadian-work-research",
            payload_data_classes=("organization_aggregate", "capability_signal"),
        )
        self.assertTrue(research["allowed"])
        direct_store = harness.validate_handoff(
            source_work_type="employer_workforce",
            target_kind="store",
            target_id="work-intelligence",
            payload_data_classes=("capability_signal",),
        )
        self.assertFalse(direct_store["allowed"])
        self.assertIn("direct handoff is not registered", direct_store["reason"])

    def test_learner_to_career_handoff_requires_accepted_evidence_boundary(self):
        harness = PlatformGraphHarness()
        allowed = harness.validate_handoff(
            source_work_type="learner_execution",
            target_kind="graph",
            target_id="career-mobility",
            payload_data_classes=("learner_private_reference",),
        )
        self.assertTrue(allowed["allowed"])
        self.assertEqual("A3", allowed["required_human_authority"])
        raw = harness.validate_handoff(
            source_work_type="learner_execution",
            target_kind="graph",
            target_id="career-mobility",
            payload_data_classes=("raw_learner_submission",),
        )
        self.assertFalse(raw["allowed"])
        self.assertIn("handoff payload exceeds contract", raw["reason"])

    def test_unknown_dispatch_fails_closed(self):
        decision = PlatformGraphHarness().validate_dispatch(
            DispatchRequest("invented_workflow", "analyze", "analysis", ("operational",))
        )
        self.assertFalse(decision.allowed)
        self.assertIsNone(decision.graph_id)
        self.assertIn("unknown platform work type", decision.reason)


if __name__ == "__main__":
    unittest.main()
