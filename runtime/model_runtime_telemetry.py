"""Privacy-bounded telemetry for OpenAI Agents SDK runtime work.

The collector records operational metadata, token usage, latency, trace linkage,
and optional pricing inputs. It never stores prompts, model outputs, learner
content, tool arguments, tool outputs, credentials, or trace payload bodies.
"""
from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


TELEMETRY_DB_ENV = "SOZOROCK_MODEL_TELEMETRY_DB"
MODEL_PRICING_ENV = "SOZOROCK_MODEL_PRICING_JSON"
TRACE_SENSITIVE_DATA_ENV = "OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA"
DEFAULT_TELEMETRY_DB = Path("local-data/model-telemetry.sqlite3")


@dataclass(frozen=True)
class ModelRuntimeContext:
    execution_id: str | None
    graph_id: str | None
    graph_version: str | None
    node_id: str | None
    actor_id: str


_CURRENT_CONTEXT: contextvars.ContextVar[ModelRuntimeContext | None] = contextvars.ContextVar(
    "sozorock_model_runtime_context",
    default=None,
)


@contextlib.contextmanager
def model_runtime_context(
    *,
    actor_id: str,
    execution_id: str | None = None,
    graph_id: str | None = None,
    graph_version: str | None = None,
    node_id: str | None = None,
) -> Iterator[None]:
    token = _CURRENT_CONTEXT.set(
        ModelRuntimeContext(
            execution_id=execution_id,
            graph_id=graph_id,
            graph_version=graph_version,
            node_id=node_id,
            actor_id=actor_id,
        )
    )
    try:
        yield
    finally:
        _CURRENT_CONTEXT.reset(token)


def current_model_runtime_context() -> ModelRuntimeContext | None:
    return _CURRENT_CONTEXT.get()


