from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from runtime.graph_execution_store import GraphExecutionStore
from runtime.learner_execution_runner import start_learner_assessment
from runtime.learner_progress_store import LearnerProgressStore
from runtime.test_learner_execution_graph import FakeLearnerProvider
from runtime.test_learner_progress_store import build_learning_fixture


class LearnerStateIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _, self.capabilities, self.learning, self.path = build_learning_fixture(self.root)
        self.progress = LearnerProgressStore(self.root / "learner.sqlite3")
        self.instance = self.progress.assign_active_path(
            learning_store=self.learning,
            instance_id="learner-integrity-001",
            learner_ref="learner-ref-integrity-001",
            cohort_id="cohort-integrity-001",
            pathway_id="applied-ai-systems",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def advance_and_submit(self, submission_id="submission-integrity-001"):
        self.progress.start_unit(self.instance["instance_id"], "agent-foundations-sprint")
        self.progress.complete_practice_unit(self.instance["instance_id"], "agent-foundations-sprint")
        self.progress.start_unit(self.instance["instance_id"], "agent-control-lab")
        self.progress.complete_practice_unit(self.instance["instance_id"], "agent-control-lab")
        return self.progress.record_mission_submission(
            submission_id=submission_id,
            instance_id=self.instance["instance_id"],
            unit_id="supplier-agent-mission",
            artifact_refs=("artifact://evaluation-report",),
            artifact_types=("evaluation_report",),
            revision_ref="artifact://revision",
            defense_response_ref="artifact://defense",
            changed_scenario_response_ref="artifact://changed",
        )

    def test_existing_instance_cannot_be_rebound_to_another_learner(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.progress.assign_active_path(
                learning_store=self.learning,
                instance_id=self.instance["instance_id"],
                learner_ref="different-learner-ref-001",
                cohort_id="cohort-integrity-001",
                pathway_id="applied-ai-systems",
            )

    def test_assigned_path_remains_frozen_after_new_active_learning_version(self):
        self.learning.retire(
            "applied-ai-systems",
            "0.1.0",
            approver_id="curriculum-accountable-person",
            note="Replace with reviewed second version.",
        )
        second = replace(self.path, version="0.2.0")
        self.learning.save_candidate(second, capabilities=self.capabilities)
        self.learning.activate(
            second.pathway_id,
            second.version,
            approver_id="curriculum-accountable-person",
            note="Activate reviewed second version.",
        )
        stored = self.progress.get_instance(self.instance["instance_id"])
        self.assertEqual("0.1.0", stored["learning_version"])
        self.assertEqual("0.1.0", stored["path_snapshot"]["version"])

    def test_reused_submission_id_must_match_original_submission(self):
        submission = self.advance_and_submit()
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.progress.record_mission_submission(
                submission_id=submission["submission_id"],
                instance_id=self.instance["instance_id"],
                unit_id="supplier-agent-mission",
                artifact_refs=("artifact://different-report",),
                artifact_types=("evaluation_report",),
                revision_ref="artifact://revision",
                defense_response_ref="artifact://defense",
                changed_scenario_response_ref="artifact://changed",
            )

    def test_fresh_assessment_cannot_start_twice_for_same_submission(self):
        submission = self.advance_and_submit("submission-integrity-assess")
        store = GraphExecutionStore(self.root / "assessment.sqlite3")
        start_learner_assessment(
            provider=FakeLearnerProvider(),
            execution_store=store,
            progress_store=self.progress,
            capability_store=self.capabilities,
            execution_id="assessment-integrity-001",
            submission_id=submission["submission_id"],
        )
        with self.assertRaisesRegex(ValueError, "newly submitted"):
            start_learner_assessment(
                provider=FakeLearnerProvider(),
                execution_store=store,
                progress_store=self.progress,
                capability_store=self.capabilities,
                execution_id="assessment-integrity-002",
                submission_id=submission["submission_id"],
            )

    def test_path_completion_event_follows_evidence_acceptance_event(self):
        submission = self.advance_and_submit("submission-integrity-events")
        self.progress.set_submission_assessment_state(
            submission["submission_id"],
            status="human_review",
            assessment_execution_id="assessment-integrity-events",
        )
        self.progress.accept_mission_evidence(
            submission["submission_id"],
            assessment_execution_id="assessment-integrity-events",
            accepted_by="assessment-accountable-person",
            note="Reviewed evidence and assessment record.",
        )
        event_types = [event["event_type"] for event in self.progress.events(self.instance["instance_id"])]
        self.assertLess(
            event_types.index("learner.capability_evidence_accepted.v1"),
            event_types.index("learner.path_completed.v1"),
        )


if __name__ == "__main__":
    unittest.main()
