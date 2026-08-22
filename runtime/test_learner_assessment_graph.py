from __future__ import annotations

import unittest

from runtime.graph_kernel import GraphKernel
from runtime.learner_assessment_graph import LearnerAssessmentGraph


def request(*, include_revision=True, include_defense=True, include_changed=True):
    submission = {
        "submission_id": "submission-assessment-001",
        "artifact_refs": ["artifact://evaluation-report"],
        "artifact_types": ["evaluation_report"],
        "revision_ref": "artifact://revision" if include_revision else None,
        "defense_response_ref": "artifact://defense" if include_defense else None,
        "changed_scenario_response_ref": "artifact://changed" if include_changed else None,
        "mission_requirements": [
            {"capability_id": "agent-evaluation", "standard_id": "agent-evaluation-proof"}
        ],
    }
    return {
        "submission": submission,
        "mission": {
            "unit_id": "agent-mission",
            "title": "Agent evaluation mission",
            "purpose": "Evaluate and defend a bounded agent system.",
        },
        "standards": [
            {
                "capability_id": "agent-evaluation",
                "standard_id": "agent-evaluation-proof",
                "description": "Evaluate a bounded agent against explicit tasks and failure conditions.",
                "artifact_types": ["evaluation_report", "oral_defense"],
                "minimum_level": "evaluate",
                "requires_revision": True,
                "requires_defense": True,
                "requires_changed_scenario": True,
            }
        ],
        "evidence_material": [
            {
                "evidence_ref": "artifact://evaluation-report",
                "summary": "Evaluation covers success cases, tool failures, and permission failures.",
            }
        ],
    }


class FakeProvider:
    def __init__(self, *, review_status="ready", verdict="meets", challenge_status="clear", extra_finding=False):
        self.review_status = review_status
        self.verdict = verdict
        self.challenge_status = challenge_status
        self.extra_finding = extra_finding

    def normalize(self, value):
        return value

    def review_submission(self, value):
        return {
            "status": self.review_status,
            "strengths": ["bounded evaluation evidence"],
            "gaps": [],
            "feedback": ["defend why the failure cases are representative"],
            "learner_actions": ["add explicit failure rationale"] if self.review_status == "action_recommended" else [],
        }

    def assess_evidence(self, value, review):
        findings = [
            {
                "capability_id": "agent-evaluation",
                "standard_id": "agent-evaluation-proof",
                "verdict": self.verdict,
                "rationale": "fixture judgment",
                "evidence_refs": ["artifact://evaluation-report"],
                "confidence": 0.84,
            }
        ]
        if self.extra_finding:
            findings.append(
                {
                    "capability_id": "invented-capability",
                    "standard_id": "invented-proof",
                    "verdict": "meets",
                    "rationale": "should be rejected",
                    "evidence_refs": [],
                    "confidence": 0.9,
                }
            )
        return {"findings": findings, "overall_note": "fixture assessment"}

    def challenge_assessment(self, value, review, assessment):
        return {
            "status": self.challenge_status,
            "concerns": ["evidence does not survive changed scenario"] if self.challenge_status == "concern" else [],
            "challenge_questions": [],
            "note": "fixture challenge",
        }


class LearnerAssessmentGraphTests(unittest.TestCase):
    def start(self, value=None, provider=None, execution_id="assessment-1"):
        kernel = GraphKernel(
            event_privacy_class="learner_private",
            event_retention_class="quality_record",
            event_learner_id="learner-ref-001",
            event_cohort_id="cohort-001",
        )
        graph = LearnerAssessmentGraph(kernel=kernel, provider=provider or FakeProvider())
        graph.register()
        definition, execution = graph.start(execution_id=execution_id, request=value or request())
        return kernel, definition, execution

    def test_complete_evidence_stops_at_a3_human_review(self):
        kernel, definition, execution = self.start()
        self.assertEqual("waiting_approval", execution.status)
        self.assertEqual("capability_evidence_review", execution.current_node)
        self.assertEqual("A3", execution.pending_approval["authority"])
        self.assertEqual("ready_for_human_review", execution.state["evidence_assurance"]["status"])
        self.assertTrue(all(event["privacy_class"] == "learner_private" for event in kernel.ledger.events))
        self.assertTrue(all(event["learner_id"] == "learner-ref-001" for event in kernel.ledger.events))

        execution = kernel.decide(
            definition,
            execution,
            approved=True,
            approver_id="assessment-accountable-person",
            note="Reviewed evidence and challenge record.",
        )
        self.assertEqual("completed", execution.status)
        self.assertEqual("accepted_capability_evidence", execution.state["assessment_record"]["status"])

    def test_missing_revision_routes_to_learner_action_without_human_gate(self):
        _, _, execution = self.start(request(include_revision=False), execution_id="assessment-missing-revision")
        self.assertEqual("completed", execution.status)
        self.assertEqual("learner_action_required", execution.state["assessment_record"]["status"])
        self.assertIsNone(execution.pending_approval)
        self.assertTrue(any("revision evidence" in item for item in execution.state["evidence_assurance"]["learner_actions"]))

    def test_non_meeting_assessment_routes_to_not_ready(self):
        _, _, execution = self.start(provider=FakeProvider(verdict="partially_meets"), execution_id="assessment-not-ready")
        self.assertEqual("completed", execution.status)
        self.assertEqual("evidence_not_ready", execution.state["assessment_record"]["status"])
        self.assertIsNone(execution.pending_approval)

    def test_material_challenge_concern_routes_to_not_ready(self):
        _, _, execution = self.start(provider=FakeProvider(challenge_status="concern"), execution_id="assessment-concern")
        self.assertEqual("completed", execution.status)
        self.assertEqual("evidence_not_ready", execution.state["assessment_record"]["status"])
        self.assertTrue(execution.state["evidence_assurance"]["blocking_reasons"])

    def test_review_action_recommendation_routes_to_learner_action(self):
        _, _, execution = self.start(provider=FakeProvider(review_status="action_recommended"), execution_id="assessment-review-action")
        self.assertEqual("learner_action_required", execution.state["assessment_record"]["status"])

    def test_extra_assessment_capability_fails_assurance(self):
        _, _, execution = self.start(provider=FakeProvider(extra_finding=True), execution_id="assessment-extra-finding")
        self.assertEqual("evidence_not_ready", execution.state["assessment_record"]["status"])
        self.assertTrue(any("outside the mission requirements" in item for item in execution.state["evidence_assurance"]["blocking_reasons"]))

    def test_agent_nodes_are_a1_and_acceptance_is_a3_human(self):
        definition = LearnerAssessmentGraph.definition()
        agents = [node for node in definition.nodes if node.actor.kind == "agent"]
        self.assertEqual(3, len(agents))
        self.assertTrue(all(node.actor.authority == "A1" for node in agents))
        human = next(node for node in definition.nodes if node.node_id == "capability_evidence_review")
        self.assertEqual("human", human.actor.kind)
        self.assertEqual("A3", human.actor.authority)


if __name__ == "__main__":
    unittest.main()
