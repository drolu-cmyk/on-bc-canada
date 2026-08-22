"""Durable helpers for privacy-preserving Outcomes Intelligence."""
from __future__ import annotations

from typing import Any

from runtime.graph_execution_store import GraphExecutionStore
from runtime.graph_kernel import GraphExecution, GraphKernel
from runtime.outcomes_intelligence_graph import OutcomesIntelligenceGraph, OutcomesIntelligenceProvider


def start_outcomes_intelligence(
    *,
    provider: OutcomesIntelligenceProvider,
    execution_store: GraphExecutionStore,
    execution_id: str,
    snapshot: dict[str, Any],
) -> GraphExecution:
    kernel = GraphKernel(
        event_privacy_class="aggregate_programme",
        event_retention_class="quality_record",
    )
    graph = OutcomesIntelligenceGraph(kernel=kernel, provider=provider)
    graph.register()
    _, execution = graph.start(execution_id=execution_id, snapshot=snapshot)
    packet = execution.state.get("outcomes_packet")
    execution_store.save_execution(
        execution,
        kernel.ledger,
        terminal_records={"outcomes_intelligence": packet} if packet is not None else None,
    )
    return execution


def outcomes_intelligence_summary(execution: GraphExecution) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "execution_id": execution.execution_id,
        "graph_id": execution.graph_id,
        "graph_version": execution.graph_version,
        "status": execution.status,
        "outcomes_status": execution.state.get("outcomes_status"),
    }
    if execution.failure:
        summary["failure"] = execution.failure
    if execution.status == "completed" and execution.state.get("outcomes_packet") is not None:
        summary["outcomes_packet"] = execution.state["outcomes_packet"]
    return summary
