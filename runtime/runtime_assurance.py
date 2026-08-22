"""Aggregate runtime assurance telemetry from durable graph stores.

The first release intentionally measures only what the current stores can prove:
execution status, failures, human-review state, graph versions, node completion,
and event counts. Token usage, model cost, provider latency, and tool-call latency
are marked as unavailable instead of inferred.
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
    def __init__(self, sources: tuple[RuntimeStoreSource, ...]) -> None:
        self.sources = sources

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

        return {
            "snapshot_version": "0.1.0",
            "graphs": graphs,
            "source_coverage": coverage,
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
                "model_token_usage": False,
                "model_monetary_cost": False,
                "provider_latency": False,
                "tool_call_latency": False,
                "trace_sampling": False,
            },
            "model_boundary": {
                "contains_learner_identity": False,
                "contains_raw_graph_state": False,
                "contains_prompts_or_model_outputs": False,
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
