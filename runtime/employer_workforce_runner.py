"""Durable helpers for organization-level Employer Workforce analysis."""
from __future__ import annotations

from typing import Any

from runtime.employer_workforce_context import EmployerWorkforceRequest
from runtime.employer_workforce_graph import EmployerWorkforceGraph, EmployerWorkforceProvider
from runtime.graph_execution_store import GraphExecutionStore
from runtime.graph_kernel import GraphExecution, GraphKernel


def start_employer_workforce_analysis(
    *,
    provider: EmployerWorkforceProvider,
    execution_store: GraphExecutionStore,
    execution_id: str,
    request: EmployerWorkforceRequest,
) -> GraphExecution:
    kernel = GraphKernel(
        event_privacy_class="operational",
        event_retention_class="quality_record",
    )
    graph = EmployerWorkforceGraph(kernel=kernel, provider=provider)
    graph.register()
    _, execution = graph.start(execution_id=execution_id, request=request)
    packet = execution.state.get("employer_workforce_packet")
    execution_store.save_execution(
        execution,
        kernel.ledger,
        terminal_records={"employer_workforce": packet} if packet is not None else None,
    )
    return execution


def employer_workforce_summary(execution: GraphExecution) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "execution_id": execution.execution_id,
        "graph_id": execution.graph_id,
        "graph_version": execution.graph_version,
        "status": execution.status,
        "employer_status": execution.state.get("employer_status"),
    }
    if execution.failure:
        summary["failure"] = execution.failure
    if execution.status == "completed" and execution.state.get("employer_workforce_packet") is not None:
        summary["employer_workforce_packet"] = execution.state["employer_workforce_packet"]
    return summary
