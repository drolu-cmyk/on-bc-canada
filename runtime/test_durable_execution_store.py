from __future__ import annotations

import unittest

from runtime.aws_durable_execution import AwsDurableExecutionConfig, ExecutionConflictError
from runtime.control_plane import EventLedger
from runtime.durable_execution_store import DurableGraphExecutionStore
from runtime.graph_kernel import GraphExecution
from runtime.test_aws_durable_execution import FakeDynamoClient


class DurableExecutionStoreTests(unittest.TestCase):
    def test_fresh_store_cannot_overwrite_existing_execution_without_load(self):
        client = FakeDynamoClient()
        config = AwsDurableExecutionConfig(
            region="ca-central-1",
            table_name="test-executions",
            queue_url="https://sqs.ca-central-1.amazonaws.com/123/test.fifo",
            event_bus_name="test-events",
        )
        execution = GraphExecution(
            execution_id="exec-protected",
            graph_id="runtime-assurance",
            graph_version="0.1.0",
            current_node="start",
            state={"bounded": True},
        )
        first = DurableGraphExecutionStore(config=config, client=client)
        first.save_execution(execution, EventLedger())

        fresh = DurableGraphExecutionStore(config=config, client=client)
        replacement = GraphExecution(
            execution_id="exec-protected",
            graph_id="runtime-assurance",
            graph_version="0.1.0",
            current_node="different-start",
            state={"bounded": False},
        )
        with self.assertRaises(ExecutionConflictError):
            fresh.save_execution(replacement, EventLedger())

        loaded, ledger = fresh.load_execution("exec-protected")
        loaded.current_node = "reviewed-update"
        fresh.save_execution(loaded, ledger)
        round_trip, _ = fresh.load_execution("exec-protected")
        self.assertEqual("reviewed-update", round_trip.current_node)


if __name__ == "__main__":
    unittest.main()
