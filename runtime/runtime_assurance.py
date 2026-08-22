"""Aggregate runtime assurance telemetry from durable platform stores.

The builder releases only operational aggregates. It never returns prompts, model
outputs, raw graph state, learner records, credentials, tool arguments, or tool
outputs. Missing telemetry remains explicit rather than being inferred as healthy.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.agent_identity_registry import disabled_agent_tokens, disabled_work_types


@dataclass(frozen=True)
class RuntimeStoreSource:
    path: str | Path
    store_kind: str


class RuntimeAssuranceSnapshotBuilder:
    def __init__(
        self,
        sources: tuple[RuntimeStoreSource, ...],
        *,
        model_telemetry_path: str | Path | None = None,
    ) -> None:
        self.sources = sources
        self.model_telemetry_path = Path(model_telemetry_path) if model_telemetry_path is not None else None

    def build(self) -> dict[str, Any]:
        graph_metrics: dict[str, dict[str, Any]] = {}
        coverage: list[dict[str, Any]] = []
        for source in self.sources:
            path = Path(source.path)
            if not path.exists():
                coverage.append({"store_kind": source.store_kind, "path_present": False})
                continue
            if source.store_kind == "generic_graph":
                rows = self._read_generic(path)
            elif source.store_kind == "research":
                rows = self._read_research(path)
            else:
                raise ValueError(f"unsupported runtime store kind: {source.store_kind}")
            coverage.append({"store_kind": source.store_kind, "path_present": True, "execution_count": len(rows)})
            for row in rows:
                self._accumulate(graph_metrics, row)

        graphs: list[dict[str, Any]] = []
        for graph_id in sorted(graph_metrics):
            metric = graph_metrics[graph_id]
            executions = metric["execution_count"]
            graphs.append(
                {
                    "graph_id": graph_id,
                    "versions": sorted(metric["versions"]),
                    "execution_count": executions,
                    "completed_count": metric["completed_count"],
                    "failed_count": metric["failed_count"],
                    "waiting_approval_count": metric["waiting_approval_count"],
                    "completed_node_count": metric["completed_node_count"],
                    "event_count": metric["event_count"],
                    "failure_categories": dict(sorted(metric["failure_categories"].items())),
                    "completion_rate": round(metric["completed_count"] / executions, 4) if executions else None,
                    "failure_rate": round(metric["failed_count"] / executions, 4) if executions else None,
                    "human_review_rate": round(metric["waiting_approval_count"] / executions, 4) if executions else None,
                    "average_completed_node_count": round(metric["completed_node_count"] / executions, 2) if executions else None,
                }
            )

        model_runtime = self._read_model_telemetry(self.model_telemetry_path)
        telemetry_present = bool(model_runtime.get("path_present")) and bool(model_runtime.get("trace_count"))
        generation_count = int(model_runtime.get("generation_count") or 0)
        priced_generation_count = int(model_runtime.get("priced_generation_count") or 0)
        tool_span_count = int(model_runtime.get("tool_span_count") or 0)

        return {
            "snapshot_version": "0.2.0",
            "graphs": graphs,
            "source_coverage": coverage,
            "model_runtime": model_runtime,
            "runtime_controls": {
                "disabled_agent_token_count": len(disabled_agent_tokens()),
                "disabled_work_types": sorted(disabled_work_types()),
            },
            "telemetry_coverage": {
                "execution_status": True,
                "graph_version": True,
                "node_completion": True,
                "human_approval_state": True,
                "failure_reason_category": True,
                "event_count": True,
                "model_token_usage": telemetry_present and generation_count > 0,
                "model_monetary_cost": generation_count > 0 and priced_generation_count == generation_count,
                "provider_latency": telemetry_present,
                "tool_call_latency": tool_span_count > 0,
                "trace_sampling": telemetry_present,
                "hosted_tool_latency": False,
            },
            "model_boundary": {
                "contains_learner_identity": False,
                "contains_raw_graph_state": False,
                "contains_prompts_or_model_outputs": False,
                "contains_tool_arguments_or_outputs": False,
                "contains_credentials": False,
            },
        }

    @staticmethod
    def _read_generic(path: Path) -> list[dict[str, Any]]:
        with sqlite3.connect(path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT graph_id, graph_version, status, failure, history_json,
                       pending_approval_json, events_json
                FROM graph_executions
                """
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _read_research(path: Path) -> list[dict[str, Any]]:
        with sqlite3.connect(path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT graph_id, graph_version, status, failure, history_json,
                       pending_approval_json, events_json
                FROM research_executions
                """
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _read_model_telemetry(path: Path | None) -> dict[str, Any]:
        if path is None:
            return {"path_present": False, "reason": "telemetry_path_not_configured", "workflows": []}
        if not path.exists():
            return {"path_present": False, "reason": "telemetry_store_not_found", "workflows": []}
        try:
            with sqlite3.connect(path) as connection:
                connection.row_factory = sqlite3.Row
                totals = connection.execute(
                    """
                    SELECT
                        COUNT(DISTINCT t.trace_id) AS trace_count,
                        COUNT(s.span_id) AS span_count,
                        SUM(CASE WHEN s.span_type = 'generation' THEN 1 ELSE 0 END) AS generation_count,
                        SUM(CASE WHEN s.span_type IN ('function', 'mcp_tools') THEN 1 ELSE 0 END) AS tool_span_count,
                        SUM(CASE WHEN s.span_type = 'generation' AND s.pricing_status = 'estimated' THEN 1 ELSE 0 END) AS priced_generation_count,
                        SUM(s.requests) AS request_count,
                        SUM(s.input_tokens) AS input_tokens,
                        SUM(s.output_tokens) AS output_tokens,
                        SUM(s.total_tokens) AS total_tokens,
                        SUM(s.cached_input_tokens) AS cached_input_tokens,
                        SUM(s.reasoning_tokens) AS reasoning_tokens,
                        SUM(s.estimated_cost_usd) AS estimated_cost_usd,
                        AVG(t.latency_ms) AS average_run_latency_ms,
                        AVG(CASE WHEN s.span_type = 'generation' THEN s.latency_ms END) AS average_generation_latency_ms,
                        AVG(CASE WHEN s.span_type IN ('function', 'mcp_tools') THEN s.latency_ms END) AS average_tool_latency_ms
                    FROM model_traces t
                    LEFT JOIN model_spans s ON s.trace_id = t.trace_id
                    """
                ).fetchone()
                workflows = connection.execute(
                    """
                    SELECT
                        t.work_type,
                        COUNT(DISTINCT t.trace_id) AS model_run_count,
                        SUM(CASE WHEN s.span_type = 'generation' THEN 1 ELSE 0 END) AS generation_count,
                        SUM(s.requests) AS request_count,
                        SUM(s.input_tokens) AS input_tokens,
                        SUM(s.output_tokens) AS output_tokens,
                        SUM(s.total_tokens) AS total_tokens,
                        SUM(s.cached_input_tokens) AS cached_input_tokens,
                        SUM(s.reasoning_tokens) AS reasoning_tokens,
                        SUM(s.estimated_cost_usd) AS estimated_cost_usd,
                        AVG(t.latency_ms) AS average_run_latency_ms,
                        AVG(CASE WHEN s.span_type = 'generation' THEN s.latency_ms END) AS average_generation_latency_ms
                    FROM model_traces t
                    LEFT JOIN model_spans s ON s.trace_id = t.trace_id
                    GROUP BY t.work_type
                    ORDER BY t.work_type
                    """
                ).fetchall()
        except sqlite3.OperationalError:
            return {"path_present": True, "reason": "telemetry_schema_unavailable", "workflows": []}

        def integer(name: str) -> int:
            return int(totals[name] or 0)

        def decimal(name: str, digits: int = 3) -> float | None:
            value = totals[name]
            return round(float(value), digits) if value is not None else None

        workflow_rows: list[dict[str, Any]] = []
        for row in workflows:
            workflow_rows.append(
                {
                    "work_type": row["work_type"],
                    "model_run_count": int(row["model_run_count"] or 0),
                    "generation_count": int(row["generation_count"] or 0),
                    "request_count": int(row["request_count"] or 0),
                    "input_tokens": int(row["input_tokens"] or 0),
                    "output_tokens": int(row["output_tokens"] or 0),
                    "total_tokens": int(row["total_tokens"] or 0),
                    "cached_input_tokens": int(row["cached_input_tokens"] or 0),
                    "reasoning_tokens": int(row["reasoning_tokens"] or 0),
                    "estimated_cost_usd": round(float(row["estimated_cost_usd"]), 8)
                    if row["estimated_cost_usd"] is not None
                    else None,
                    "average_run_latency_ms": round(float(row["average_run_latency_ms"]), 3)
                    if row["average_run_latency_ms"] is not None
                    else None,
                    "average_generation_latency_ms": round(float(row["average_generation_latency_ms"]), 3)
                    if row["average_generation_latency_ms"] is not None
                    else None,
                }
            )

        return {
            "path_present": True,
            "trace_count": integer("trace_count"),
            "span_count": integer("span_count"),
            "generation_count": integer("generation_count"),
            "tool_span_count": integer("tool_span_count"),
            "priced_generation_count": integer("priced_generation_count"),
            "request_count": integer("request_count"),
            "input_tokens": integer("input_tokens"),
            "output_tokens": integer("output_tokens"),
            "total_tokens": integer("total_tokens"),
            "cached_input_tokens": integer("cached_input_tokens"),
            "reasoning_tokens": integer("reasoning_tokens"),
            "estimated_cost_usd": decimal("estimated_cost_usd", 8),
            "average_run_latency_ms": decimal("average_run_latency_ms"),
            "average_generation_latency_ms": decimal("average_generation_latency_ms"),
            "average_tool_latency_ms": decimal("average_tool_latency_ms"),
            "workflows": workflow_rows,
            "trace_linkage": "local trace_id retained; prompts and outputs excluded",
            "pricing": "cost is estimated only when SOZOROCK_MODEL_PRICING_JSON supplies reviewed rates",
        }

    @staticmethod
    def _failure_category(failure: str | None) -> str | None:
        if not failure:
            return None
        lowered = failure.casefold()
        if "evaluation failed" in lowered:
            return "evaluation_failure"
        if "agent identity is disabled" in lowered or "runtime turn cap" in lowered:
            return "runtime_policy_block"
        if "handler not registered" in lowered or "evaluator not registered" in lowered:
            return "configuration_failure"
        if "max steps exceeded" in lowered:
            return "workflow_loop_guard"
        if "failed" in lowered:
            return "node_failure"
        return "other_failure"

    @classmethod
    def _accumulate(cls, graph_metrics: dict[str, dict[str, Any]], row: dict[str, Any]) -> None:
        graph_id = row["graph_id"]
        metric = graph_metrics.setdefault(
            graph_id,
            {
                "versions": set(),
                "execution_count": 0,
                "completed_count": 0,
                "failed_count": 0,
                "waiting_approval_count": 0,
                "completed_node_count": 0,
                "event_count": 0,
                "failure_categories": {},
            },
        )
        metric["versions"].add(row["graph_version"])
        metric["execution_count"] += 1
        status = row["status"]
        if status == "completed":
            metric["completed_count"] += 1
        elif status == "failed":
            metric["failed_count"] += 1
        elif status == "waiting_approval":
            metric["waiting_approval_count"] += 1

        history = json.loads(row["history_json"] or "[]")
        events = json.loads(row["events_json"] or "[]")
        metric["completed_node_count"] += len(history)
        metric["event_count"] += len(events)
        category = cls._failure_category(row.get("failure"))
        if category:
            metric["failure_categories"][category] = metric["failure_categories"].get(category, 0) + 1
