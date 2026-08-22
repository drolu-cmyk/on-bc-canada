from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.business_operations_runner import resume_business_operations, start_business_operations
from runtime.graph_execution_store import GraphExecutionStore
from runtime.test_business_operations_graph import FakeProvider


class BusinessOperationsStoreTests(unittest.TestCase):
    def test_a3_gate_survives_restart_without_rerunning_marketing_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "business.sqlite3"
            store = GraphExecutionStore(path)
            provider = FakeProvider()
            first = start_business_operations(
                provider=provider,
                store=store,
                execution_id="business-restart-a3",
                request={
                    "workstream": "marketing",
                    "action_class": "external_publish",
                    "problem": "Prepare a public pathway message.",
                },
            )
            self.assertEqual(["marketing"], provider.calls)
            self.assertEqual("waiting_approval", first.status)
            original_event_count = len(store.load_execution(first.execution_id)[1].events)

            restarted_store = GraphExecutionStore(path)
            restarted_provider = FakeProvider()
            completed = resume_business_operations(
                provider=restarted_provider,
                store=restarted_store,
                execution_id=first.execution_id,
                approved=True,
                approver_id="external-action-accountable-person",
                note="Reviewed external publication package.",
            )
            self.assertEqual([], restarted_provider.calls)
            self.assertEqual("completed", completed.status)
            self.assertEqual("authorized_for_external_execution", completed.state["business_record"]["status"])
            terminal = restarted_store.get_terminal_record(first.execution_id, "business_record")
            self.assertEqual("authorized_for_external_execution", terminal["status"])
            self.assertGreater(len(restarted_store.load_execution(first.execution_id)[1].events), original_event_count)

    def test_a4_gate_survives_restart_without_rerunning_finance_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "business.sqlite3"
            store = GraphExecutionStore(path)
            first_provider = FakeProvider()
            first = start_business_operations(
                provider=first_provider,
                store=store,
                execution_id="business-restart-a4",
                request={
                    "workstream": "finance",
                    "action_class": "financial_commitment",
                    "problem": "Evaluate a bounded model-cost commitment.",
                },
            )
            self.assertEqual(["finance"], first_provider.calls)
            self.assertEqual("A4", first.pending_approval["authority"])

            restarted_provider = FakeProvider()
            completed = resume_business_operations(
                provider=restarted_provider,
                store=GraphExecutionStore(path),
                execution_id=first.execution_id,
                approved=True,
                approver_id="financial-accountable-person",
                note="Authorization recorded separately from payment execution.",
            )
            self.assertEqual([], restarted_provider.calls)
            self.assertEqual("authorized_for_financial_execution", completed.state["business_record"]["status"])

    def test_direct_analysis_persists_terminal_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = GraphExecutionStore(Path(tmp) / "business.sqlite3")
            execution = start_business_operations(
                provider=FakeProvider(),
                store=store,
                execution_id="business-direct",
                request={
                    "workstream": "operations",
                    "action_class": "analysis",
                    "problem": "Review learner intake flow.",
                },
            )
            self.assertEqual("completed", execution.status)
            record = store.get_terminal_record(execution.execution_id, "business_record")
            self.assertEqual("analysis_complete", record["status"])


if __name__ == "__main__":
    unittest.main()
