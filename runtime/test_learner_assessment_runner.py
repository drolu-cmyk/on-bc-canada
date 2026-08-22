from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.graph_execution_store import GraphExecutionStore
from runtime.learner_assessment_runner import resume_learner_assessment, start_learner_assessment
from runtime.learner_progress_store import LearnerProgressStore
from runtime.test_learner_assessment_graph import FakeProvider
from runtime.test_learner_progress_store import build_learning_fixture


class RaisingProvider:
    def normalize(self, request):
        raise AssertionError("resume must not rerun normalize")

    def review_submission(self, request):
        raise AssertionError("resume must not rerun review")

    def assess_evidence(self, request, review):
        raise AssertionError("resume must not rerun assessment")

    def challenge_assessment(self, request, review, assessment):
        raise AssertionError("resume must not rerun challenge")


class LearnerAssessmentRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _, self.capabilities, self.learning, _ = build_learning_fixture(self.root)
        self.progress = LearnerProgressStore(self.root / "learner.sqlite3")
        self.assessments = GraphExecutionStore(self.root / "assessment.sqlite3")
        self.instance = self.progress.assign_active_path(
            learning_store=self.learning,
            instance_id="learner-path-runner-001",
            learner_ref="learner-ref-runner-001",
            cohort_id="cohort-runner-001",
            pathway_id="applied-ai-systems",
        )
        self.progress.start_unit(self.instance["instance_id"], "agent-foundations-sprint")
        self.progress.complete_practice_unit(self.instance["instance_id"], "agent-foundations-sprint")
        self.progress.start_unit(self.instance["instance_id"], "agent-control-lab")
        self.progress.complete_practice_unit(self.instance["instance_id"], "agent-control-lab")

    def tearDown(self):
        self.tmp.cleanup()

    def submit(self, submission_id="submission-runner-001", *, revision=True):
        return self.progress.record_mission_submission(
            submission_id=submission_id,
            instance_id=self.instance["instance_id"],
            unit_id="supplier-agent-mission",
            artifact_refs=("artifact://evaluation-report",),
            artifact_types=("evaluation_report",),
            revision_ref="artifact://revision" if revision else None,
            defense_response_ref="artifact://defense",
            changed_scenario_response_ref="artifact://changed",
        )

    def test_passing_assessment_survives_restart_and_accepts_evidence_after_a3(self):
        submission = self.submit()
        execution = start_learner_assessment(
            provider=FakeProvider(),
            execution_store=self.assessments,
            progress_store=self.progress,
            capability_store=self.capabilities,
            execution_id="assessment-runner-001",
            submission_id=submission["submission_id"],
            evidence_material=[
                {"evidence_ref": "artifact://evaluation-report", "summary": "Agent evaluation and permission evidence."}
            ],
        )
        self.assertEqual("waiting_approval", execution.status)
        self.assertEqual("human_review", self.progress.get_submission(submission["submission_id"])["status"])
        ledger = self.assessments.load_execution(execution.execution_id)[1]
        self.assertTrue(all(event["privacy_class"] == "learner_private" for event in ledger.events))
        self.assertTrue(all(event["learner_id"] == "learner-ref-runner-001" for event in ledger.events))

        completed = resume_learner_assessment(
            provider=RaisingProvider(),
            execution_store=GraphExecutionStore(self.root / "assessment.sqlite3"),
            progress_store=LearnerProgressStore(self.root / "learner.sqlite3"),
            execution_id=execution.execution_id,
            approved=True,
            approver_id="assessment-accountable-person",
            note="Reviewed assessment, learner evidence, and challenge result.",
        )
        self.assertEqual("completed", completed.status)
        stored_submission = self.progress.get_submission(submission["submission_id"])
        self.assertEqual("accepted", stored_submission["status"])
        self.assertEqual("completed", self.progress.get_unit(self.instance["instance_id"], "supplier-agent-mission")["status"])
        self.assertEqual("completed", self.progress.get_instance(self.instance["instance_id"])["status"])
        self.assertEqual(2, len(self.progress.accepted_capability_evidence(self.instance["instance_id"])))
        terminal = self.assessments.get_terminal_record(execution.execution_id, "assessment_record")
        self.assertEqual("accepted_capability_evidence", terminal["status"])

    def test_human_denial_rejects_submission_without_accepting_capability_evidence(self):
        submission = self.submit("submission-runner-deny")
        execution = start_learner_assessment(
            provider=FakeProvider(),
            execution_store=self.assessments,
            progress_store=self.progress,
            capability_store=self.capabilities,
            execution_id="assessment-runner-deny",
            submission_id=submission["submission_id"],
            evidence_material=[],
        )
        denied = resume_learner_assessment(
            provider=RaisingProvider(),
            execution_store=self.assessments,
            progress_store=self.progress,
            execution_id=execution.execution_id,
            approved=False,
            approver_id="assessment-accountable-person",
            note="Evidence does not support acceptance after human review.",
        )
        self.assertEqual("failed", denied.status)
        self.assertEqual("rejected", self.progress.get_submission(submission["submission_id"])["status"])
        self.assertEqual([], self.progress.accepted_capability_evidence(self.instance["instance_id"]))

    def test_missing_required_revision_returns_learner_action_and_syncs_submission(self):
        submission = self.submit("submission-runner-action", revision=False)
        execution = start_learner_assessment(
            provider=FakeProvider(),
            execution_store=self.assessments,
            progress_store=self.progress,
            capability_store=self.capabilities,
            execution_id="assessment-runner-action",
            submission_id=submission["submission_id"],
            evidence_material=[],
        )
        self.assertEqual("completed", execution.status)
        self.assertEqual("learner_action_required", execution.state["assessment_record"]["status"])
        self.assertEqual("learner_action_required", self.progress.get_submission(submission["submission_id"])["status"])
        terminal = self.assessments.get_terminal_record(execution.execution_id, "assessment_record")
        self.assertEqual("learner_action_required", terminal["status"])


if __name__ == "__main__":
    unittest.main()
