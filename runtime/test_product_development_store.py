from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.product_development_runner import resume_product_development, start_product_development
from runtime.product_development_store import ProductDevelopmentStore
from runtime.test_product_development_graph import FakeProvider


class ProductDevelopmentStoreTests(unittest.TestCase):
    def test_human_review_survives_restart_and_records_release_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "product.sqlite3"
            store = ProductDevelopmentStore(path)
            first = start_product_development(
                provider=FakeProvider(),
                store=store,
                execution_id="product-restart-1",
                request={"problem": "Learners cannot quickly see current work."},
            )
            self.assertEqual("waiting_approval", first.status)
            event_count = len(store.load_execution(first.execution_id)[1].events)

            restarted_store = ProductDevelopmentStore(path)
            completed = resume_product_development(
                provider=FakeProvider(),
                store=restarted_store,
                execution_id=first.execution_id,
                approved=True,
                approver_id="release-accountable-person",
                note="Reviewed release packet after restart.",
            )
            self.assertEqual("completed", completed.status)
            self.assertEqual("authorized_for_implementation", completed.state["release_record"]["status"])
            record = restarted_store.get_release_record(first.execution_id)
            self.assertEqual("authorized_for_implementation", record["status"])
            self.assertGreater(len(restarted_store.load_execution(first.execution_id)[1].events), event_count)

    def test_blocked_execution_is_durable_without_human_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ProductDevelopmentStore(Path(tmp) / "product.sqlite3")
            execution = start_product_development(
                provider=FakeProvider(
                    security_status="block",
                    security_blockers=["destructive agent action has no approval boundary"],
                ),
                store=store,
                execution_id="product-blocked-1",
                request={"problem": "Add destructive autonomous maintenance."},
            )
            self.assertEqual("completed", execution.status)
            self.assertEqual("blocked", store.get_release_record(execution.execution_id)["status"])
            loaded, _ = store.load_execution(execution.execution_id)
            self.assertEqual("blocked", loaded.state["product_status"])


if __name__ == "__main__":
    unittest.main()
