from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.career_mobility_runner import start_career_mobility
from runtime.graph_execution_store import GraphExecutionStore
from runtime.test_career_intelligence import build_career_fixture


class FakeCareerProvider:
    def __init__(self):
        self.contexts = []
        self.calls = []

    def _capture(self, name, context):
        payload = context.as_payload()
        self.calls.append(name)
        self.contexts.append(payload)
        return payload

    def profile(self, context):
        payload = self._capture("profile", context)
        return {
            "positioning_summary": "Demonstrated capability evidence in bounded agent evaluation and tool-permission design.",
            "demonstrated_capabilities": [
                {
                    "capability_id": item["capability_id"],
                    "statement": f"Can discuss and defend {item['capability_name'].lower()} at the reviewed target level.",
                    "evidence_boundary": "Based on a human-accepted capability evidence record; raw artifact content was not provided to this agent.",
                }
                for item in payload["accepted_capabilities"]
            ],
            "boundary_notes": ["This is evidence positioning, not an employment claim."],
        }

    def analyze_role_transitions(self, context):
        payload = self._capture("roles", context)
        return {
            "roles": [
                {
                    "role_name": item["role_name"],
                    "evidence_based_strengths": list(item["matched_capabilities"]),
                    "capability_gaps": list(item["missing_capabilities"]),
                    "interpretation": "Evidence alignment describes overlap with research-backed capability relationships, not hiring likelihood.",
                }
                for item in payload["role_alignments"]
            ],
            "note": "Role analysis is learner-facing and does not rank candidates for employers.",
        }

    def package_evidence(self, context):
        payload = self._capture("evidence", context)
        return {
            "cards": [
                {
                    "capability_id": item["capability_id"],
                    "standard_id": item["standard_id"],
                    "label": item["capability_name"],
                    "proof_prompt": "Explain the problem, your decision, the evidence standard, tradeoffs, revision, and what changed under critique.",
                }
                for item in payload["accepted_capabilities"]
            ],
            "portfolio_structure": ["Problem", "Decision", "Evidence", "Tradeoffs", "Revision", "Reflection"],
            "note": "Learner supplies the actual artifact and claims.",
        }

    def prepare_interview_practice(self, context):
        payload = self._capture("interview", context)
        capability_ids = [item["capability_id"] for item in payload["accepted_capabilities"]]
        return {
            "questions": [
                {
                    "role_name": role["role_name"],
                    "question": "Describe a bounded agent decision, the failure conditions you tested, and how human authority affected the design.",
                    "capability_ids": capability_ids,
                    "what_to_demonstrate": "Reasoning, evidence traceability, failure handling, and accountable boundaries.",
                }
                for role in payload["role_alignments"]
            ],
            "practice_method": "Answer from your actual accepted evidence, then challenge the answer with a changed scenario.",
        }

    def plan_actions(self, context):
        payload = self._capture("actions", context)
        role_names = [item["role_name"] for item in payload["role_alignments"]]
        capability_ids = [item["capability_id"] for item in payload["accepted_capabilities"]]
        return {
            "actions": [
                {
                    "action_type": "portfolio_preparation",
                    "action": "Prepare a concise evidence card for each accepted capability without adding claims not supported by your work.",
                    "related_role_names": role_names,
                    "related_capability_ids": capability_ids,
                },
                {
                    "action_type": "interview_practice",
                    "action": "Practice defending one technical decision and one failure condition from the accepted capability evidence.",
                    "related_role_names": role_names,
                    "related_capability_ids": capability_ids,
                },
            ],
            "sequencing_note": "Evidence clarity before broader employer research.",
            "boundary_note": "No job application, employer contact, or external publication is executed here.",
        }


class UnknownRoleProvider(FakeCareerProvider):
    def analyze_role_transitions(self, context):
        self._capture("roles", context)
        return {
            "roles": [
                {
                    "role_name": "Chief Autonomous Officer",
                    "evidence_based_strengths": [],
                    "capability_gaps": [],
                    "interpretation": "Invented role fixture.",
                }
            ],
            "note": "fixture",
        }


class CareerMobilityGraphTests(unittest.TestCase):
    def test_guidance_uses_accepted_evidence_and_persists_learner_private_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, capabilities, learner, instance, submission = build_career_fixture(root)
            executions = GraphExecutionStore(root / "graph.sqlite3")
            provider = FakeCareerProvider()
            execution = start_career_mobility(
                provider=provider,
                learner_store=learner,
                capability_store=capabilities,
                work_store=work,
                execution_store=executions,
                execution_id="career-guidance-001",
                instance_id=instance["instance_id"],
            )

            self.assertEqual("completed", execution.status)
            self.assertEqual("guidance_ready", execution.state["career_status"])
            self.assertEqual(5, len(provider.calls))
            packet = execution.state["career_packet"]
            self.assertFalse(packet["assurance"]["external_action_authorized"])
            self.assertFalse(packet["assurance"]["employer_decision_authorized"])
            self.assertFalse(packet["assurance"]["hiring_prediction_authorized"])
            self.assertEqual(
                {"Applied AI Developer", "Agentic AI Engineer"},
                {item["role_name"] for item in packet["role_alignments"]},
            )

            stored = executions.get_terminal_record(execution.execution_id, "career_guidance")
            self.assertEqual("applied-ai-systems", stored["pathway_id"])
            _, ledger = executions.load_execution(execution.execution_id)
            self.assertTrue(all(event["privacy_class"] == "learner_private" for event in ledger.events))
            self.assertTrue(all(event["learner_id"] == instance["learner_ref"] for event in ledger.events))

            serialized_model_context = repr(provider.contexts)
            for private_value in (
                instance["instance_id"],
                instance["learner_ref"],
                instance["cohort_id"],
                submission["submission_id"],
                *submission["artifact_refs"],
                "assessment-accountable-person",
            ):
                self.assertNotIn(private_value, serialized_model_context)

    def test_unknown_role_from_agent_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, capabilities, learner, instance, _ = build_career_fixture(root)
            executions = GraphExecutionStore(root / "graph.sqlite3")
            execution = start_career_mobility(
                provider=UnknownRoleProvider(),
                learner_store=learner,
                capability_store=capabilities,
                work_store=work,
                execution_store=executions,
                execution_id="career-unknown-role-001",
                instance_id=instance["instance_id"],
            )
            self.assertEqual("failed", execution.status)
            self.assertIn("unknown or duplicate role", execution.failure)

    def test_no_accepted_evidence_fails_before_agent_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            from runtime.learner_progress_store import LearnerProgressStore
            from runtime.test_learner_progress_store import build_learning_fixture

            work, capabilities, learning, _ = build_learning_fixture(root)
            learner = LearnerProgressStore(root / "learner.sqlite3")
            instance = learner.assign_active_path(
                learning_store=learning,
                instance_id="learner-career-no-evidence-001",
                learner_ref="learner-ref-career-no-evidence-001",
                cohort_id="cohort-career-no-evidence-001",
                pathway_id="applied-ai-systems",
            )
            provider = FakeCareerProvider()
            execution = start_career_mobility(
                provider=provider,
                learner_store=learner,
                capability_store=capabilities,
                work_store=work,
                execution_store=GraphExecutionStore(root / "graph.sqlite3"),
                execution_id="career-no-evidence-001",
                instance_id=instance["instance_id"],
            )
            self.assertEqual("failed", execution.status)
            self.assertIn("human-accepted", execution.failure)
            self.assertEqual([], provider.calls)


if __name__ == "__main__":
    unittest.main()