def telemetry_db_path() -> Path:
    value = os.getenv(TELEMETRY_DB_ENV, "").strip()
    return Path(value) if value else DEFAULT_TELEMETRY_DB


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fingerprint(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _duration_ms(started_at: str | None, ended_at: str | None) -> float | None:
    if not started_at or not ended_at:
        return None
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return round(max((end - start).total_seconds() * 1000.0, 0.0), 3)


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _usage_value(usage: dict[str, Any] | None, key: str) -> int:
    if not isinstance(usage, dict):
        return 0
    return _safe_int(usage.get(key))


def _nested_usage_value(usage: dict[str, Any] | None, section: str, key: str) -> int:
    if not isinstance(usage, dict):
        return 0
    detail = usage.get(section)
    if not isinstance(detail, dict):
        return 0
    return _safe_int(detail.get(key))


def _pricing(model: str | None, *, input_tokens: int, cached_tokens: int, output_tokens: int) -> dict[str, Any]:
    if not model:
        return {"pricing_status": "model_unavailable", "estimated_cost_usd": None}
    raw = os.getenv(MODEL_PRICING_ENV, "").strip()
    if not raw:
        return {"pricing_status": "unconfigured", "estimated_cost_usd": None}
    try:
        table = json.loads(raw)
        if not isinstance(table, dict):
            raise TypeError("pricing table must be an object")
        entry = table.get(model) or table.get("*")
        if not isinstance(entry, dict):
            return {"pricing_status": "model_unpriced", "estimated_cost_usd": None}
        input_rate = float(entry["input_per_million"])
        output_rate = float(entry["output_per_million"])
        cached_rate = float(entry.get("cached_input_per_million", input_rate))
        if min(input_rate, output_rate, cached_rate) < 0:
            raise ValueError("pricing rates cannot be negative")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {"pricing_status": "invalid_config", "estimated_cost_usd": None}

    uncached_tokens = max(input_tokens - cached_tokens, 0)
    estimated = (
        (uncached_tokens * input_rate)
        + (cached_tokens * cached_rate)
        + (output_tokens * output_rate)
    ) / 1_000_000.0
    return {
        "pricing_status": "estimated",
        "input_rate_per_million": input_rate,
        "cached_input_rate_per_million": cached_rate,
        "output_rate_per_million": output_rate,
        "estimated_cost_usd": round(estimated, 8),
    }


class ModelTelemetryStore:
    """Append privacy-safe trace and span facts to local SQLite."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else telemetry_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS model_traces (
                    trace_id TEXT PRIMARY KEY,
                    identity_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    sdk_name TEXT NOT NULL,
                    work_type TEXT NOT NULL,
                    graph_id TEXT,
                    graph_version TEXT,
                    execution_id TEXT,
                    execution_fingerprint TEXT,
                    node_id TEXT,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    latency_ms REAL,
                    span_count INTEGER NOT NULL DEFAULT 0,
                    generation_count INTEGER NOT NULL DEFAULT 0,
                    tool_span_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS model_spans (
                    span_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    span_type TEXT NOT NULL,
                    span_name TEXT,
                    model TEXT,
                    started_at TEXT,
                    ended_at TEXT,
                    latency_ms REAL,
                    requests INTEGER NOT NULL DEFAULT 0,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    cached_input_tokens INTEGER NOT NULL DEFAULT 0,
                    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
                    input_rate_per_million REAL,
                    cached_input_rate_per_million REAL,
                    output_rate_per_million REAL,
                    estimated_cost_usd REAL,
                    pricing_status TEXT NOT NULL,
                    error_present INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(trace_id) REFERENCES model_traces(trace_id)
                );
                CREATE INDEX IF NOT EXISTS idx_model_traces_work_type ON model_traces(work_type);
                CREATE INDEX IF NOT EXISTS idx_model_traces_execution ON model_traces(execution_id);
                CREATE INDEX IF NOT EXISTS idx_model_spans_trace ON model_spans(trace_id);
                CREATE INDEX IF NOT EXISTS idx_model_spans_type ON model_spans(span_type);
                """
            )

    def start_trace(self, trace: Any, context: ModelRuntimeContext, identity: Any) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO model_traces (
                    trace_id, identity_id, actor_id, sdk_name, work_type,
                    graph_id, graph_version, execution_id, execution_fingerprint,
                    node_id, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(trace.trace_id),
                    identity.identity_id,
                    identity.actor_id,
                    identity.sdk_name,
                    identity.work_type,
                    context.graph_id,
                    context.graph_version,
                    context.execution_id,
                    _fingerprint(context.execution_id),
                    context.node_id,
                    _now_iso(),
                ),
            )

    def end_trace(self, trace_id: str, *, started_monotonic: float | None) -> None:
        ended = _now_iso()
        elapsed = round((time.monotonic() - started_monotonic) * 1000.0, 3) if started_monotonic is not None else None
        with self._connect() as connection:
            connection.execute(
                "UPDATE model_traces SET ended_at = ?, latency_ms = ? WHERE trace_id = ?",
                (ended, elapsed, trace_id),
            )

    def record_span(self, span: Any) -> None:
        trace_id = str(getattr(span, "trace_id", "") or "")
        span_id = str(getattr(span, "span_id", "") or "")
        if not trace_id or not span_id:
            return
        data = getattr(span, "span_data", None)
        span_type = str(getattr(data, "type", "unknown") or "unknown")
        span_name: str | None = None
        model: str | None = None
        if span_type in {"agent", "function", "task"}:
            value = getattr(data, "name", None)
            span_name = str(value) if value else None
        elif span_type == "generation":
            value = getattr(data, "model", None)
            model = str(value) if value else None
            span_name = "model_generation"
        elif span_type == "response":
            span_name = "openai_response"
        elif span_type == "mcp_tools":
            span_name = "mcp_tools"

        usage = getattr(data, "usage", None)
        if not isinstance(usage, dict):
            usage = None
        requests = _usage_value(usage, "requests")
        input_tokens = _usage_value(usage, "input_tokens")
        output_tokens = _usage_value(usage, "output_tokens")
        total_tokens = _usage_value(usage, "total_tokens")
        cached_tokens = _nested_usage_value(usage, "input_tokens_details", "cached_tokens")
        reasoning_tokens = _nested_usage_value(usage, "output_tokens_details", "reasoning_tokens")
        pricing = _pricing(
            model,
            input_tokens=input_tokens,
            cached_tokens=cached_tokens,
            output_tokens=output_tokens,
        )
        started_at = getattr(span, "started_at", None)
        ended_at = getattr(span, "ended_at", None)
        latency_ms = _duration_ms(started_at, ended_at)
        error_present = 1 if getattr(span, "error", None) is not None else 0

        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO model_spans (
                    span_id, trace_id, span_type, span_name, model, started_at,
                    ended_at, latency_ms, requests, input_tokens, output_tokens,
                    total_tokens, cached_input_tokens, reasoning_tokens,
                    input_rate_per_million, cached_input_rate_per_million,
                    output_rate_per_million, estimated_cost_usd, pricing_status,
                    error_present
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    span_id,
                    trace_id,
                    span_type,
                    span_name,
                    model,
                    started_at,
                    ended_at,
                    latency_ms,
                    requests,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                    cached_tokens,
                    reasoning_tokens,
                    pricing.get("input_rate_per_million"),
                    pricing.get("cached_input_rate_per_million"),
                    pricing.get("output_rate_per_million"),
                    pricing.get("estimated_cost_usd"),
                    pricing["pricing_status"],
                    error_present,
                ),
            )
            connection.execute(
                """
                UPDATE model_traces
                SET span_count = span_count + 1,
                    generation_count = generation_count + ?,
                    tool_span_count = tool_span_count + ?
                WHERE trace_id = ?
                """,
                (
                    1 if span_type == "generation" else 0,
                    1 if span_type in {"function", "mcp_tools"} else 0,
                    trace_id,
                ),
            )


