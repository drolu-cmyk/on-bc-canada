from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.capability_graph import CapabilityGraphStore
from runtime.learner_progress_store import LearnerProgressStore
from runtime.learning_graph import EvidenceRequirement, LearningGraphStore, LearningPathDefinition, LearningUnit
from runtime.test_capability_graph import completed_execution, standard
from runtime.work_intelligence import WorkIntelligenceStore


def build_learning_fixture(root: Path):
    work = WorkIntelligenceStore(root / "work.sqlite3")
    capabilities = CapabilityGraphStore(root / "capabilities.sqlite3")
    learning = LearningGraphStore(root / "learning.sqlite3")
    work.ingest_research_execution(
        completed_execution(),
        pathway_id="applied-ai-systems",
        pathway_name="Applied AI Systems",
    )
    first = capabilities.draft_from_work_intelligence(
        work_store=work,
        pathway_id="applied-ai-systems",
        pathway_name="Applied AI Systems",
        capability_id="agent-evaluation",
        capability_name="Agent evaluation",
        description="Evaluate bounded agent behaviour against explicit tasks, evidence criteria, and failure conditions.",
        target_level="evaluate",
        evidence_standards=(standard("agent-evaluation-proof"),),
    )
    capabilities.activate(first.capability_id, approver_id="curriculum-accountable-person")
    second = capabilities.draft_from_work_intelligence(
        work_store=work,
        pathway_id="applied-ai-systems",
        pathway_name="Applied AI Systems",
        capability_id="tool-permission-design",
        capability_name="Tool permission design",
        description="Design bounded tool permissions for agent actions according to risk and accountable decision authority.",
        target_level="design",
        evidence_standards=(standard("tool-permission-proof"),),
        prerequisite_ids=(first.capability_id,),
    )
    capabilities.activate(second.capability_id, approver_id="curriculum-accountable-person")

    sprint = LearningUnit(
        unit_id="agent-foundations-sprint",
        kind="sprint",
        title="Agent evaluation foundations",
        purpose="Build the reasoning needed to define tasks, failure conditions, and evidence boundaries.",
        develops_capability_ids=(first.capability_id,),
        source_module_ids=("AAI-101",),
    )
    lab = LearningUnit(
        unit_id="agent-control-lab",
        kind="lab",
        title="Agent control lab",
        purpose="Practise evaluation and permission decisions in a bounded synthetic agent environment.",
        develops_capability_ids=(first.capability_id, second.capability_id),
        prerequisite_unit_ids=(sprint.unit_id,),
        source_module_ids=("AAI-101", "AAI-102"),
    )
    mission = LearningUnit(
        unit_id="supplier-agent-mission",
        kind="mission",
        title="Supplier review agent mission",
        purpose="Evaluate and constrain a supplier-review agent, defend the design, and respond to a changed scenario.",
        develops_capability_ids=(first.capability_id, second.capability_id),
        evidence_requirements=(
            EvidenceRequirement(first.capability_id, "agent-evaluation-proof"),
            EvidenceRequirement(second.capability_id, "tool-permission-proof"),
        ),
        prerequisite_unit_ids=(lab.unit_id,),
        source_module_ids=("AAI-102",),
    )
    path = LearningPathDefinition(
        pathway_id="applied-ai-systems",
        version="0.1.0",
        title="Applied AI Systems capability path",
        target_capability_ids=(first.capability_id, second.capability_id),
        units=(mission, lab, sprint),
    )
    learning.save_candidate(path, capabilities=capabilities)
    learning.activate(
        path.pathway_id,
        path.version,
        approver_id="curriculum-accountable-person",
        note="Reviewed sequence and evidence coverage.",
    )
    return work, capabilities, learning, path


class LearnerProgressStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.work, self.capabilities, self.learning, self.path = build_learning_fixture(self.root)
        self.progress = LearnerProgressStore(self.root / "learner.sqlite3")
        self.instance = self.progress.assign_active_path(
            learning_store=self.learning,
            instance_id="learner-path-001",
            learner_ref="learner-ref-001",
            cohort_id="cohort-001",
            pathway_id="applied-ai-systems",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def advance_to_mission(self):
        self.progress.start_unit(self.instance["instance_id"], "agent-foundations-sprint")
        self.progress.complete_practice_unit(
            self.instance["instance_id"],
            "agent-foundations-sprint",
            evidence_refs=("artifact://sprint-notes",),
        )
        self.progress.start_unit(self.instance["instance_id"], "agent-control-lab")
        self.progress.complete_practice_unit(
            self.instance["instance_id"],
            "agent-control-lab",
            evidence_refs=("artifact://lab-notebook",),
        )

    def test_assignment_freezes_reviewed_learning_path_version(self):
        self.assertEqual("0.1.0", self.instance["learning_version"])
        self.assertEqual("0.1.0", self.instance["path_snapshot"]["version"])
        statuses = {item["unit_id"]: item["status"] for item in self.instance["units"]}
        self.assertEqual("available", statuses["agent-foundations-sprint"])
        self.assertEqual("locked", statuses["agent-control-lab"])
        self.assertEqual("locked", statuses["supplier-agent-mission"])

    def test_practice_completion_unlocks_graph_dependencies(self):
        self.advance_to_mission()
        statuses = {item["unit_id"]: item["status"] for item in self.progress.get_instance(self.instance["instance_id"])["units"]}
        self.assertEqual("completed", statuses["agent-foundations-sprint"])
        self.assertEqual("completed", statuses["agent-control-lab"])
        self.assertEqual("available", statuses["supplier-agent-mission"])

    def test_mission_cannot_be_completed_as_practice(self):
        self.advance_to_mission()
        with self.assertRaisesRegex(ValueError, "missions complete only"):
            self.progress.complete_practice_unit(self.instance["instance_id"], "supplier-agent-mission")

    def test_submission_records_references_and_frozen_mission_requirements(self):
        self.advance_to_mission()
        submission = self.progress.record_mission_submission(
            submission_id="submission-001",
            instance_id=self.instance["instance_id"],
            unit_id="supplier-agent-mission",
            artifact_refs=("artifact://evaluation-report",),
            artifact_types=("evaluation_report",),
            revision_ref="artifact://revision-diff",
            defense_response_ref="artifact://defense-response",
            changed_scenario_response_ref="artifact://changed-scenario",
        )
        self.assertEqual("submitted", submission["status"])
        self.assertEqual(["artifact://evaluation-report"], submission["artifact_refs"])
        self.assertEqual(2, len(submission["mission_requirements"]))
        self.assertEqual(1, submission["attempt_number"])

    def test_evidence_acceptance_requires_human_review_and_completes_mission(self):
        self.advance_to_mission()
        submission = self.progress.record_mission_submission(
            submission_id="submission-accept-001",
            instance_id=self.instance["instance_id"],
            unit_id="supplier-agent-mission",
            artifact_refs=("artifact://evaluation-report",),
            artifact_types=("evaluation_report",),
            revision_ref="artifact://revision-diff",
            defense_response_ref="artifact://defense-response",
            changed_scenario_response_ref="artifact://changed-scenario",
        )
        with self.assertRaisesRegex(ValueError, "human review"):
            self.progress.accept_mission_evidence(
                submission["submission_id"],
                assessment_execution_id="assessment-001",
                accepted_by="assessment-accountable-person",
                note="Reviewed evidence.",
            )
        self.progress.set_submission_assessment_state(
            submission["submission_id"],
            status="human_review",
            assessment_execution_id="assessment-001",
        )
        accepted = self.progress.accept_mission_evidence(
            submission["submission_id"],
            assessment_execution_id="assessment-001",
            accepted_by="assessment-accountable-person",
            note="Reviewed evidence and assessment record.",
        )
        self.assertEqual("accepted", accepted["status"])
        self.assertEqual("completed", self.progress.get_unit(self.instance["instance_id"], "supplier-agent-mission")["status"])
        self.assertEqual("completed", self.progress.get_instance(self.instance["instance_id"])["status"])
        evidence = self.progress.accepted_capability_evidence(self.instance["instance_id"])
        self.assertEqual(2, len(evidence))
        self.assertTrue(all(item["accepted_by"] == "assessment-accountable-person" for item in evidence))

    def test_event_log_uses_pseudonymous_learner_private_boundary(self):
        events = self.progress.events(self.instance["instance_id"])
        self.assertGreaterEqual(len(events), 1)
        self.assertTrue(all(event["learner_id"] == "learner-ref-001" for event in events))
        self.assertTrue(all(event["privacy_class"] == "learner_private" for event in events))
        self.assertTrue(all(event["cohort_id"] == "cohort-001" for event in events))

    def test_submission_requires_matching_reference_and_type_counts(self):
        self.advance_to_mission()
        with self.assertRaisesRegex(ValueError, "matching artifact"):
            self.progress.record_mission_submission(
                submission_id="submission-bad-001",
                instance_id=self.instance["instance_id"],
                unit_id="supplier-agent-mission",
                artifact_refs=("artifact://one", "artifact://two"),
                artifact_types=("evaluation_report",),
            )


if __name__ == "__main__":
    unittest.main()
