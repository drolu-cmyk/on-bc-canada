"""SQLite persistence for research graph executions and validated findings."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.control_plane import EventLedger
from runtime.graph_kernel import GraphExecution


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class ResearchStore:
    """Persist graph state without storing API credentials or direct learner identity."""

    STORE_VERSION = "0.1.0"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_executions (
                    execution_id TEXT PRIMARY KEY,
                    graph_id TEXT NOT NULL,
                    graph_version TEXT NOT NULL,
                    current_node TEXT NOT NULL,
                    status TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    history_json TEXT NOT NULL,
                    checkpoints_json TEXT NOT NULL,
                    pending_approval_json TEXT,
                    failure TEXT,
                    events_json TEXT NOT NULL,
                    store_version TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_findings (
                    execution_id TEXT PRIMARY KEY,
                    finding_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY(execution_id) REFERENCES research_executions(execution_id)
                );
                """
            )

    def save_execution(self, execution: GraphExecution, ledger: EventLedger) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO research_executions (
                    execution_id, graph_id, graph_version, current_node, status,
                    state_json, history_json, checkpoints_json, pending_approval_json,
                    failure, events_json, store_version, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(execution_id) DO UPDATE SET
                    graph_id=excluded.graph_id,
                    graph_version=excluded.graph_version,
                    current_node=excluded.current_node,
                    status=excluded.status,
                    state_json=excluded.state_json,
                    history_json=excluded.history_json,
                    checkpoints_json=excluded.checkpoints_json,
                    pending_approval_json=excluded.pending_approval_json,
                    failure=excluded.failure,
                    events_json=excluded.events_json,
                    store_version=excluded.store_version,
                    updated_at=excluded.updated_at
                """,
                (
                    execution.execution_id,
                    execution.graph_id,
                    execution.graph_version,
                    execution.current_node,
                    execution.status,
                    _dumps(execution.state),
                    _dumps(execution.history),
                    _dumps(execution.checkpoints),
                    _dumps(execution.pending_approval) if execution.pending_approval is not None else None,
                    execution.failure,
                    _dumps(ledger.events),
                    self.STORE_VERSION,
                    _utc_now(),
                ),
            )
            finding = execution.state.get("finding")
            if execution.status == "completed" and finding is not None:
                connection.execute(
                    """
                    INSERT INTO research_findings (execution_id, finding_json, recorded_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(execution_id) DO UPDATE SET
                        finding_json=excluded.finding_json,
                        recorded_at=excluded.recorded_at
                    """,
                    (execution.execution_id, _dumps(finding), _utc_now()),
                )

    def load_execution(self, execution_id: str) -> tuple[GraphExecution, EventLedger]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM research_executions WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"research execution not found: {execution_id}")
        events = json.loads(row["events_json"])
        ledger = EventLedger(
            events=events,
            idempotency_keys={event["idempotency_key"]: event["event_id"] for event in events},
        )
        execution = GraphExecution(
            execution_id=row["execution_id"],
            graph_id=row["graph_id"],
            graph_version=row["graph_version"],
            current_node=row["current_node"],
            state=json.loads(row["state_json"]),
            status=row["status"],
            history=json.loads(row["history_json"]),
            checkpoints=json.loads(row["checkpoints_json"]),
            pending_approval=json.loads(row["pending_approval_json"]) if row["pending_approval_json"] else None,
            failure=row["failure"],
        )
        return execution, ledger

    def get_finding(self, execution_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT finding_json FROM research_findings WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
        return json.loads(row["finding_json"]) if row else None
