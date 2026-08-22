from __future__ import annotations

import json
import os
import unittest
from copy import deepcopy
from unittest.mock import patch

from botocore.exceptions import ClientError

from runtime.aws_durable_execution import (
    AWS_EXECUTION_ENABLED_ENV,
    AwsDurableExecutionConfig,
    AwsDurableWorkQueue,
    BoundedPlatformEventPublisher,
    DurableCommandConflictError,
    DynamoGraphExecutionStore,
    ExecutionConflictError,
    ExecutionLeaseError,
    WorkCommand,
    _read_n,
    _read_s,
)
from runtime.aws_execution_assurance import (
    DynamoRuntimeExecutionSource,
    aggregate_dynamo_execution_rows,
    apply_dynamo_executions_to_snapshot,
)
from runtime.control_plane import EventLedger
from runtime.execution_store_factory import create_execution_store, execution_backend
from runtime.graph_execution_store import GraphExecutionStore
from runtime.graph_kernel import GraphExecution


def conditional_error(operation: str = "UpdateItem") -> ClientError:
    return ClientError({"Error": {"Code": "ConditionalCheckFailedException", "Message": "conditional"}}, operation)


class FakeDynamoClient:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict] = {}
        self.query_calls: list[dict] = []

    @staticmethod
    def _key(key: dict) -> tuple[str, str]:
        return key["pk"]["S"], key["sk"]["S"]

    def get_item(self, *, TableName, Key, ConsistentRead=False):
        item = self.items.get(self._key(Key))
        return {"Item": deepcopy(item)} if item is not None else {}

    def put_item(self, *, TableName, Item, ConditionExpression=None):
        key = self._key(Item)
        if ConditionExpression and key in self.items:
            raise conditional_error("PutItem")
        self.items[key] = deepcopy(Item)
        return {}

    def update_item(
        self,
        *,
        TableName,
        Key,
        UpdateExpression,
        ConditionExpression=None,
        ExpressionAttributeValues=None,
        ExpressionAttributeNames=None,
    ):
        values = ExpressionAttributeValues or {}
        key = self._key(Key)
        item = deepcopy(self.items.get(key, {"pk": Key["pk"], "sk": Key["sk"]}))

        if UpdateExpression.startswith("SET lease_owner"):
            if key not in self.items:
                raise conditional_error()
            now = int(values[":now"]["N"])
            current_expiry = _read_n(item, "lease_expires_at", 0)
            current_owner = _read_s(item, "lease_owner")
            owner = values[":owner"]["S"]
            if current_expiry >= now and current_owner not in {None, owner}:
                raise conditional_error()
            item["lease_owner"] = deepcopy(values[":owner"])
            item["lease_expires_at"] = deepcopy(values[":expires"])
            item["lease_acquired_at"] = deepcopy(values[":now"])
        elif UpdateExpression.startswith("REMOVE lease_owner"):
            if _read_s(item, "lease_owner") != values[":owner"]["S"]:
                raise conditional_error()
            for field in ("lease_owner", "lease_expires_at", "lease_acquired_at"):
                item.pop(field, None)
        elif "#command_status" in UpdateExpression:
            if key not in self.items:
                raise conditional_error()
            item["status"] = deepcopy(values[":status"])
            item["updated_at"] = deepcopy(values[":updated"])
        else:
            current_revision = _read_n(item, "revision", 0)
            if ConditionExpression == "attribute_not_exists(revision)" and key in self.items:
                raise conditional_error()
            if ConditionExpression == "revision = :expected_revision":
                expected = int(values[":expected_revision"]["N"])
                if current_revision != expected:
                    raise conditional_error()
            mapping = {
                "graph_id": ":graph_id",
                "graph_version": ":graph_version",
                "current_node": ":current_node",
                "status": ":status",
                "state_json": ":state",
                "history_json": ":history",
                "checkpoints_json": ":checkpoints",
                "events_json": ":events",
                "store_version": ":store_version",
                "updated_at": ":updated",
                "revision": ":revision",
            }
            for field, token in mapping.items():
                item[field] = deepcopy(values[token])
            if ":pending" in values:
                item["pending_approval_json"] = deepcopy(values[":pending"])
                item.pop("failure", None)
            elif ":failure" in values:
                item["failure"] = deepcopy(values[":failure"])
                item.pop("pending_approval_json", None)
            else:
                item.pop("failure", None)
                item.pop("pending_approval_json", None)
        self.items[key] = item
        return {}

    def query(self, **kwargs):
        self.query_calls.append(deepcopy(kwargs))
        items = [deepcopy(item) for (pk, sk), item in self.items.items() if sk == "STATE"]
        return {"Items": items}


