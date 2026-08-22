"""Durable helpers for aggregate autonomous-platform Runtime Assurance."""
from __future__ import annotations

from typing import Any

from runtime.graph_execution_store import GraphExecutionStore
from runtime.graph_kernel import GraphExecution, GraphKernel
from runtime.runtime_assurance_graph import RuntimeAssuranceGraph, RuntimeAssuranceProvider


def start_runtime_assurance(
    *,
    provider: RuntimeAssuranceProvider,
    execution_store: GraphExecutionStore,
    execution_id: str,
    snapshot: dict[str, Any],
) -> GraphExecution:
    kernel = GraphKernel(
        event_privacy_class="operational",
        event_retention_class="quality_record",
    )
    graph = RuntimeAssuranceGraph(kernel=kernel, provider=provider)
    graph.register()
    _, execution = graph.start(execution_id=execution_id, snapshot=snapshot)
    packet = execution.state.get("runtime_assurance_packet")
    execution_store.save_execution(
        execution,
        kernel.ledger,
        terminal_records={"runtime_assurance": packet} if packet is not None else None,
    )
    return execution


def runtime_assurance_summary(execution: GraphExecution) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "execution_id": execution.execution_id,
        "graph_id": execution.graph_id,
        "graph_version": execution.graph_version,
        "status": execution.status,
        "runtime_assurance_status": execution.state.get("runtime_assurance_status"),
    }
    if execution.failure:
        summary["failure"] = execution.failure
    if execution.status == "completed" and execution.state.get("runtime_assurance_packet") is not None:
        summary["runtime_assurance_packet"] = execution.state["runtime_assurance_packet"]
    return summary
