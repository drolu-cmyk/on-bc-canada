"""Strict production wrapper around the low-level DynamoDB graph store."""
from __future__ import annotations

from typing import Any

from runtime.aws_durable_execution import DynamoGraphExecutionStore, ExecutionConflictError
from runtime.control_plane import EventLedger
from runtime.graph_kernel import GraphExecution


class DurableGraphExecutionStore(DynamoGraphExecutionStore):
    """Prevent a fresh process from overwriting an execution it never loaded."""

    def save_execution(
        self,
        execution: GraphExecution,
        ledger: EventLedger,
        *,
        terminal_records: dict[str, Any] | None = None,
    ) -> None:
        existing = self._state_item(execution.execution_id)
        if existing is not None and execution.execution_id not in self._revisions:
            raise ExecutionConflictError(
                f"existing execution must be loaded before update: {execution.execution_id}"
            )
        super().save_execution(execution, ledger, terminal_records=terminal_records)
