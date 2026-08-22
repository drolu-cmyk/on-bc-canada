from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.career_intelligence import CareerIntelligenceBuilder
from runtime.learner_progress_store import LearnerProgressStore
from runtime.test_learner_progress_store import build_learning_fixture


def build_career_fixture(root: Path):
    work, capabilities, learning, _ = build_learning_fixture(root)
    learner = LearnerProgressStore(root / "learner.sqlite3")
    instance = learner.assign_active_path(
        learning_store=learning,
        instance_id="learner-career-001",
        learner_ref="learner-ref-career-001",
        cohort_id="cohort-career-001",
        pathway_id="applied-ai-systems",
    )
    learner.start_unit(instance["instance_id"], "agent-foundations-sprint")
    learner.complete_practice_unit(instance["instance_id"], "agent-foundations-sprint")
    learner.start_unit(instance["instance_id"], "agent-control-lab")
    learner.complete_practice_unit(instance["instance_id"], "agent-control-lab")
    submission = learner.record_mission_submission(
        submission_id="submission-career-001",
        instance_id=instance["instance_id"],
        unit_id="supplier-agent-mission",
        artifact_refs=("artifact://career/evaluation-report",),
        artifact_types=("evaluation_report",),
        revision_ref="artifact://career/revision",
        defense_response_ref="artifact://career/defense",
        changed_scenario_response_ref="artifact://career/changed",
    )
    learner.set_submission_assessment_state(
        submission["submission_id"],
        status="human_review",
        assessment_execution_id="assessment-career-001",
    )
    learner.accept_mission_evidence(
        submission["submission_id"],
        assessment_execution_id="assessment-career-001",
        accepted_by="assessment-accountable-person",
        note="Reviewed raw mission evidence against both capability standards.",
    )
    return work, capabilities, learner, instance, submission


class CareerIntelligenceBuilderTests(unittest.TestCase):
    def test_context_uses_only_human_accepted_capabilities_and_work_roles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, capabilities, learner, instance, _ = build_career_fixture(root)
            context = CareerIntelligenceBuilder(
                learner_store=learner,
                capability_store=capabilities,
                work_store=work,
            ).build(instance["instance_id"])

            self.assertEqual("applied-ai-systems", context.pathway_id)
            self.assertEqual(2, len(context.accepted_capabilities))
            self.assertEqual(
                {"agent-evaluation", "tool-permission-design"},
                {item.capability_id for item in context.accepted_capabilities},
            )
            self.assertEqual(
                {"Applied AI Developer", "Agentic AI Engineer"},
                {item.role_name for item in context.role_alignments},
            )
            self.assertTrue(all(item.evidence_alignment == 1.0 for item in context.role_alignments))
            self.assertTrue(all(item.relation_ids for item in context.role_alignments))
            self.assertTrue(all(item.research_execution_ids for item in context.role_alignments))

    def test_context_payload_excludes_identity_and_raw_artifact_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, capabilities, learner, instance, submission = build_career_fixture(root)
            payload = CareerIntelligenceBuilder(
                learner_store=learner,
                capability_store=capabilities,
                work_store=work,
            ).build(instance["instance_id"]).as_payload()
            serialized = repr(payload)
            for private_value in (
                instance["instance_id"],
                instance["learner_ref"],
                instance["cohort_id"],
                submission["submission_id"],
                *submission["artifact_refs"],
                submission["revision_ref"],
                submission["defense_response_ref"],
                submission["changed_scenario_response_ref"],
                "assessment-accountable-person",
            ):
                self.assertNotIn(private_value, serialized)
            self.assertIn("Agent evaluation", serialized)
            self.assertIn("Applied AI Developer", serialized)

    def test_context_requires_human_accepted_capability_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, capabilities, learning, _ = build_learning_fixture(root)
            learner = LearnerProgressStore(root / "learner.sqlite3")
            instance = learner.assign_active_path(
                learning_store=learning,
                instance_id="learner-career-empty-001",
                learner_ref="learner-ref-career-empty-001",
                cohort_id="cohort-career-empty-001",
                pathway_id="applied-ai-systems",
            )
            with self.assertRaisesRegex(ValueError, "human-accepted"):
                CareerIntelligenceBuilder(
                    learner_store=learner,
                    capability_store=capabilities,
                    work_store=work,
                ).build(instance["instance_id"])


if __name__ == "__main__":
    unittest.main()
