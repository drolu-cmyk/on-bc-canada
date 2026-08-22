"""Durable start and human-review helpers for the Business Operations Graph."""
from __future__ import annotations

from typing import Any

from runtime.business_operations_graph import BusinessOperationsGraph, BusinessOperationsProvider
from runtime.graph_execution_store import GraphExecutionStore
from runtime.graph_kernel import GraphExecution, GraphKernel


def _terminal_records(execution: GraphExecution) -> dict[str, Any] | None:
    record = execution.state.get("business_record")
    return {"business_record": record} if record is not None else None


def start_business_operations(
    *,
    provider: BusinessOperationsProvider,
    store: GraphExecutionStore,
    execution_id: str,
    request: dict[str, Any],
) -> GraphExecution:
    kernel = GraphKernel()
    graph = BusinessOperationsGraph(kernel=kernel, provider=provider)
    graph.register()
    _, execution = graph.start(execution_id=execution_id, request=request)
    store.save_execution(execution, kernel.ledger, terminal_records=_terminal_records(execution))
    return execution


def resume_business_operations(
    *,
    provider: BusinessOperationsProvider,
    store: GraphExecutionStore,
    execution_id: str,
    approved: bool,
    approver_id: str,
    note: str,
) -> GraphExecution:
    execution, ledger = store.load_execution(execution_id)
    kernel = GraphKernel(ledger=ledger)
    graph = BusinessOperationsGraph(kernel=kernel, provider=provider)
    graph.register()
    definition = graph.definition()
    if execution.graph_id != definition.graph_id or execution.graph_version != definition.version:
        raise ValueError("stored execution does not match the current Business Operations Graph version")
    kernel.executions[execution.execution_id] = execution
    execution = kernel.decide(
        definition,
        execution,
        approved=approved,
        approver_id=approver_id,
        note=note,
    )
    store.save_execution(execution, kernel.ledger, terminal_records=_terminal_records(execution))
    return execution


def business_execution_summary(execution: GraphExecution) -> dict[str, Any]:
    request = execution.state.get("request", execution.state.get("input_request", {}))
    summary: dict[str, Any] = {
        "execution_id": execution.execution_id,
        "graph_id": execution.graph_id,
        "graph_version": execution.graph_version,
        "status": execution.status,
        "current_node": execution.current_node,
        "workstream": request.get("workstream"),
        "action_class": request.get("action_class"),
        "business_status": execution.state.get("business_status"),
    }
    if execution.pending_approval is not None:
        summary["pending_approval"] = execution.pending_approval
    if execution.failure:
        summary["failure"] = execution.failure
    if "operating_assurance" in execution.state:
        summary["operating_assurance"] = execution.state["operating_assurance"]
    if "business_record" in execution.state:
        summary["business_record"] = execution.state["business_record"]
    return summary
