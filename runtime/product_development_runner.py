"""Durable Product Development Graph start and human-review helpers."""
from __future__ import annotations

from typing import Any

from runtime.graph_kernel import GraphExecution, GraphKernel
from runtime.product_development_graph import ProductDevelopmentGraph, ProductDevelopmentProvider
from runtime.product_development_store import ProductDevelopmentStore


def start_product_development(
    *,
    provider: ProductDevelopmentProvider,
    store: ProductDevelopmentStore,
    execution_id: str,
    request: dict[str, Any],
) -> GraphExecution:
    kernel = GraphKernel()
    graph = ProductDevelopmentGraph(kernel=kernel, provider=provider)
    graph.register()
    _, execution = graph.start(execution_id=execution_id, request=request)
    store.save_execution(execution, kernel.ledger)
    return execution


def resume_product_development(
    *,
    provider: ProductDevelopmentProvider,
    store: ProductDevelopmentStore,
    execution_id: str,
    approved: bool,
    approver_id: str,
    note: str = "",
) -> GraphExecution:
    execution, ledger = store.load_execution(execution_id)
    kernel = GraphKernel(ledger=ledger)
    graph = ProductDevelopmentGraph(kernel=kernel, provider=provider)
    graph.register()
    definition = graph.definition()
    if execution.graph_id != definition.graph_id or execution.graph_version != definition.version:
        raise ValueError("stored execution does not match the current Product Development Graph version")
    kernel.executions[execution.execution_id] = execution
    execution = kernel.decide(
        definition,
        execution,
        approved=approved,
        approver_id=approver_id,
        note=note,
    )
    store.save_execution(execution, kernel.ledger)
    return execution


def product_execution_summary(execution: GraphExecution) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "execution_id": execution.execution_id,
        "graph_id": execution.graph_id,
        "graph_version": execution.graph_version,
        "status": execution.status,
        "current_node": execution.current_node,
        "product_status": execution.state.get("product_status"),
    }
    if execution.pending_approval is not None:
        summary["pending_approval"] = execution.pending_approval
    if execution.failure:
        summary["failure"] = execution.failure
    if "release_assurance" in execution.state:
        summary["release_assurance"] = execution.state["release_assurance"]
    if "release_record" in execution.state:
        summary["release_record"] = execution.state["release_record"]
    return summary
