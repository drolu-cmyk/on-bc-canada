"""AWS durable execution primitives for governed graph work.

This module preserves the existing graph-store contract while adding optimistic
concurrency, append-only event mirrors, execution leases, pointer-only SQS work
messages, and bounded EventBridge signals. It does not execute graphs or models.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from botocore.exceptions import ClientError

from runtime.control_plane import EventLedger
from runtime.graph_kernel import GraphExecution


AWS_EXECUTION_REGION_ENV = "SOZOROCK_AWS_EXECUTION_REGION"
AWS_EXECUTION_TABLE_ENV = "SOZOROCK_AWS_EXECUTION_TABLE"
AWS_EXECUTION_QUEUE_URL_ENV = "SOZOROCK_AWS_EXECUTION_QUEUE_URL"
AWS_EXECUTION_EVENT_BUS_ENV = "SOZOROCK_AWS_EXECUTION_EVENT_BUS"
AWS_EXECUTION_ENABLED_ENV = "SOZOROCK_AWS_EXECUTION_ENABLED"
AWS_EXECUTION_COMMAND_TTL_DAYS_ENV = "SOZOROCK_AWS_EXECUTION_COMMAND_TTL_DAYS"
AWS_EXECUTION_LEASE_SECONDS_ENV = "SOZOROCK_AWS_EXECUTION_LEASE_SECONDS"

DEFAULT_REGION = "ca-central-1"
DEFAULT_TABLE = "sozorock-ca-graph-executions"
DEFAULT_EVENT_BUS = "sozorock-ca-platform-events"
DEFAULT_COMMAND_TTL_DAYS = 14
DEFAULT_LEASE_SECONDS = 120
STORE_VERSION = "0.2.0"

ALLOWED_WORK_TYPES = frozenset(
    {
        "research_intelligence",
        "product_development",
        "business_operations",
        "learner_execution",
        "career_mobility",
        "employer_workforce",
        "outcomes_intelligence",
        "runtime_assurance",
    }
)
ALLOWED_ACTIONS = frozenset({"start", "resume"})
ALLOWED_DATA_CLASSES = frozenset({"operational", "learner_private", "employer_private"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _s(value: str) -> dict[str, str]:
    return {"S": str(value)}


def _n(value: int | float) -> dict[str, str]:
    return {"N": str(value)}


def _read_s(item: dict[str, Any], key: str, default: str | None = None) -> str | None:
    raw = item.get(key)
    return raw.get("S") if isinstance(raw, dict) and "S" in raw else default


def _read_n(item: dict[str, Any], key: str, default: int = 0) -> int:
    raw = item.get(key)
    if not isinstance(raw, dict) or "N" not in raw:
        return default
    return int(raw["N"])


def _client_error_code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


class ExecutionConflictError(RuntimeError):
    """Raised when optimistic execution state concurrency fails."""


class ExecutionLeaseError(RuntimeError):
    """Raised when an execution lease cannot be acquired or released."""


class DurableCommandConflictError(RuntimeError):
    """Raised when a work ID is reused with different immutable command data."""


@dataclass(frozen=True)
class AwsDurableExecutionConfig:
    region: str = DEFAULT_REGION
    table_name: str = DEFAULT_TABLE
    queue_url: str = ""
    event_bus_name: str = DEFAULT_EVENT_BUS
    command_ttl_days: int = DEFAULT_COMMAND_TTL_DAYS
    lease_seconds: int = DEFAULT_LEASE_SECONDS

    @classmethod
    def from_environment(cls) -> "AwsDurableExecutionConfig":
        ttl = int(os.getenv(AWS_EXECUTION_COMMAND_TTL_DAYS_ENV, str(DEFAULT_COMMAND_TTL_DAYS)))
        lease = int(os.getenv(AWS_EXECUTION_LEASE_SECONDS_ENV, str(DEFAULT_LEASE_SECONDS)))
        if not 1 <= ttl <= 30:
            raise RuntimeError("SOZOROCK_AWS_EXECUTION_COMMAND_TTL_DAYS must be between 1 and 30")
        if not 30 <= lease <= 900:
            raise RuntimeError("SOZOROCK_AWS_EXECUTION_LEASE_SECONDS must be between 30 and 900")
        region = os.getenv(AWS_EXECUTION_REGION_ENV, DEFAULT_REGION).strip() or DEFAULT_REGION
        if region != DEFAULT_REGION:
            raise RuntimeError("durable execution data must remain in ca-central-1")
        return cls(
            region=region,
            table_name=os.getenv(AWS_EXECUTION_TABLE_ENV, DEFAULT_TABLE).strip() or DEFAULT_TABLE,
            queue_url=os.getenv(AWS_EXECUTION_QUEUE_URL_ENV, "").strip(),
            event_bus_name=os.getenv(AWS_EXECUTION_EVENT_BUS_ENV, DEFAULT_EVENT_BUS).strip() or DEFAULT_EVENT_BUS,
            command_ttl_days=ttl,
            lease_seconds=lease,
        )


def aws_execution_enabled() -> bool:
    return os.getenv(AWS_EXECUTION_ENABLED_ENV, "").strip().casefold() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class WorkCommand:
    work_id: str
    execution_id: str
    work_type: str
    graph_id: str
    graph_version: str
    action: str
    data_class: str
    idempotency_key: str

    def validate(self) -> None:
        for field_name in ("work_id", "execution_id", "graph_id", "graph_version", "idempotency_key"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} is required")
        if self.work_type not in ALLOWED_WORK_TYPES:
            raise ValueError("work_type is not registered for durable execution")
        if self.action not in ALLOWED_ACTIONS:
            raise ValueError("action must be start or resume")
        if self.data_class not in ALLOWED_DATA_CLASSES:
            raise ValueError("unsupported durable command data_class")

    def pointer_message(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": "1.0",
            "work_id": self.work_id,
            "execution_fingerprint": _fingerprint(self.execution_id),
            "work_type": self.work_type,
            "graph_id": self.graph_id,
            "graph_version": self.graph_version,
            "action": self.action,
            "command_fingerprint": _fingerprint(self.idempotency_key),
        }


class DynamoGraphExecutionStore:
    """DynamoDB implementation of the generic graph execution store contract."""

    def __init__(
        self,
        *,
        config: AwsDurableExecutionConfig | None = None,
        client: Any | None = None,
    ) -> None:
        self.config = config or AwsDurableExecutionConfig.from_environment()
        if client is None:
            import boto3

            client = boto3.client("dynamodb", region_name=self.config.region)
        self.client = client
        self._revisions: dict[str, int] = {}

    @staticmethod
    def _key(execution_id: str, sort_key: str) -> dict[str, Any]:
        return {"pk": _s(f"EXEC#{execution_id}"), "sk": _s(sort_key)}

    def _state_item(self, execution_id: str) -> dict[str, Any] | None:
        response = self.client.get_item(
            TableName=self.config.table_name,
            Key=self._key(execution_id, "STATE"),
            ConsistentRead=True,
        )
        item = response.get("Item")
        return item if isinstance(item, dict) else None

    def save_execution(
        self,
        execution: GraphExecution,
        ledger: EventLedger,
        *,
        terminal_records: dict[str, Any] | None = None,
    ) -> None:
        existing = self._state_item(execution.execution_id)
        observed_revision = _read_n(existing, "revision", 0) if existing else 0
        expected_revision = self._revisions.get(execution.execution_id, observed_revision)
        new_revision = expected_revision + 1
        values: dict[str, Any] = {
            ":graph_id": _s(execution.graph_id),
            ":graph_version": _s(execution.graph_version),
            ":current_node": _s(execution.current_node),
            ":status": _s(execution.status),
            ":state": _s(_canonical(execution.state)),
            ":history": _s(_canonical(execution.history)),
            ":checkpoints": _s(_canonical(execution.checkpoints)),
            ":events": _s(_canonical(ledger.events)),
            ":store_version": _s(STORE_VERSION),
            ":updated": _s(_utc_now()),
            ":revision": _n(new_revision),
        }
        pending_expression = "REMOVE pending_approval_json, failure"
        if execution.pending_approval is not None:
            values[":pending"] = _s(_canonical(execution.pending_approval))
            pending_expression = "SET pending_approval_json = :pending REMOVE failure"
        if execution.failure is not None:
            values[":failure"] = _s(str(execution.failure))
            pending_expression = "SET failure = :failure REMOVE pending_approval_json"

        update = (
            "SET graph_id = :graph_id, graph_version = :graph_version, current_node = :current_node, "
            "#execution_status = :status, state_json = :state, history_json = :history, "
            "checkpoints_json = :checkpoints, events_json = :events, store_version = :store_version, "
            "updated_at = :updated, revision = :revision "
        )
        if pending_expression.startswith("SET "):
            update += ", " + pending_expression[4:pending_expression.index(" REMOVE")]
            update += pending_expression[pending_expression.index(" REMOVE"):]
        else:
            update += pending_expression

        condition = "attribute_not_exists(revision)" if existing is None else "revision = :expected_revision"
        if existing is not None:
            values[":expected_revision"] = _n(expected_revision)
        try:
            self.client.update_item(
                TableName=self.config.table_name,
                Key=self._key(execution.execution_id, "STATE"),
                UpdateExpression=update,
                ConditionExpression=condition,
                ExpressionAttributeNames={"#execution_status": "status"},
                ExpressionAttributeValues=values,
            )
        except ClientError as exc:
            if _client_error_code(exc) == "ConditionalCheckFailedException":
                raise ExecutionConflictError(
                    f"execution revision conflict: {execution.execution_id} expected {expected_revision}"
                ) from exc
            raise
        self._revisions[execution.execution_id] = new_revision
        self._mirror_events(execution.execution_id, ledger.events)
        if execution.status == "completed" and terminal_records:
            for record_kind, record in terminal_records.items():
                self._write_terminal_record(execution.execution_id, record_kind, record)

    def _mirror_events(self, execution_id: str, events: list[dict[str, Any]]) -> None:
        for event in events:
            event_id = str(event.get("event_id", "")).strip()
            if not event_id:
                raise ValueError("event ledger record is missing event_id")
            item = {
                **self._key(execution_id, f"EVENT#{event_id}"),
                "record_type": _s("event"),
                "event_id": _s(event_id),
                "event_json": _s(_canonical(event)),
                "event_hash": _s(str(event.get("integrity", {}).get("event_hash", ""))),
                "idempotency_key": _s(str(event.get("idempotency_key", ""))),
                "recorded_at": _s(str(event.get("occurred_at") or _utc_now())),
            }
            try:
                self.client.put_item(
                    TableName=self.config.table_name,
                    Item=item,
                    ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
                )
            except ClientError as exc:
                if _client_error_code(exc) != "ConditionalCheckFailedException":
                    raise
                existing = self.client.get_item(
                    TableName=self.config.table_name,
                    Key=self._key(execution_id, f"EVENT#{event_id}"),
                    ConsistentRead=True,
                ).get("Item") or {}
                if _read_s(existing, "event_json") != item["event_json"]["S"]:
                    raise ExecutionConflictError(f"event ID collision with different content: {event_id}") from exc

    def _write_terminal_record(self, execution_id: str, record_kind: str, record: Any) -> None:
        record_json = _canonical(record)
        item = {
            **self._key(execution_id, f"TERM#{record_kind}"),
            "record_type": _s("terminal"),
            "record_kind": _s(record_kind),
            "record_json": _s(record_json),
            "recorded_at": _s(_utc_now()),
        }
        try:
            self.client.put_item(
                TableName=self.config.table_name,
                Item=item,
                ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
            )
        except ClientError as exc:
            if _client_error_code(exc) != "ConditionalCheckFailedException":
                raise
            existing = self.client.get_item(
                TableName=self.config.table_name,
                Key=self._key(execution_id, f"TERM#{record_kind}"),
                ConsistentRead=True,
            ).get("Item") or {}
            if _read_s(existing, "record_json") != record_json:
                raise ExecutionConflictError(
                    f"terminal record is immutable after completion: {execution_id}/{record_kind}"
                ) from exc

    def load_execution(self, execution_id: str) -> tuple[GraphExecution, EventLedger]:
        item = self._state_item(execution_id)
        if item is None:
            raise KeyError(f"graph execution not found: {execution_id}")
        events = json.loads(_read_s(item, "events_json", "[]") or "[]")
        ledger = EventLedger(
            events=events,
            idempotency_keys={event["idempotency_key"]: event["event_id"] for event in events},
        )
        execution = GraphExecution(
            execution_id=execution_id,
            graph_id=_read_s(item, "graph_id", "") or "",
            graph_version=_read_s(item, "graph_version", "") or "",
            current_node=_read_s(item, "current_node", "") or "",
            state=json.loads(_read_s(item, "state_json", "{}") or "{}"),
            status=_read_s(item, "status", "ready") or "ready",
            history=json.loads(_read_s(item, "history_json", "[]") or "[]"),
            checkpoints=json.loads(_read_s(item, "checkpoints_json", "[]") or "[]"),
            pending_approval=(
                json.loads(_read_s(item, "pending_approval_json", "null") or "null")
                if _read_s(item, "pending_approval_json") is not None
                else None
            ),
            failure=_read_s(item, "failure"),
        )
        self._revisions[execution_id] = _read_n(item, "revision", 0)
        return execution, ledger

    def get_terminal_record(self, execution_id: str, record_kind: str) -> dict[str, Any] | None:
        response = self.client.get_item(
            TableName=self.config.table_name,
            Key=self._key(execution_id, f"TERM#{record_kind}"),
            ConsistentRead=True,
        )
        item = response.get("Item") or {}
        raw = _read_s(item, "record_json")
        return json.loads(raw) if raw else None

    def acquire_lease(
        self,
        execution_id: str,
        *,
        owner: str,
        now_epoch: int | None = None,
        lease_seconds: int | None = None,
    ) -> int:
        now = int(now_epoch if now_epoch is not None else time.time())
        duration = int(lease_seconds or self.config.lease_seconds)
        expires = now + duration
        if not owner.strip():
            raise ValueError("lease owner is required")
        try:
            self.client.update_item(
                TableName=self.config.table_name,
                Key=self._key(execution_id, "STATE"),
                UpdateExpression="SET lease_owner = :owner, lease_expires_at = :expires, lease_acquired_at = :now",
                ConditionExpression=(
                    "attribute_exists(pk) AND (attribute_not_exists(lease_expires_at) "
                    "OR lease_expires_at < :now OR lease_owner = :owner)"
                ),
                ExpressionAttributeValues={
                    ":owner": _s(owner),
                    ":expires": _n(expires),
                    ":now": _n(now),
                },
            )
        except ClientError as exc:
            if _client_error_code(exc) == "ConditionalCheckFailedException":
                raise ExecutionLeaseError(f"execution lease unavailable: {execution_id}") from exc
            raise
        return expires

    def release_lease(self, execution_id: str, *, owner: str) -> None:
        try:
            self.client.update_item(
                TableName=self.config.table_name,
                Key=self._key(execution_id, "STATE"),
                UpdateExpression="REMOVE lease_owner, lease_expires_at, lease_acquired_at",
                ConditionExpression="lease_owner = :owner",
                ExpressionAttributeValues={":owner": _s(owner)},
            )
        except ClientError as exc:
            if _client_error_code(exc) == "ConditionalCheckFailedException":
                raise ExecutionLeaseError(f"execution lease owner mismatch: {execution_id}") from exc
            raise

    def put_command(self, command: WorkCommand, payload: dict[str, Any]) -> None:
        command.validate()
        now = int(time.time())
        expires = now + (self.config.command_ttl_days * 86400)
        command_json = _canonical(
            {
                "work_id": command.work_id,
                "execution_id": command.execution_id,
                "work_type": command.work_type,
                "graph_id": command.graph_id,
                "graph_version": command.graph_version,
                "action": command.action,
                "data_class": command.data_class,
                "idempotency_key": command.idempotency_key,
                "payload": payload,
            }
        )
        key = {"pk": _s(f"WORK#{command.work_id}"), "sk": _s("COMMAND")}
        item = {
            **key,
            "record_type": _s("command"),
            "command_json": _s(command_json),
            "command_fingerprint": _s(_fingerprint(command.idempotency_key)),
            "data_class": _s(command.data_class),
            "status": _s("queued"),
            "created_at": _s(_utc_now()),
            "expires_at_epoch": _n(expires),
        }
        try:
            self.client.put_item(
                TableName=self.config.table_name,
                Item=item,
                ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
            )
        except ClientError as exc:
            if _client_error_code(exc) != "ConditionalCheckFailedException":
                raise
            existing = self.client.get_item(
                TableName=self.config.table_name,
                Key=key,
                ConsistentRead=True,
            ).get("Item") or {}
            if _read_s(existing, "command_json") != command_json:
                raise DurableCommandConflictError(f"work_id reused with different command: {command.work_id}") from exc

    def load_command(self, work_id: str) -> dict[str, Any]:
        response = self.client.get_item(
            TableName=self.config.table_name,
            Key={"pk": _s(f"WORK#{work_id}"), "sk": _s("COMMAND")},
            ConsistentRead=True,
        )
        item = response.get("Item") or {}
        raw = _read_s(item, "command_json")
        if not raw:
            raise KeyError(f"durable command not found: {work_id}")
        return json.loads(raw)

    def mark_command_status(self, work_id: str, status: str) -> None:
        if status not in {"queued", "running", "completed", "failed"}:
            raise ValueError("unsupported durable command status")
        self.client.update_item(
            TableName=self.config.table_name,
            Key={"pk": _s(f"WORK#{work_id}"), "sk": _s("COMMAND")},
            UpdateExpression="SET #command_status = :status, updated_at = :updated",
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeNames={"#command_status": "status"},
            ExpressionAttributeValues={":status": _s(status), ":updated": _s(_utc_now())},
        )


class AwsDurableWorkQueue:
    """FIFO pointer queue; sensitive command payload remains in encrypted DynamoDB."""

    def __init__(
        self,
        store: DynamoGraphExecutionStore,
        *,
        config: AwsDurableExecutionConfig | None = None,
        client: Any | None = None,
    ) -> None:
        self.store = store
        self.config = config or store.config
        if not self.config.queue_url:
            raise RuntimeError("SOZOROCK_AWS_EXECUTION_QUEUE_URL is required for durable work delivery")
        if client is None:
            import boto3

            client = boto3.client("sqs", region_name=self.config.region)
        self.client = client

    def enqueue(self, command: WorkCommand, payload: dict[str, Any]) -> dict[str, Any]:
        command.validate()
        self.store.put_command(command, payload)
        pointer = command.pointer_message()
        response = self.client.send_message(
            QueueUrl=self.config.queue_url,
            MessageBody=_canonical(pointer),
            MessageGroupId=_fingerprint(command.execution_id),
            MessageDeduplicationId=_fingerprint(command.idempotency_key),
        )
        return {
            "work_id": command.work_id,
            "message_id": response.get("MessageId"),
            "execution_fingerprint": pointer["execution_fingerprint"],
        }

    def receive(self, *, max_messages: int = 1, visibility_timeout: int | None = None) -> list[dict[str, Any]]:
        if not 1 <= max_messages <= 10:
            raise ValueError("max_messages must be between 1 and 10")
        response = self.client.receive_message(
            QueueUrl=self.config.queue_url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=20,
            VisibilityTimeout=int(visibility_timeout or self.config.lease_seconds),
            AttributeNames=["ApproximateReceiveCount"],
        )
        messages: list[dict[str, Any]] = []
        for raw in response.get("Messages", []):
            pointer = json.loads(raw.get("Body") or "{}")
            work_id = str(pointer.get("work_id", ""))
            if not work_id:
                continue
            messages.append(
                {
                    "work_id": work_id,
                    "pointer": pointer,
                    "command": self.store.load_command(work_id),
                    "receipt_handle": raw.get("ReceiptHandle"),
                    "receive_count": int((raw.get("Attributes") or {}).get("ApproximateReceiveCount", "1")),
                }
            )
        return messages

    def acknowledge(self, receipt_handle: str) -> None:
        if not receipt_handle:
            raise ValueError("receipt_handle is required")
        self.client.delete_message(QueueUrl=self.config.queue_url, ReceiptHandle=receipt_handle)

    def extend_visibility(self, receipt_handle: str, *, seconds: int) -> None:
        if not 0 <= seconds <= 43200:
            raise ValueError("visibility timeout must be between 0 and 43200 seconds")
        self.client.change_message_visibility(
            QueueUrl=self.config.queue_url,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=seconds,
        )


class BoundedPlatformEventPublisher:
    """Publish non-sensitive execution pointers to the custom EventBridge bus."""

    ALLOWED_EVENT_TYPES = frozenset(
        {
            "graph.execution.queued",
            "graph.execution.completed",
            "graph.execution.failed",
            "graph.approval.requested",
            "graph.execution.retry_exhausted",
        }
    )

    def __init__(
        self,
        *,
        config: AwsDurableExecutionConfig | None = None,
        client: Any | None = None,
    ) -> None:
        self.config = config or AwsDurableExecutionConfig.from_environment()
        if client is None:
            import boto3

            client = boto3.client("events", region_name=self.config.region)
        self.client = client

    def publish(
        self,
        *,
        event_type: str,
        execution_id: str,
        work_type: str,
        graph_id: str,
        status: str,
    ) -> str | None:
        if event_type not in self.ALLOWED_EVENT_TYPES:
            raise ValueError("event type is not allowed on the durable platform bus")
        if work_type not in ALLOWED_WORK_TYPES:
            raise ValueError("unknown work_type")
        detail = {
            "schema_version": "1.0",
            "execution_fingerprint": _fingerprint(execution_id),
            "work_type": work_type,
            "graph_id": graph_id,
            "status": status,
        }
        response = self.client.put_events(
            Entries=[
                {
                    "Source": "sozorock.canada.platform",
                    "DetailType": event_type,
                    "Detail": _canonical(detail),
                    "EventBusName": self.config.event_bus_name,
                }
            ]
        )
        if int(response.get("FailedEntryCount", 0)):
            raise RuntimeError("EventBridge rejected durable platform event")
        entries = response.get("Entries") or []
        return entries[0].get("EventId") if entries else None