class PrivacySafeTelemetryProcessor:
    """Secondary SDK tracing processor that stores no trace payload bodies."""

    def __init__(self, store: ModelTelemetryStore | None = None) -> None:
        self.store = store or ModelTelemetryStore()
        self._tracked: dict[str, float] = {}
        self._lock = threading.RLock()

    def on_trace_start(self, trace: Any) -> None:
        context = current_model_runtime_context()
        if context is None:
            return
        try:
            from runtime.agent_identity_registry import identity_for_actor

            identity = identity_for_actor(context.actor_id)
            self.store.start_trace(trace, context, identity)
            with self._lock:
                self._tracked[str(trace.trace_id)] = time.monotonic()
        except Exception:
            return

    def on_trace_end(self, trace: Any) -> None:
        trace_id = str(getattr(trace, "trace_id", "") or "")
        if not trace_id:
            return
        with self._lock:
            started = self._tracked.pop(trace_id, None)
        if started is None:
            return
        try:
            self.store.end_trace(trace_id, started_monotonic=started)
        except Exception:
            return

    def on_span_start(self, span: Any) -> None:
        return None

    def on_span_end(self, span: Any) -> None:
        trace_id = str(getattr(span, "trace_id", "") or "")
        with self._lock:
            tracked = trace_id in self._tracked
        if not tracked:
            return
        try:
            self.store.record_span(span)
        except Exception:
            return

    def shutdown(self) -> None:
        with self._lock:
            self._tracked.clear()

    def force_flush(self) -> None:
        return None


_INSTALL_LOCK = threading.Lock()
_INSTALLED = False
_PROCESSOR: PrivacySafeTelemetryProcessor | None = None


def install_model_runtime_telemetry() -> None:
    """Install one privacy-safe secondary tracing processor per process."""

    global _INSTALLED, _PROCESSOR
    if _INSTALLED:
        return
    with _INSTALL_LOCK:
        if _INSTALLED:
            return
        # This platform never permits prompt, output, or tool payload bodies in SDK traces.
        os.environ[TRACE_SENSITIVE_DATA_ENV] = "0"
        try:
            from agents import add_trace_processor

            _PROCESSOR = PrivacySafeTelemetryProcessor()
            add_trace_processor(_PROCESSOR)
            _INSTALLED = True
        except Exception:
            # Telemetry must never widen authority or prevent deterministic test fixtures
            # from loading. Live provider paths still operate, while Runtime Assurance
            # reports missing telemetry coverage.
            _PROCESSOR = None
            _INSTALLED = False
