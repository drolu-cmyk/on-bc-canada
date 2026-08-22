from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.employer_workforce_runner import start_employer_workforce_analysis
from runtime.graph_execution_store import GraphExecutionStore
from runtime.test_employer_workforce_context import employer_request


class FakeEmployerProvider:
    def __init__(self):
        self.calls = []
        self.payloads = []

    def _capture(self, name, payload):
        self.calls.append(name)
        self.payloads.append(payload)

    def analyze_workflow(self, payload):
        self._capture("workflow", payload)
        return {
            "workflow_summary": "Two linked intake tasks with repeated manual classification and human-owned routing decisions.",
            "findings": [
                {
                    "task_id": "review-intake",
                    "issue": "Repeated classification work creates avoidable handling time and inconsistent labels.",
                    "decision_points": ["Select service category"],
                    "human_accountability_points": ["Confirm ambiguous or high-impact classifications"],
                },
                {
                    "task_id": "route-request",
                    "issue": "Incomplete routing context can create rework.",
                    "decision_points": ["Select destination queue"],
                    "human_accountability_points": ["Retain final routing authority for exceptional cases"],
                },
            ],
            "cross_task_constraints": ["Do not use production personal data in the first pilot"],
        }

    def identify_ai_opportunities(self, payload):
        self._capture("opportunities", payload)
        return {
            "opportunities": [
                {
                    "opportunity_id": "intake-classification-assist",
                    "task_ids": ["review-intake", "route-request"],
                    "pattern": "assist",
                    "value_hypothesis": "Suggest consistent categories and routing context while staff retain final decisions.",
                    "automation_boundary": "Recommendation only; no autonomous final routing in the first pilot.",
                    "evidence_needed": ["classification consistency", "staff correction rate", "handling-time comparison"],
                }
            ],
            "no_change_reasons": [],
        }

    def analyze_workforce_impact(self, payload):
        self._capture("workforce", payload)
        return {
            "role_impacts": [
                {
                    "role_label": "Intake Coordinator",
                    "affected_task_ids": ["review-intake", "route-request"],
                    "change_type": "assist",
                    "work_change": "Shift part of manual categorization toward reviewing and correcting bounded AI suggestions.",
                    "human_decisions_preserved": ["Final category for ambiguous requests", "Final exceptional routing decision"],
                },
                {
                    "role_label": "Program Manager",
                    "affected_task_ids": ["route-request"],
                    "change_type": "control_requirement",
                    "work_change": "Review exception patterns and approve changes to routing rules.",
                    "human_decisions_preserved": ["Approval of workflow-control changes"],
                },
            ],
            "organization_notes": ["No individual employee decision is implied."],
        }

    def identify_capability_demand(self, payload):
        self._capture("capabilities", payload)
        return {
            "demands": [
                {
                    "capability_name": "AI-assisted classification review",
                    "observable_work": "Evaluate AI category suggestions, identify failure patterns, and document when human correction is required.",
                    "source_task_ids": ["review-intake"],
                    "priority": "core",
                    "research_validation_required": True,
                },
                {
                    "capability_name": "Human oversight for AI routing",
                    "observable_work": "Define and apply decision boundaries for AI-supported routing and exceptions.",
                    "source_task_ids": ["route-request"],
                    "priority": "important",
                    "research_validation_required": True,
                },
            ],
            "note": "Organization-specific capability signals require research validation before platform adoption.",
        }

    def analyze_adoption_risk(self, payload):
        self._capture("risk", payload)
        return {
            "risks": [
                {
                    "opportunity_id": "intake-classification-assist",
                    "risk_type": "data_quality",
                    "risk": "Inconsistent historical category labels could distort suggestions.",
                    "mitigation": "Use a reviewed synthetic or deidentified test set and inspect category disagreement.",
                    "stop_condition": "Stop if disagreement exceeds the pre-agreed threshold or category meaning is unstable.",
                },
                {
                    "opportunity_id": "intake-classification-assist",
                    "risk_type": "human_oversight",
                    "risk": "Staff may over-rely on suggestions.",
                    "mitigation": "Keep explicit confirmation and exception review in the pilot workflow.",
                    "stop_condition": "Stop if the confirmation step can be bypassed or correction behavior cannot be observed.",
                },
            ],
            "cross_cutting_controls": ["No production personal data in first pilot", "Human confirmation remains mandatory"],
        }

    def design_pilot(self, payload):
        self._capture("pilot", payload)
        return {
            "pilot_id": "intake-assist-pilot-001",
            "opportunity_ids": ["intake-classification-assist"],
            "task_ids": ["review-intake", "route-request"],
            "pilot_scope": "Evaluate category and routing suggestions on a bounded test set with staff confirmation and no autonomous external action.",
            "success_measures": ["classification consistency", "correction rate", "handling time", "exception quality"],
            "stop_conditions": ["Unstable category definitions", "Human confirmation can be bypassed", "Material increase in misrouting"],
            "required_human_approvals": ["Approve test data", "Approve pilot start", "Approve any change in autonomy"],
        }

    def define_measurement(self, payload):
        self._capture("measurement", payload)
        return {
            "measures": [
                {
                    "measure_id": "intake-volume-context",
                    "definition": "Use monthly intake volume only as workload context, not an employee productivity score.",
                    "baseline_metric_id": "monthly-volume",
                    "interpretation": "Contextual denominator for organization-level pilot results.",
                },
                {
                    "measure_id": "classification-correction-rate",
                    "definition": "Share of AI category suggestions corrected by staff during the bounded pilot.",
                    "baseline_metric_id": None,
                    "interpretation": "Lower is better only after label quality and case mix are stable.",
                },
            ],
            "decision_rules": ["Do not increase autonomy unless quality, oversight, and exception controls all meet the agreed criteria."],
            "evidence_collection_notes": ["Aggregate at workflow level; do not produce employee rankings."],
        }


