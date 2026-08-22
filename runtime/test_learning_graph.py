from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from runtime.capability_graph import CapabilityGraphStore
from runtime.learning_graph import EvidenceRequirement, LearningGraphStore, LearningPathDefinition, LearningUnit
from runtime.test_capability_graph import completed_execution, standard
from runtime.work_intelligence import WorkIntelligenceStore


class LearningGraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.work = WorkIntelligenceStore(root / "work.sqlite3")
        self.capabilities = CapabilityGraphStore(root / "capabilities.sqlite3")
        self.learning = LearningGraphStore(root / "learning.sqlite3")
        self.work.ingest_research_execution(
            completed_execution(),
            pathway_id="applied-ai-systems",
            pathway_name="Applied AI Systems",
        )
        self.agent_eval = self.capabilities.draft_from_work_intelligence(
            work_store=self.work,
            pathway_id="applied-ai-systems",
            pathway_name="Applied AI Systems",
            capability_id="agent-evaluation",
            capability_name="Agent evaluation",
            description="Evaluate bounded agent behaviour against explicit tasks, evidence criteria, and failure conditions.",
            target_level="evaluate",
            evidence_standards=(standard("agent-evaluation-proof"),),
        )
        self.capabilities.activate(
            self.agent_eval.capability_id,
            approver_id="curriculum-accountable-person",
            note="Reviewed capability definition and evidence standard.",
        )
        self.tool_permissions = self.capabilities.draft_from_work_intelligence(
            work_store=self.work,
            pathway_id="applied-ai-systems",
            pathway_name="Applied AI Systems",
            capability_id="tool-permission-design",
            capability_name="Tool permission design",
            description="Design bounded tool permissions for agent actions according to risk and accountable decision authority.",
            target_level="design",
            evidence_standards=(standard("tool-permission-proof"),),
            prerequisite_ids=(self.agent_eval.capability_id,),
        )
        self.capabilities.activate(
            self.tool_permissions.capability_id,
            approver_id="curriculum-accountable-person",
            note="Reviewed dependency and evidence requirements.",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def path(self, version: str = "0.1.0") -> LearningPathDefinition:
        sprint = LearningUnit(
            unit_id="agent-evaluation-sprint",
            kind="sprint",
            title="Agent evaluation foundations",
            purpose="Build the reasoning needed to define tasks, failure conditions, evidence, and evaluation boundaries.",
            develops_capability_ids=("agent-evaluation",),
            source_module_ids=("AAI-101",),
        )
        lab = LearningUnit(
            unit_id="agent-control-lab",
            kind="lab",
            title="Agent control lab",
            purpose="Practise evaluation and permission decisions in a bounded synthetic agent environment before the mission.",
            develops_capability_ids=("agent-evaluation", "tool-permission-design"),
            prerequisite_unit_ids=(sprint.unit_id,),
            source_module_ids=("AAI-101", "AAI-102"),
        )
        mission = LearningUnit(
            unit_id="supplier-agent-mission",
            kind="mission",
            title="Supplier review agent mission",
            purpose="Evaluate and constrain a supplier-review agent, defend the control design, and respond to a changed scenario.",
            develops_capability_ids=("agent-evaluation", "tool-permission-design"),
            evidence_requirements=(
                EvidenceRequirement("agent-evaluation", "agent-evaluation-proof"),
                EvidenceRequirement("tool-permission-design", "tool-permission-proof"),
            ),
            prerequisite_unit_ids=(lab.unit_id,),
            source_module_ids=("AAI-102",),
        )
        # Deliberately reverse dependency order to prove persistence is graph-based,
        # not dependent on input ordering.
        return LearningPathDefinition(
            pathway_id="applied-ai-systems",
            version=version,
            title="Applied AI Systems capability path",
            target_capability_ids=("agent-evaluation", "tool-permission-design"),
            units=(mission, lab, sprint),
        )

    def test_valid_path_persists_edges_independent_of_input_order(self):
        saved = self.learning.save_candidate(self.path(), capabilities=self.capabilities)
        self.assertEqual("candidate", saved["status"])
        mission = next(item for item in saved["units"] if item["unit_id"] == "supplier-agent-mission")
        lab = next(item for item in saved["units"] if item["unit_id"] == "agent-control-lab")
        self.assertEqual(["agent-control-lab"], mission["prerequisite_unit_ids"])
        self.assertEqual(["agent-evaluation-sprint"], lab["prerequisite_unit_ids"])
        self.assertEqual(2, len(mission["evidence_requirements"]))

    def test_activation_requires_human_review_note(self):
        self.learning.save_candidate(self.path(), capabilities=self.capabilities)
        with self.assertRaisesRegex(ValueError, "review note"):
            self.learning.activate("applied-ai-systems", "0.1.0", approver_id="human", note="")
        active = self.learning.activate(
            "applied-ai-systems",
            "0.1.0",
            approver_id="curriculum-accountable-person",
            note="Reviewed sequence, evidence coverage, and existing module links.",
        )
        self.assertEqual("active", active["status"])
        self.assertEqual("activate", active["decisions"][0]["decision"])

    def test_cycle_fails_before_storage(self):
        first = LearningUnit(
            unit_id="first-unit",
            kind="sprint",
            title="First unit",
            purpose="Develop evaluation reasoning with a bounded technical exercise and explicit evidence criteria.",
            develops_capability_ids=("agent-evaluation",),
            prerequisite_unit_ids=("second-unit",),
        )
        second = LearningUnit(
            unit_id="second-unit",
            kind="lab",
            title="Second unit",
            purpose="Practise evaluation decisions with a bounded technical exercise and explicit evidence criteria.",
            develops_capability_ids=("agent-evaluation",),
            prerequisite_unit_ids=("first-unit",),
        )
        with self.assertRaisesRegex(ValueError, "cycle"):
            LearningPathDefinition(
                pathway_id="applied-ai-systems",
                version="bad-cycle",
                title="Bad cycle",
                target_capability_ids=("agent-evaluation",),
                units=(first, second),
            )

    def test_evidence_requirement_must_be_on_mission(self):
        with self.assertRaisesRegex(ValueError, "attached to missions"):
            LearningUnit(
                unit_id="bad-lab",
                kind="lab",
                title="Bad lab",
                purpose="This lab incorrectly attempts to establish final capability evidence rather than practice.",
                develops_capability_ids=("agent-evaluation",),
                evidence_requirements=(EvidenceRequirement("agent-evaluation", "agent-evaluation-proof"),),
            )

    def test_mission_cannot_assess_capability_it_does_not_develop(self):
        with self.assertRaisesRegex(ValueError, "does not develop"):
            LearningUnit(
                unit_id="bad-mission",
                kind="mission",
                title="Bad mission",
                purpose="This mission incorrectly claims evidence for a capability that is outside its developed work.",
                develops_capability_ids=("agent-evaluation",),
                evidence_requirements=(EvidenceRequirement("tool-permission-design", "tool-permission-proof"),),
            )

    def test_unknown_evidence_standard_is_rejected(self):
        definition = self.path()
        mission = next(item for item in definition.units if item.kind == "mission")
        changed_mission = replace(
            mission,
            evidence_requirements=(EvidenceRequirement("agent-evaluation", "unknown-proof"),),
            develops_capability_ids=("agent-evaluation",),
        )
        changed = replace(
            definition,
            target_capability_ids=("agent-evaluation",),
            units=tuple(changed_mission if item.unit_id == mission.unit_id else item for item in definition.units),
        )
        with self.assertRaisesRegex(ValueError, "unknown evidence standard"):
            self.learning.save_candidate(changed, capabilities=self.capabilities)

    def test_every_target_capability_requires_mission_evidence(self):
        definition = self.path()
        mission = next(item for item in definition.units if item.kind == "mission")
        changed_mission = replace(
            mission,
            evidence_requirements=(EvidenceRequirement("agent-evaluation", "agent-evaluation-proof"),),
        )
        changed = replace(
            definition,
            units=tuple(changed_mission if item.unit_id == mission.unit_id else item for item in definition.units),
        )
        with self.assertRaisesRegex(ValueError, "lack mission evidence coverage"):
            self.learning.save_candidate(changed, capabilities=self.capabilities)

    def test_inactive_capability_is_rejected(self):
        self.capabilities.retire(
            self.tool_permissions.capability_id,
            approver_id="curriculum-accountable-person",
            note="Retired for validation test.",
        )
        with self.assertRaisesRegex(ValueError, "not active"):
            self.learning.save_candidate(self.path(), capabilities=self.capabilities)

    def test_active_path_version_cannot_be_replaced(self):
        definition = self.path()
        self.learning.save_candidate(definition, capabilities=self.capabilities)
        self.learning.activate(
            definition.pathway_id,
            definition.version,
            approver_id="curriculum-accountable-person",
            note="Reviewed learning path.",
        )
        with self.assertRaisesRegex(ValueError, "cannot be replaced"):
            self.learning.save_candidate(definition, capabilities=self.capabilities)

    def test_second_version_waits_until_current_active_path_is_retired(self):
        first = self.path("0.1.0")
        second = self.path("0.2.0")
        self.learning.save_candidate(first, capabilities=self.capabilities)
        self.learning.activate(
            first.pathway_id,
            first.version,
            approver_id="curriculum-accountable-person",
            note="Activate first version.",
        )
        self.learning.save_candidate(second, capabilities=self.capabilities)
        with self.assertRaisesRegex(ValueError, "retire active"):
            self.learning.activate(
                second.pathway_id,
                second.version,
                approver_id="curriculum-accountable-person",
                note="Attempt second version.",
            )
        self.learning.retire(
            first.pathway_id,
            first.version,
            approver_id="curriculum-accountable-person",
            note="Replace with reviewed second version.",
        )
        active = self.learning.activate(
            second.pathway_id,
            second.version,
            approver_id="curriculum-accountable-person",
            note="Activate reviewed second version.",
        )
        self.assertEqual("0.2.0", active["version"])

    def test_retired_capability_definition_cannot_be_rewritten(self):
        retired = self.tool_permissions
        self.capabilities.retire(
            retired.capability_id,
            approver_id="curriculum-accountable-person",
            note="Retire for history-preservation test.",
        )
        with self.assertRaisesRegex(ValueError, "retired capability"):
            self.capabilities.save_draft(replace(retired, description="A replacement definition that must not erase historical evidence."))


if __name__ == "__main__":
    unittest.main()
