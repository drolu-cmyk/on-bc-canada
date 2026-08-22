from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.graph_execution_store import GraphExecutionStore
from runtime.learner_execution_runner import start_learner_assessment
from runtime.learner_progress_store import LearnerProgressStore
from runtime.test_learner_progress_store import build_learning_fixture


class FailingProvider:
    def coach(self, context):
        raise RuntimeError("simulated model or runtime failure")

    def analyze_progress(self, context):
        raise AssertionError("progress must not run after coaching failure")

    def prepare_human_review(self, context):
        raise AssertionError("review preparation must not run after coaching failure")


class LearnerAssessmentFailureRecoveryTests(unittest.TestCase):
    def test_runtime_failure_returns_submission_to_retryable_state_and_preserves_failed_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, capabilities, learning, _ = build_learning_fixture(root)
            progress = LearnerProgressStore(root / "learner.sqlite3")
            assessments = GraphExecutionStore(root / "assessment.sqlite3")
            instance = progress.assign_active_path(
                learning_store=learning,
                instance_id="learner-failure-001",
                learner_ref="learner-ref-failure-001",
                cohort_id="cohort-failure-001",
                pathway_id="applied-ai-systems",
            )
            progress.start_unit(instance["instance_id"], "agent-foundations-sprint")
            progress.complete_practice_unit(instance["instance_id"], "agent-foundations-sprint")
            progress.start_unit(instance["instance_id"], "agent-control-lab")
            progress.complete_practice_unit(instance["instance_id"], "agent-control-lab")
            submission = progress.record_mission_submission(
                submission_id="submission-failure-001",
                instance_id=instance["instance_id"],
                unit_id="supplier-agent-mission",
                artifact_refs=("artifact://evaluation-report",),
                artifact_types=("evaluation_report",),
                revision_ref="artifact://revision",
                defense_response_ref="artifact://defense",
                changed_scenario_response_ref="artifact://changed",
            )

            execution = start_learner_assessment(
                provider=FailingProvider(),
                execution_store=assessments,
                progress_store=progress,
                capability_store=capabilities,
                execution_id="assessment-failure-001",
                submission_id=submission["submission_id"],
            )

            self.assertEqual("failed", execution.status)
            self.assertIn("simulated model or runtime failure", execution.failure)
            self.assertEqual("submitted", progress.get_submission(submission["submission_id"])["status"])

            persisted, ledger = assessments.load_execution(execution.execution_id)
            self.assertEqual("failed", persisted.status)
            self.assertIn("simulated model or runtime failure", persisted.failure)
            self.assertTrue(any(event["event_type"] == "graph.execution_failed.v1" for event in ledger.events))
            self.assertTrue(all(event["privacy_class"] == "learner_private" for event in ledger.events))


if __name__ == "__main__":
    unittest.main()