class NoOpportunityProvider(FakeEmployerProvider):
    def identify_ai_opportunities(self, payload):
        self._capture("opportunities", payload)
        return {
            "opportunities": [],
            "no_change_reasons": ["The supplied problem is primarily a category-definition and process-ownership issue that should be corrected before adding AI."],
        }


class InvalidCapabilityProvider(FakeEmployerProvider):
    def identify_capability_demand(self, payload):
        self._capture("capabilities", payload)
        return {
            "demands": [
                {
                    "capability_name": "AI-assisted classification review",
                    "observable_work": "Evaluate AI category suggestions against workflow rules.",
                    "source_task_ids": ["review-intake"],
                    "priority": "core",
                    "research_validation_required": False,
                }
            ],
            "note": "invalid fixture",
        }


class EmployerWorkforceGraphTests(unittest.TestCase):
    def test_bounded_analysis_produces_packet_without_external_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = FakeEmployerProvider()
            store = GraphExecutionStore(Path(tmp) / "graph.sqlite3")
            execution = start_employer_workforce_analysis(
                provider=provider,
                execution_store=store,
                execution_id="employer-analysis-001",
                request=employer_request(),
            )
            self.assertEqual("completed", execution.status)
            self.assertEqual("analysis_ready", execution.state["employer_status"])
            self.assertEqual(7, len(provider.calls))
            packet = execution.state["employer_workforce_packet"]
            self.assertEqual("org-canada-001", packet["organization_ref"])
            self.assertFalse(packet["assurance"]["employee_decision_authorized"])
            self.assertFalse(packet["assurance"]["production_deployment_authorized"])
            self.assertFalse(packet["assurance"]["work_intelligence_write_authorized"])
            self.assertTrue(packet["assurance"]["capability_signals_require_research_validation"])

            serialized_model_payloads = repr(provider.payloads)
            self.assertNotIn("org-canada-001", serialized_model_payloads)
            self.assertNotIn("employee_id", serialized_model_payloads)
            persisted = store.get_terminal_record(execution.execution_id, "employer_workforce")
            self.assertEqual("Community intake triage", persisted["workflow"]["workflow_name"])
            _, ledger = store.load_execution(execution.execution_id)
            self.assertTrue(all(event["privacy_class"] == "operational" for event in ledger.events))

    def test_no_justified_ai_opportunity_is_valid_terminal_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = NoOpportunityProvider()
            execution = start_employer_workforce_analysis(
                provider=provider,
                execution_store=GraphExecutionStore(Path(tmp) / "graph.sqlite3"),
                execution_id="employer-no-change-001",
                request=employer_request(),
            )
            self.assertEqual("completed", execution.status)
            self.assertEqual("no_change", execution.state["employer_status"])
            self.assertEqual("no_justified_ai_opportunity", execution.state["employer_workforce_packet"]["outcome"])
            self.assertEqual(["workflow", "opportunities"], provider.calls)

    def test_capability_signal_cannot_skip_research_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            execution = start_employer_workforce_analysis(
                provider=InvalidCapabilityProvider(),
                execution_store=GraphExecutionStore(Path(tmp) / "graph.sqlite3"),
                execution_id="employer-invalid-capability-001",
                request=employer_request(),
            )
            self.assertEqual("failed", execution.status)
            self.assertIn("must require research validation", execution.failure)


if __name__ == "__main__":
    unittest.main()
