from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.capability_graph import CapabilityDraft, CapabilityGraphStore, CapabilityProvenance, EvidenceStandard
from runtime.test_capability_graph import completed_execution
from runtime.work_intelligence import WorkIntelligenceStore


class CapabilityGraphIntegrityTests(unittest.TestCase):
    def test_pathway_identifier_must_match_work_intelligence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = WorkIntelligenceStore(root / "work.sqlite3")
            graph = CapabilityGraphStore(root / "capabilities.sqlite3")
            work.ingest_research_execution(
                completed_execution(),
                pathway_id="applied-ai-systems",
                pathway_name="Applied AI Systems",
            )
            standard = EvidenceStandard(
                standard_id="agent-evaluation-proof",
                description="Evaluate a bounded agent against explicit tasks and failure conditions.",
                artifact_types=("evaluation_report",),
                minimum_level="evaluate",
            )
            with self.assertRaisesRegex(ValueError, "pathway ID does not match"):
                graph.draft_from_work_intelligence(
                    work_store=work,
                    pathway_id="wrong-pathway",
                    pathway_name="Applied AI Systems",
                    capability_id="agent-evaluation",
                    capability_name="Agent evaluation",
                    description="Evaluate a bounded agent against explicit tasks and failure conditions.",
                    target_level="evaluate",
                    evidence_standards=(standard,),
                )

    def test_duplicate_evidence_standard_ids_fail_before_storage(self):
        standard = EvidenceStandard(
            standard_id="proof-one",
            description="Produce traceable evidence for the defined technical capability.",
            artifact_types=("evaluation_report",),
            minimum_level="evaluate",
        )
        with self.assertRaisesRegex(ValueError, "duplicate evidence standard"):
            CapabilityDraft(
                capability_id="agent-evaluation",
                pathway_id="applied-ai-systems",
                name="Agent evaluation",
                description="Evaluate a bounded agent against explicit tasks and failure conditions.",
                target_level="evaluate",
                evidence_standards=(standard, standard),
                provenance=(CapabilityProvenance("research-1", "relation-1", 0.8),),
            )


if __name__ == "__main__":
    unittest.main()