class FakeSqsClient:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.received: list[dict] = []
        self.deleted: list[dict] = []
        self.visibility: list[dict] = []

    def send_message(self, **kwargs):
        self.sent.append(deepcopy(kwargs))
        self.received.append(
            {
                "MessageId": "msg-001",
                "ReceiptHandle": "receipt-001",
                "Body": kwargs["MessageBody"],
                "Attributes": {"ApproximateReceiveCount": "1"},
            }
        )
        return {"MessageId": "msg-001"}

    def receive_message(self, **kwargs):
        return {"Messages": deepcopy(self.received[: kwargs["MaxNumberOfMessages"]])}

    def delete_message(self, **kwargs):
        self.deleted.append(deepcopy(kwargs))

    def change_message_visibility(self, **kwargs):
        self.visibility.append(deepcopy(kwargs))


class FakeEventsClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def put_events(self, *, Entries):
        self.calls.append(deepcopy(Entries[0]))
        return {"FailedEntryCount": 0, "Entries": [{"EventId": "event-001"}]}


class AwsDurableExecutionTests(unittest.TestCase):
    def _config(self) -> AwsDurableExecutionConfig:
        return AwsDurableExecutionConfig(
            region="ca-central-1",
            table_name="test-executions",
            queue_url="https://sqs.ca-central-1.amazonaws.com/123/test.fifo",
            event_bus_name="test-events",
            command_ttl_days=14,
            lease_seconds=120,
        )

    def _execution(self, execution_id: str = "exec-001") -> tuple[GraphExecution, EventLedger]:
        ledger = EventLedger()
        ledger.append(
            event_type="graph.execution_started.v1",
            program_id="applied-ai-training-canada",
            producer="graph-kernel",
            actor_id="platform-service",
            correlation_id=execution_id,
            idempotency_key=f"{execution_id}:start",
            payload={"start_node": "start"},
            privacy_class="internal_operational",
            retention_class="quality_record",
        )
        execution = GraphExecution(
            execution_id=execution_id,
            graph_id="business-operations",
            graph_version="0.1.0",
            current_node="start",
            state={"request": {"market": "Canada"}},
            status="waiting_approval",
            history=[{"node_id": "prepare", "actor_id": "operations-agent", "route": None, "evidence": []}],
            checkpoints=[],
            pending_approval={"node_id": "authorize", "authority": "A3"},
        )
        return execution, ledger

    def test_round_trip_preserves_state_events_and_terminal_record(self):
        client = FakeDynamoClient()
        store = DynamoGraphExecutionStore(config=self._config(), client=client)
        execution, ledger = self._execution()
        store.save_execution(execution, ledger)
        loaded, loaded_ledger = store.load_execution(execution.execution_id)
        self.assertEqual(execution.state, loaded.state)
        self.assertEqual("waiting_approval", loaded.status)
        self.assertEqual(ledger.events, loaded_ledger.events)
        self.assertEqual(1, _read_n(client.items[("EXEC#exec-001", "STATE")], "revision"))
        self.assertIn(("EXEC#exec-001", "EVENT#evt-000001"), client.items)

        loaded.status = "completed"
        loaded.pending_approval = None
        loaded.current_node = "finalize"
        store.save_execution(loaded, loaded_ledger, terminal_records={"business_record": {"status": "complete"}})
        self.assertEqual({"status": "complete"}, store.get_terminal_record("exec-001", "business_record"))
        self.assertEqual(2, _read_n(client.items[("EXEC#exec-001", "STATE")], "revision"))

    def test_concurrent_writers_fail_closed_on_revision_conflict(self):
        client = FakeDynamoClient()
        first = DynamoGraphExecutionStore(config=self._config(), client=client)
        execution, ledger = self._execution()
        first.save_execution(execution, ledger)
        writer_a = DynamoGraphExecutionStore(config=self._config(), client=client)
        writer_b = DynamoGraphExecutionStore(config=self._config(), client=client)
        a, a_ledger = writer_a.load_execution("exec-001")
        b, b_ledger = writer_b.load_execution("exec-001")
        a.current_node = "a"
        writer_a.save_execution(a, a_ledger)
        b.current_node = "b"
        with self.assertRaises(ExecutionConflictError):
            writer_b.save_execution(b, b_ledger)

    def test_lease_blocks_second_owner_until_expiry(self):
        client = FakeDynamoClient()
        store = DynamoGraphExecutionStore(config=self._config(), client=client)
        execution, ledger = self._execution()
        store.save_execution(execution, ledger)
        self.assertEqual(1120, store.acquire_lease("exec-001", owner="worker-a", now_epoch=1000, lease_seconds=120))
        with self.assertRaises(ExecutionLeaseError):
            store.acquire_lease("exec-001", owner="worker-b", now_epoch=1050, lease_seconds=120)
        self.assertEqual(1320, store.acquire_lease("exec-001", owner="worker-b", now_epoch=1200, lease_seconds=120))
        with self.assertRaises(ExecutionLeaseError):
            store.release_lease("exec-001", owner="worker-a")
        store.release_lease("exec-001", owner="worker-b")

    def test_command_is_idempotent_only_when_immutable_content_matches(self):
        client = FakeDynamoClient()
        store = DynamoGraphExecutionStore(config=self._config(), client=client)
        command = WorkCommand(
            work_id="work-001",
            execution_id="exec-sensitive-reference",
            work_type="business_operations",
            graph_id="business-operations",
            graph_version="0.1.0",
            action="start",
            data_class="operational",
            idempotency_key="request-001",
        )
        store.put_command(command, {"problem": "bounded request"})
        store.put_command(command, {"problem": "bounded request"})
        with self.assertRaises(DurableCommandConflictError):
            store.put_command(command, {"problem": "different request"})

    def test_fifo_queue_contains_pointer_only_and_loads_command_after_receive(self):
        client = FakeDynamoClient()
        store = DynamoGraphExecutionStore(config=self._config(), client=client)
        sqs = FakeSqsClient()
        queue = AwsDurableWorkQueue(store, config=self._config(), client=sqs)
        command = WorkCommand(
            work_id="work-002",
            execution_id="direct-execution-id-must-not-be-in-sqs",
            work_type="learner_execution",
            graph_id="learner-execution",
            graph_version="0.1.0",
            action="resume",
            data_class="learner_private",
            idempotency_key="review-command-001",
        )
        queue.enqueue(command, {"submission_id": "private-submission-reference"})
        body = sqs.sent[0]["MessageBody"]
        self.assertNotIn("direct-execution-id-must-not-be-in-sqs", body)
        self.assertNotIn("private-submission-reference", body)
        received = queue.receive()[0]
        self.assertEqual("private-submission-reference", received["command"]["payload"]["submission_id"])
        self.assertEqual(1, received["receive_count"])
        queue.extend_visibility(received["receipt_handle"], seconds=300)
        queue.acknowledge(received["receipt_handle"])
        self.assertEqual(1, len(sqs.visibility))
        self.assertEqual(1, len(sqs.deleted))

    def test_eventbridge_signal_excludes_direct_execution_identifier(self):
        client = FakeEventsClient()
        publisher = BoundedPlatformEventPublisher(config=self._config(), client=client)
        event_id = publisher.publish(
            event_type="graph.execution.failed",
            execution_id="private-execution-001",
            work_type="runtime_assurance",
            graph_id="runtime-assurance",
            status="failed",
        )
        self.assertEqual("event-001", event_id)
        detail = client.calls[0]["Detail"]
        self.assertNotIn("private-execution-001", detail)
        self.assertIn("execution_fingerprint", detail)

    def test_dynamo_assurance_source_releases_only_operational_execution_fields(self):
        client = FakeDynamoClient()
        store = DynamoGraphExecutionStore(config=self._config(), client=client)
        execution, ledger = self._execution()
        execution.status = "failed"
        execution.failure = "evaluation failed at assurance: blocked"
        execution.pending_approval = None
        store.save_execution(execution, ledger)
        rows = DynamoRuntimeExecutionSource(config=self._config(), client=client).read_rows()
        aggregate = aggregate_dynamo_execution_rows(rows)
        self.assertEqual(1, aggregate["execution_count"])
        self.assertEqual(1, aggregate["graphs"][0]["failed_count"])
        self.assertEqual({"evaluation_failure": 1}, aggregate["graphs"][0]["failure_categories"])
        base = {"graphs": [], "source_coverage": [{"store_kind": "generic_graph", "path_present": False}]}
        snapshot = apply_dynamo_executions_to_snapshot(base, aggregate)
        self.assertEqual("aws_dynamodb", snapshot["execution_state_source"])
        self.assertEqual("aws_generic_graph", snapshot["source_coverage"][0]["store_kind"])
        encoded = json.dumps(snapshot, sort_keys=True)
        self.assertNotIn("request", encoded)
        self.assertNotIn("private", encoded)
        self.assertEqual("ExecutionUpdatedIndex", client.query_calls[0]["IndexName"])

    def test_factory_keeps_local_default_and_requires_explicit_aws_enablement(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual("local", execution_backend())
            store = create_execution_store(local_path=":memory:")
            self.assertIsInstance(store, GraphExecutionStore)
        with patch.dict(os.environ, {AWS_EXECUTION_ENABLED_ENV: "true"}, clear=True):
            self.assertEqual("aws", execution_backend())

    def test_region_and_bounds_fail_closed(self):
        with patch.dict(os.environ, {"SOZOROCK_AWS_EXECUTION_REGION": "us-east-1"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "ca-central-1"):
                AwsDurableExecutionConfig.from_environment()
        with patch.dict(os.environ, {"SOZOROCK_AWS_EXECUTION_LEASE_SECONDS": "10"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "between 30 and 900"):
                AwsDurableExecutionConfig.from_environment()


if __name__ == "__main__":
    unittest.main()
