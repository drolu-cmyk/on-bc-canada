from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from runtime.capability_graph import CapabilityDraft, CapabilityGraphStore, CapabilityProvenance, EvidenceStandard
from runtime.graph_kernel import GraphExecution
from runtime.work_intelligence import WorkIntelligenceStore


def completed_execution(execution_id: str = "research-capability-001") -> GraphExecution:
    state = {
        "research_status": "complete",
        "sources": [
            {
                "source_id": "s1",
                "publisher": "Canada Job Bank",
                "title": "Applied AI role",
                "url": "https://example.invalid/s1",
            },
            {
                "source_id": "s2",
                "publisher": "Example Employer",
                "title": "Agent systems role",
                "url": "https://example.invalid/s2",
            },
        ],
        "capabilities": [
            {
                "capability": "Agent evaluation",
                "description": "Evaluate agent behaviour against defined tasks and failure conditions.",
                "evidence_source_ids": ["s1", "s2"],
                "relevant_roles": ["Applied AI Developer"],
                "relevance": "core",
                "tool_neutral": True,
            },
            {
                "capability": "Tool permission design",
                "description": "Constrain agent tool access according to action risk and decision authority.",
                "evidence_source_ids": ["s2"],
                "relevant_roles": ["Agentic AI Engineer"],
                "relevance": "important",
                "tool_neutral": True,
            },
        ],
        "labour_market": {"signals": []},
        "technology": {"signals": []},
        "finding": {
            "question": "What Applied AI capabilities matter?",
            "domain_id": "applied-ai-systems",
            "pathway_name": "Applied AI Systems",
            "confidence": 0.81,
            "curriculum_impact": {
                "recommendation": "increase",
                "requires_human_review": True,
            },
        },
    }
    return GraphExecution(
        execution_id=execution_id,
        graph_id="canadian-work-research",
        graph_version="0.2.0",
        current_node="finalize_finding",
        state=state,
        status="completed",
        history=[
            {"node_id": "curriculum_review", "actor_id": "accountable-human", "approved": True},
            {"node_id": "finalize_finding"},
        ],
    )


def standard(standard_id: str = "agent-evaluation-proof") -> EvidenceStandard:
    return EvidenceStandard(
        standard_id=standard_id,
        description="Evaluate a bounded agent against defined tasks, failure conditions, and evidence criteria.",
        artifact_types=("evaluation_report", "oral_defense"),
        minimum_level="evaluate",
        requires_defense=True,
        requires_revision=True,
        requires_changed_scenario=True,
    )


class CapabilityGraphStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.work = WorkIntelligenceStore(root / "work.sqlite3")
        self.capabilities = CapabilityGraphStore(root / "capabilities.sqlite3")
        self.work.ingest_research_execution(
            completed_execution(),
            pathway_id="applied-ai-systems",
            pathway_name="Applied AI Systems",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def draft(self, *, capability_id="agent-evaluation", capability_name="Agent evaluation", prerequisites=()):
        return self.capabilities.draft_from_work_intelligence(
            work_store=self.work,
            pathway_id="applied-ai-systems",
            pathway_name="Applied AI Systems",
            capability_id=capability_id,
            capability_name=capability_name,
            description=f"Demonstrate {capability_name.lower()} in a bounded technical work scenario with traceable evidence.",
            target_level="evaluate",
            evidence_standards=(standard(f"{capability_id}-proof"),),
            prerequisite_ids=prerequisites,
        )

    def test_research_supported_capability_becomes_draft_with_exact_provenance(self):
        definition = self.draft()
        stored = self.capabilities.get(definition.capability_id)
        self.assertEqual("draft", stored["status"])
        self.assertEqual(0.81, stored["source_confidence"])
        self.assertEqual(1, len(stored["provenance"]))

        work_capability = self.work.find_entity("capability", "Agent evaluation")
        work_relation = next(
            relation
            for relation in self.work.relations_for_entity(work_capability["entity_id"])
            if relation["relation_type"] == "develops_capability"
        )
        self.assertEqual(work_relation["execution_id"], stored["provenance"][0]["execution_id"])
        self.assertEqual(work_relation["relation_id"], stored["provenance"][0]["relation_id"])
        self.assertEqual(work_relation["confidence"], stored["provenance"][0]["confidence"])

    def test_multiple_research_executions_keep_relation_execution_pairs(self):
        self.work.ingest_research_execution(
            completed_execution("research-capability-002"),
            pathway_id="applied-ai-systems",
            pathway_name="Applied AI Systems",
        )
        definition = self.draft()
        stored = self.capabilities.get(definition.capability_id)
        observed = {(item["execution_id"], item["relation_id"]) for item in stored["provenance"]}

        work_capability = self.work.find_entity("capability", "Agent evaluation")
        expected = {
            (relation["execution_id"], relation["relation_id"])
            for relation in self.work.relations_for_entity(work_capability["entity_id"])
            if relation["relation_type"] == "develops_capability"
        }
        self.assertEqual(expected, observed)

    def test_unsupported_capability_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not supported"):
            self.capabilities.draft_from_work_intelligence(
                work_store=self.work,
                pathway_id="applied-ai-systems",
                pathway_name="Applied AI Systems",
                capability_id="quantum-routing",
                capability_name="Quantum routing",
                description="Design quantum routing for a production agent system with traceable evidence.",
                target_level="design",
                evidence_standards=(standard("quantum-proof"),),
            )

    def test_activation_requires_human_and_records_decision(self):
        definition = self.draft()
        with self.assertRaisesRegex(ValueError, "human approver"):
            self.capabilities.activate(definition.capability_id, approver_id="")

        active = self.capabilities.activate(
            definition.capability_id,
            approver_id="curriculum-accountable-person",
            note="Evidence standard and pathway fit reviewed.",
        )
        self.assertEqual("active", active["status"])
        self.assertEqual("activate", active["decisions"][0]["decision"])
        self.assertEqual("curriculum-accountable-person", active["decisions"][0]["approver_id"])

    def test_prerequisite_must_be_active_before_dependent_activation(self):
        base = self.draft()
        dependent = self.draft(
            capability_id="tool-permission-design",
            capability_name="Tool permission design",
            prerequisites=(base.capability_id,),
        )
        with self.assertRaisesRegex(ValueError, "prerequisites must be active"):
            self.capabilities.activate(dependent.capability_id, approver_id="curriculum-accountable-person")

        self.capabilities.activate(base.capability_id, approver_id="curriculum-accountable-person")
        active = self.capabilities.activate(dependent.capability_id, approver_id="curriculum-accountable-person")
        self.assertEqual("active", active["status"])
        self.assertEqual([base.capability_id], active["prerequisite_ids"])

    def test_active_capability_cannot_be_overwritten_by_agent_draft(self):
        definition = self.draft()
        self.capabilities.activate(definition.capability_id, approver_id="curriculum-accountable-person")
        changed = replace(definition, description="A materially different agent-authored definition that should not replace active curriculum.")
        with self.assertRaisesRegex(ValueError, "cannot be overwritten"):
            self.capabilities.save_draft(changed)

    def test_retirement_is_blocked_while_active_dependents_exist(self):
        base = self.draft()
        self.capabilities.activate(base.capability_id, approver_id="curriculum-accountable-person")
        dependent = self.draft(
            capability_id="tool-permission-design",
            capability_name="Tool permission design",
            prerequisites=(base.capability_id,),
        )
        self.capabilities.activate(dependent.capability_id, approver_id="curriculum-accountable-person")

        with self.assertRaisesRegex(ValueError, "active capabilities depend"):
            self.capabilities.retire(
                base.capability_id,
                approver_id="curriculum-accountable-person",
                note="Attempted retirement for test.",
            )

    def test_evidence_standard_rejects_unknown_artifact_type(self):
        with self.assertRaisesRegex(ValueError, "unsupported evidence artifact"):
            EvidenceStandard(
                standard_id="bad-proof",
                description="A long enough evidence standard description for validation.",
                artifact_types=("multiple_choice_quiz",),
                minimum_level="evaluate",
            )

    def test_manual_draft_without_work_provenance_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "requires Work Intelligence provenance"):
            CapabilityDraft(
                capability_id="unproven-capability",
                pathway_id="applied-ai-systems",
                name="Unproven capability",
                description="This definition has no supporting Work Intelligence relation and must fail closed.",
                target_level="evaluate",
                evidence_standards=(standard("unproven-proof"),),
                provenance=(),
            )

    def test_provenance_object_rejects_invalid_confidence(self):
        with self.assertRaisesRegex(ValueError, "confidence"):
            CapabilityProvenance(execution_id="r1", relation_id="rel-1", confidence=1.1)


if __name__ == "__main__":
    unittest.main()
