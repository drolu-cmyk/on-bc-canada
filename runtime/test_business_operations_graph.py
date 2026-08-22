from __future__ import annotations

import unittest

from runtime.business_operations_graph import BusinessOperationsGraph
from runtime.graph_kernel import GraphKernel


class FakeProvider:
    def __init__(self, *, status="pass", blockers=None):
        self.status = status
        self.blockers = blockers or []
        self.calls = []

    def normalize(self, request):
        workstream = request["workstream"]
        action_class = request.get("action_class", "analysis")
        allowed = {
            "growth": {"analysis", "prepare", "external_publish"},
            "marketing": {"analysis", "prepare", "external_publish"},
            "partnerships": {"analysis", "prepare", "external_contact"},
            "operations": {"analysis", "prepare", "external_contact"},
            "finance": {"analysis", "prepare", "external_contact", "financial_commitment"},
        }
        if workstream not in allowed or action_class not in allowed[workstream]:
            raise ValueError("invalid business request")
        return {
            "workstream": workstream,
            "action_class": action_class,
            "problem": request["problem"],
            "market": "Canada",
        }

    def _output(self, workstream):
        self.calls.append(workstream)
        return {
            "status": self.status,
            "summary": f"{workstream} analysis complete",
            "blockers": list(self.blockers),
            "warnings": [],
        }

    def analyze_growth(self, request):
        return self._output("growth")

    def analyze_marketing(self, request):
        return self._output("marketing")

    def analyze_partnerships(self, request):
        return self._output("partnerships")

    def analyze_operations(self, request):
        return self._output("operations")

    def analyze_finance(self, request):
        return self._output("finance")


class BusinessOperationsGraphTests(unittest.TestCase):
    def start(self, request, provider=None, execution_id="business-1"):
        provider = provider or FakeProvider()
        kernel = GraphKernel()
        graph = BusinessOperationsGraph(kernel=kernel, provider=provider)
        graph.register()
        definition, execution = graph.start(execution_id=execution_id, request=request)
        return provider, kernel, definition, execution

    def test_growth_analysis_routes_only_to_growth_and_finishes_directly(self):
        provider, _, _, execution = self.start(
            {"workstream": "growth", "action_class": "analysis", "problem": "Understand pathway interest conversion."}
        )
        self.assertEqual(["growth"], provider.calls)
        self.assertEqual("completed", execution.status)
        self.assertEqual("analysis_complete", execution.state["business_record"]["status"])
        self.assertEqual("A1", execution.state["operating_assurance"]["required_authority"])

    def test_operations_analysis_finishes_without_human_gate(self):
        provider, _, _, execution = self.start(
            {"workstream": "operations", "action_class": "analysis", "problem": "Reduce registration handling friction."},
            execution_id="business-ops",
        )
        self.assertEqual(["operations"], provider.calls)
        self.assertEqual("completed", execution.status)
        self.assertIsNone(execution.pending_approval)

    def test_marketing_external_publish_stops_at_a3(self):
        _, kernel, definition, execution = self.start(
            {"workstream": "marketing", "action_class": "external_publish", "problem": "Prepare a research-based public campaign."},
            execution_id="business-marketing",
        )
        self.assertEqual("waiting_approval", execution.status)
        self.assertEqual("external_action_review", execution.current_node)
        self.assertEqual("A3", execution.pending_approval["authority"])
        execution = kernel.decide(
            definition,
            execution,
            approved=True,
            approver_id="external-action-accountable-person",
            note="Reviewed claims and publication package.",
        )
        self.assertEqual("authorized_for_external_execution", execution.state["business_record"]["status"])

    def test_partnership_external_contact_stops_at_a3(self):
        _, _, _, execution = self.start(
            {"workstream": "partnerships", "action_class": "external_contact", "problem": "Prepare employer partnership outreach."},
            execution_id="business-partnerships",
        )
        self.assertEqual("waiting_approval", execution.status)
        self.assertEqual("A3", execution.pending_approval["authority"])

    def test_financial_commitment_stops_at_a4(self):
        _, kernel, definition, execution = self.start(
            {"workstream": "finance", "action_class": "financial_commitment", "problem": "Evaluate whether to commit a defined cloud budget."},
            execution_id="business-finance",
        )
        self.assertEqual("waiting_approval", execution.status)
        self.assertEqual("financial_commitment_review", execution.current_node)
        self.assertEqual("A4", execution.pending_approval["authority"])
        execution = kernel.decide(
            definition,
            execution,
            approved=True,
            approver_id="financial-accountable-person",
            note="Reviewed commitment separately from payment execution.",
        )
        self.assertEqual("authorized_for_financial_execution", execution.state["business_record"]["status"])

    def test_worker_blocker_routes_to_blocked_without_human_gate(self):
        provider = FakeProvider(status="block", blockers=["claim lacks evidence"])
        _, _, _, execution = self.start(
            {"workstream": "marketing", "action_class": "external_publish", "problem": "Publish an unsupported outcome claim."},
            provider=provider,
            execution_id="business-blocked",
        )
        self.assertEqual("completed", execution.status)
        self.assertEqual("blocked", execution.state["business_record"]["status"])
        self.assertIsNone(execution.pending_approval)

    def test_invalid_workstream_action_combination_fails_closed(self):
        _, _, _, execution = self.start(
            {"workstream": "growth", "action_class": "financial_commitment", "problem": "Commit funds from a growth analysis."},
            execution_id="business-invalid",
        )
        self.assertEqual("failed", execution.status)
        self.assertIn("invalid business request", execution.failure)

    def test_agent_nodes_are_a1_and_human_gates_have_distinct_authority(self):
        definition = BusinessOperationsGraph.definition()
        agents = [node for node in definition.nodes if node.actor.kind == "agent"]
        self.assertEqual(5, len(agents))
        self.assertTrue(all(node.actor.authority == "A1" for node in agents))
        a3 = next(node for node in definition.nodes if node.node_id == "external_action_review")
        a4 = next(node for node in definition.nodes if node.node_id == "financial_commitment_review")
        self.assertEqual("A3", a3.actor.authority)
        self.assertEqual("A4", a4.actor.authority)


if __name__ == "__main__":
    unittest.main()
