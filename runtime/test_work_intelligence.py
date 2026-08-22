from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.graph_kernel import GraphExecution
from runtime.work_intelligence import WorkIntelligenceStore


def completed_execution(*, authorized: bool = True, recommendation: str = "increase") -> GraphExecution:
    history = [{"node_id": "finalize_finding"}]
    if authorized:
        history.insert(
            0,
            {
                "node_id": "curriculum_review",
                "actor_id": "accountable-human",
                "approved": True,
            },
        )
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
                "publisher": "Employer 2",
                "title": "AI systems role",
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
                "description": "Constrain tool access according to action risk.",
                "evidence_source_ids": ["s2"],
                "relevant_roles": ["Agentic AI Engineer"],
                "relevance": "important",
                "tool_neutral": True,
            },
        ],
        "labour_market": {
            "signals": [
                {
                    "role": "Applied AI Developer",
                    "capability_hint": "Agent evaluation",
                    "geography": "Canada",
                    "signal": "repeated",
                    "source_ids": ["s1", "s2"],
                    "note": "Observed across more than one source.",
                }
            ]
        },
        "technology": {
            "signals": [
                {
                    "technology": "Agent evaluation harness",
                    "relationship": "Supports repeatable agent testing.",
                    "maturity": "growing",
                    "source_ids": ["s2"],
                    "note": "Implementation technology, not the learning outcome.",
                }
            ]
        },
        "finding": {
            "question": "What capabilities matter?",
            "confidence": 0.81,
            "curriculum_impact": {
                "recommendation": recommendation,
                "requires_human_review": recommendation != "no_change",
            },
        },
    }
    return GraphExecution(
        execution_id="research-validated-001",
        graph_id="canadian-work-research",
        graph_version="0.2.0",
        current_node="finalize_finding",
        state=state,
        status="completed",
        history=history,
    )


class WorkIntelligenceStoreTests(unittest.TestCase):
    def test_validated_research_builds_traceable_work_relationships(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = WorkIntelligenceStore(Path(tmp) / "work.sqlite3")
            result = store.ingest_research_execution(
                completed_execution(),
                pathway_id="applied-ai-systems",
                pathway_name="Applied AI Systems",
            )
            self.assertFalse(result["idempotent"])
            self.assertEqual(2, result["source_count"])
            self.assertEqual(6, result["relation_count"])

            capability = store.find_entity("capability", "Agent evaluation")
            self.assertIsNotNone(capability)
            relations = store.relations_for_entity(capability["entity_id"])
            relation_types = {relation["relation_type"] for relation in relations}
            self.assertIn("develops_capability", relation_types)
            self.assertIn("requires_capability", relation_types)
            self.assertIn("signals_capability", relation_types)

    def test_same_research_execution_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = WorkIntelligenceStore(Path(tmp) / "work.sqlite3")
            execution = completed_execution()
            first = store.ingest_research_execution(
                execution,
                pathway_id="applied-ai-systems",
                pathway_name="Applied AI Systems",
            )
            second = store.ingest_research_execution(
                execution,
                pathway_id="applied-ai-systems",
                pathway_name="Applied AI Systems",
            )
            self.assertFalse(first["idempotent"])
            self.assertTrue(second["idempotent"])
            self.assertEqual(first["relation_count"], second["relation_count"])

    def test_change_recommendation_without_human_authorization_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = WorkIntelligenceStore(Path(tmp) / "work.sqlite3")
            with self.assertRaisesRegex(ValueError, "human authorization"):
                store.ingest_research_execution(
                    completed_execution(authorized=False),
                    pathway_id="applied-ai-systems",
                    pathway_name="Applied AI Systems",
                )

    def test_no_change_finding_can_enter_without_curriculum_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = WorkIntelligenceStore(Path(tmp) / "work.sqlite3")
            result = store.ingest_research_execution(
                completed_execution(authorized=False, recommendation="no_change"),
                pathway_id="applied-ai-systems",
                pathway_name="Applied AI Systems",
            )
            self.assertGreater(result["relation_count"], 0)

    def test_incomplete_research_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = WorkIntelligenceStore(Path(tmp) / "work.sqlite3")
            execution = completed_execution()
            execution.status = "waiting_approval"
            with self.assertRaisesRegex(ValueError, "only completed"):
                store.ingest_research_execution(
                    execution,
                    pathway_id="applied-ai-systems",
                    pathway_name="Applied AI Systems",
                )


if __name__ == "__main__":
    unittest.main()
