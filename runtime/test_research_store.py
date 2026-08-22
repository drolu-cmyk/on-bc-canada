from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.control_plane import EventLedger
from runtime.graph_kernel import GraphExecution
from runtime.research_store import ResearchStore


class ResearchStoreTests(unittest.TestCase):
    def test_round_trip_preserves_state_approval_and_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ResearchStore(Path(tmp) / "research.sqlite3")
            ledger = EventLedger()
            ledger.append(
                event_type="graph.execution_started.v1",
                program_id="applied-ai-training-canada",
                producer="graph-runtime",
                actor_id="graph-kernel",
                correlation_id="corr-r1",
                idempotency_key="graph:r1:start:1",
                payload={"graph_id": "canadian-work-research"},
                privacy_class="internal_operational",
                retention_class="quality_record",
            )
            execution = GraphExecution(
                execution_id="r1",
                graph_id="canadian-work-research",
                graph_version="0.2.0",
                current_node="curriculum_review",
                state={
                    "evidence": [{"source_id": "s1"}],
                    "curriculum_impact": {"recommendation": "increase"},
                },
                status="waiting_approval",
                history=[{"node_id": "assess_curriculum_impact"}],
                checkpoints=[{"node_id": "assess_curriculum_impact", "state": {"x": 1}}],
                pending_approval={"node_id": "curriculum_review", "authority": "A3"},
            )
            store.save_execution(execution, ledger)
            restored, restored_ledger = store.load_execution("r1")
            self.assertEqual("waiting_approval", restored.status)
            self.assertEqual("increase", restored.state["curriculum_impact"]["recommendation"])
            self.assertEqual("A3", restored.pending_approval["authority"])
            self.assertEqual(ledger.events, restored_ledger.events)
            self.assertEqual(ledger.idempotency_keys, restored_ledger.idempotency_keys)

    def test_completed_finding_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ResearchStore(Path(tmp) / "research.sqlite3")
            execution = GraphExecution(
                execution_id="r2",
                graph_id="canadian-work-research",
                graph_version="0.2.0",
                current_node="finalize_finding",
                state={"finding": {"question": "q", "confidence": 0.8}},
                status="completed",
            )
            store.save_execution(execution, EventLedger())
            self.assertEqual(0.8, store.get_finding("r2")["confidence"])


if __name__ == "__main__":
    unittest.main()
