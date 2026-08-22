from __future__ import annotations

import unittest

from runtime.platform_harness import (
    DispatchRequest,
    PlatformHarness,
    WORKFLOW_CONTRACTS,
    evaluate_harness_cases,
)


class PlatformHarnessTests(unittest.TestCase):
    def setUp(self):
        self.harness = PlatformHarness()

    def test_registry_matches_live_graph_definitions_and_authority(self):
        audit = self.harness.audit_registry()
        self.assertTrue(audit["passed"], audit["errors"])
        self.assertEqual(6, audit["workflow_count"])

    def test_contract_case_matrix_passes(self):
        result = evaluate_harness_cases(self.harness)
        self.assertTrue(result["passed"], result["results"])
        self.assertGreaterEqual(result["case_count"], 10)

    def test_every_registered_graph_keeps_agent_authority_at_a1(self):
        audit = self.harness.audit_registry()
        self.assertTrue(audit["passed"])
        for contract in WORKFLOW_CONTRACTS.values():
            self.assertNotIn("employment_decision", contract.executable_map)
            self.assertNotIn("financial_transaction", contract.executable_map)
            self.assertNotIn("production_mutation", contract.executable_map)
            self.assertNotIn("external_publish", contract.executable_map)
            self.assertNotIn("external_contact", contract.executable_map)
            self.assertNotIn("credential_issue", contract.executable_map)

    def test_model_context_rejects_raw_learner_submission(self):
        decision = self.harness.validate_model_context("learner_support", ("raw_learner_submission",))
        self.assertFalse(decision.allowed)
        self.assertIn("forbidden", decision.reason)

    def test_career_model_context_accepts_only_bounded_evidence_metadata(self):
        accepted = self.harness.validate_model_context(
            "career_mobility",
            ("learner_deidentified", "accepted_capability_metadata", "work_intelligence"),
        )
        self.assertTrue(accepted.allowed)
        rejected = self.harness.validate_model_context(
            "career_mobility",
            ("learner_private_reference",),
        )
        self.assertFalse(rejected.allowed)
        self.assertIn("outside the model contract", rejected.reason)

    def test_employer_model_context_rejects_employee_level_data(self):
        decision = self.harness.validate_model_context("employer_workforce", ("employee_individual",))
        self.assertFalse(decision.allowed)
        self.assertIn("forbidden", decision.reason)

    def test_product_graph_cannot_execute_production_mutation(self):
        decision = self.harness.validate_dispatch(
            DispatchRequest("product_change", "execute", "production_mutation", ("internal_operational",))
        )
        self.assertFalse(decision.allowed)
        self.assertIn("no current graph", decision.reason)

    def test_business_graph_can_prepare_a4_financial_authorization_but_not_move_money(self):
        authorization = self.harness.validate_dispatch(
            DispatchRequest(
                "business_operations",
                "authorize",
                "financial_commitment_authorization_record",
                ("financial_summary",),
            )
        )
        self.assertTrue(authorization.allowed)
        self.assertEqual("A4", authorization.required_authority)
        execution = self.harness.validate_dispatch(
            DispatchRequest("business_operations", "execute", "financial_transaction", ("financial_summary",))
        )
        self.assertFalse(execution.allowed)

    def test_learner_evidence_write_requires_a3_and_stays_inside_learner_graph(self):
        decision = self.harness.validate_dispatch(
            DispatchRequest(
                "learner_support",
                "execute",
                "learner_capability_evidence_write",
                ("learner_private_reference", "learner_evidence_reference", "capability_standard"),
            )
        )
        self.assertTrue(decision.allowed)
        self.assertEqual("A3", decision.required_authority)
        self.assertEqual("learner-execution", decision.graph_id)

    def test_employer_capability_signal_may_handoff_to_research_not_work_intelligence(self):
        research = self.harness.validate_handoff(
            source_workflow_key="employer_workforce",
            target_kind="graph",
            target_id="canadian-work-research",
            payload_data_classes=("organization_aggregate", "capability_signal"),
        )
        self.assertTrue(research["allowed"])
        direct_store = self.harness.validate_handoff(
            source_workflow_key="employer_workforce",
            target_kind="store",
            target_id="work-intelligence",
            payload_data_classes=("capability_signal",),
        )
        self.assertFalse(direct_store["allowed"])
        self.assertIn("direct handoff is not registered", direct_store["reason"])

    def test_learner_to_career_handoff_accepts_only_accepted_capability_metadata(self):
        allowed = self.harness.validate_handoff(
            source_workflow_key="learner_support",
            target_kind="graph",
            target_id="career-mobility",
            payload_data_classes=("accepted_capability_metadata", "learner_deidentified"),
        )
        self.assertTrue(allowed["allowed"])
        raw = self.harness.validate_handoff(
            source_workflow_key="learner_support",
            target_kind="graph",
            target_id="career-mobility",
            payload_data_classes=("raw_learner_submission",),
        )
        self.assertFalse(raw["allowed"])
        self.assertIn("handoff payload exceeds contract", raw["reason"])

    def test_unknown_workflow_fails_closed(self):
        decision = self.harness.validate_dispatch(
            DispatchRequest("invented-workflow", "analyze", "analysis", ("internal_operational",))
        )
        self.assertFalse(decision.allowed)
        self.assertIsNone(decision.graph_id)
        self.assertIn("not registered", decision.reason)


if __name__ == "__main__":
    unittest.main()
