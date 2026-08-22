from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.graph_execution_store import GraphExecutionStore
from runtime.learner_execution_runner import resume_learner_assessment, start_learner_assessment
from runtime.learner_progress_store import LearnerProgressStore
from runtime.test_learner_progress_store import build_learning_fixture


class FakeLearnerProvider:
    def __init__(self):
        self.contexts = []
        self.calls = []

    def _capture(self, name, context):
        payload = context.as_payload()
        self.calls.append(name)
        self.contexts.append(payload)
        return payload

    def coach(self, context):
        self._capture("coach", context)
        return {
            "focus": "Prepare evidence against the supplied standards.",
            "next_actions": ["Address every missing readiness element."],
            "questions_for_learner": ["What evidence best demonstrates the required decision?"],
            "note": "This guidance does not assess submission content.",
        }

    def analyze_progress(self, context):
        payload = self._capture("progress", context)
        return {
            "status": "ready_for_review" if payload["readiness_complete"] else "needs_iteration",
            "rationale": "Based only on deidentified readiness metadata.",
            "recommended_next_step": "Human review" if payload["readiness_complete"] else "Complete missing evidence elements",
            "signals": ["attempt metadata reviewed"],
        }

    def prepare_human_review(self, context):
        payload = self._capture("review", context)
        return {
            "summary": "Human assessor should inspect the raw evidence against each reviewed standard.",
            "checklist": [
                {
                    "capability_id": item["capability_id"],
                    "standard_id": item["standard_id"],
                    "review_question": f"Does the raw evidence satisfy {item['standard_description']}?",
                }
                for item in payload["readiness_requirements"]
            ],
            "reviewer_cautions": ["Do not substitute metadata readiness for substantive evidence review."],
        }


class LearnerExecutionGraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.work, self.capabilities, self.learning, _ = build_learning_fixture(self.root)
        self.progress = LearnerProgressStore(self.root / "learner.sqlite3")
        self.instance = self.progress.assign_active_path(
            learning_store=self.learning,
            instance_id="learner-path-001",
            learner_ref="learner-ref-001",
            cohort_id="cohort-001",
            pathway_id="applied-ai-systems",
        )
        self.execution_store = GraphExecutionStore(self.root / "graph.sqlite3")
        self.provider = FakeLearnerProvider()
        self._advance_to_mission()

    def tearDown(self):
        self.tmp.cleanup()

    def _advance_to_mission(self):
        self.progress.start_unit(self.instance["instance_id"], "agent-foundations-sprint")
        self.progress.complete_practice_unit(self.instance["instance_id"], "agent-foundations-sprint")
        self.progress.start_unit(self.instance["instance_id"], "agent-control-lab")
        self.progress.complete_practice_unit(self.instance["instance_id"], "agent-control-lab")

    def _submit(self, submission_id: str, *, complete: bool):
        return self.progress.record_mission_submission(
            submission_id=submission_id,
            instance_id=self.instance["instance_id"],
            unit_id="supplier-agent-mission",
            artifact_refs=(f"artifact://{submission_id}/report",),
            artifact_types=("evaluation_report",),
            revision_ref=f"artifact://{submission_id}/revision" if complete else None,
            defense_response_ref=f"artifact://{submission_id}/defense" if complete else None,
            changed_scenario_response_ref=f"artifact://{submission_id}/changed" if complete else None,
        )

    def test_incomplete_metadata_routes_to_learner_action_without_human_gate(self):
        submission = self._submit("submission-incomplete-001", complete=False)
        execution = start_learner_assessment(
            provider=self.provider,
            progress_store=self.progress,
            capability_store=self.capabilities,
            execution_store=self.execution_store,
            execution_id="assessment-incomplete-001",
            submission_id=submission["submission_id"],
        )
        self.assertEqual("completed", execution.status)
        self.assertEqual("learner_action_required", execution.state["assessment_status"])
        self.assertEqual("learner_action_required", self.progress.get_submission(submission["submission_id"])["status"])
        self.assertNotIn("human_decisions", execution.state)
        self.assertEqual(3, len(self.provider.calls))

    def test_ready_submission_stops_for_human_review(self):
        submission = self._submit("submission-ready-001", complete=True)
        execution = start_learner_assessment(
            provider=self.provider,
            progress_store=self.progress,
            capability_store=self.capabilities,
            execution_store=self.execution_store,
            execution_id="assessment-ready-001",
            submission_id=submission["submission_id"],
        )
        self.assertEqual("waiting_approval", execution.status)
        self.assertEqual("human_assessment", execution.current_node)
        self.assertEqual("A3", execution.pending_approval["authority"])
        self.assertEqual("human_review", self.progress.get_submission(submission["submission_id"])["status"])

    def test_human_acceptance_records_capability_evidence_and_completes_path(self):
        submission = self._submit("submission-accept-graph-001", complete=True)
        execution = start_learner_assessment(
            provider=self.provider,
            progress_store=self.progress,
            capability_store=self.capabilities,
            execution_store=self.execution_store,
            execution_id="assessment-accept-001",
            submission_id=submission["submission_id"],
        )
        call_count = len(self.provider.calls)
        execution = resume_learner_assessment(
            provider=self.provider,
            progress_store=self.progress,
            capability_store=self.capabilities,
            execution_store=self.execution_store,
            execution_id=execution.execution_id,
            accepted=True,
            reviewer_id="assessment-accountable-person",
            note="Reviewed the raw evidence against both standards.",
        )
        self.assertEqual("completed", execution.status)
        self.assertEqual("accepted", execution.state["assessment_status"])
        self.assertEqual(call_count, len(self.provider.calls), "resume must not rerun learner agents")
        self.assertEqual("accepted", self.progress.get_submission(submission["submission_id"])["status"])
        self.assertEqual("completed", self.progress.get_instance(self.instance["instance_id"])["status"])
        self.assertEqual(2, len(self.progress.accepted_capability_evidence(self.instance["instance_id"])))
        terminal = self.execution_store.get_terminal_record(execution.execution_id, "learner_assessment")
        self.assertEqual("accepted", terminal["status"])

    def test_human_nonacceptance_routes_to_revision_not_graph_failure(self):
        submission = self._submit("submission-revise-graph-001", complete=True)
        execution = start_learner_assessment(
            provider=self.provider,
            progress_store=self.progress,
            capability_store=self.capabilities,
            execution_store=self.execution_store,
            execution_id="assessment-revise-001",
            submission_id=submission["submission_id"],
        )
        execution = resume_learner_assessment(
            provider=self.provider,
            progress_store=self.progress,
            capability_store=self.capabilities,
            execution_store=self.execution_store,
            execution_id=execution.execution_id,
            accepted=False,
            reviewer_id="assessment-accountable-person",
            note="The raw evidence does not yet demonstrate the required decisions.",
        )
        self.assertEqual("completed", execution.status)
        self.assertEqual("revision_required", execution.state["assessment_status"])
        self.assertIsNone(execution.failure)
        self.assertEqual("rejected", self.progress.get_submission(submission["submission_id"])["status"])

    def test_agent_context_excludes_identity_and_raw_evidence_references(self):
        submission = self._submit("submission-private-001", complete=True)
        start_learner_assessment(
            provider=self.provider,
            progress_store=self.progress,
            capability_store=self.capabilities,
            execution_store=self.execution_store,
            execution_id="assessment-private-001",
            submission_id=submission["submission_id"],
        )
        serialized = repr(self.provider.contexts)
        forbidden_values = [
            self.instance["learner_ref"],
            self.instance["cohort_id"],
            submission["submission_id"],
            *submission["artifact_refs"],
            submission["revision_ref"],
            submission["defense_response_ref"],
            submission["changed_scenario_response_ref"],
        ]
        for value in forbidden_values:
            self.assertNotIn(value, serialized)
        self.assertIn("evaluation_report", serialized)
        self.assertIn("agent-evaluation-proof", serialized)

    def test_resume_requires_named_reviewer_and_note(self):
        submission = self._submit("submission-review-note-001", complete=True)
        execution = start_learner_assessment(
            provider=self.provider,
            progress_store=self.progress,
            capability_store=self.capabilities,
            execution_store=self.execution_store,
            execution_id="assessment-review-note-001",
            submission_id=submission["submission_id"],
        )
        with self.assertRaisesRegex(ValueError, "review note"):
            resume_learner_assessment(
                provider=self.provider,
                progress_store=self.progress,
                capability_store=self.capabilities,
                execution_store=self.execution_store,
                execution_id=execution.execution_id,
                accepted=True,
                reviewer_id="assessment-accountable-person",
                note="",
            )


if __name__ == "__main__":
    unittest.main()
