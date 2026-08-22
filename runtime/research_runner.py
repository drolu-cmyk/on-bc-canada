"""Runnable research workflow helpers with durable stop-and-resume state."""
from __future__ import annotations

from typing import Any

from runtime.graph_kernel import GraphExecution, GraphKernel
from runtime.research_graph import ResearchGraph, ResearchProvider
from runtime.research_store import ResearchStore


def start_research(
    *,
    provider: ResearchProvider,
    store: ResearchStore,
    execution_id: str,
    question: str,
    geography: str = "Canada",
) -> GraphExecution:
    kernel = GraphKernel()
    graph = ResearchGraph(kernel=kernel, provider=provider)
    graph.register()
    _, execution = graph.start(
        execution_id=execution_id,
        question=question,
        geography=geography,
    )
    store.save_execution(execution, kernel.ledger)
    return execution


def resume_research(
    *,
    provider: ResearchProvider,
    store: ResearchStore,
    execution_id: str,
    approved: bool,
    approver_id: str,
    note: str = "",
) -> GraphExecution:
    execution, ledger = store.load_execution(execution_id)
    kernel = GraphKernel(ledger=ledger)
    graph = ResearchGraph(kernel=kernel, provider=provider)
    graph.register()
    definition = graph.definition()
    if execution.graph_id != definition.graph_id or execution.graph_version != definition.version:
        raise ValueError("stored execution does not match the current research graph version")
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


def execution_summary(execution: GraphExecution) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "execution_id": execution.execution_id,
        "graph_id": execution.graph_id,
        "graph_version": execution.graph_version,
        "status": execution.status,
        "current_node": execution.current_node,
    }
    research = execution.state.get("research", {})
    domain = research.get("domain") or {}
    if domain:
        summary["domain"] = {
            "domain_id": domain.get("domain_id"),
            "pathway_name": domain.get("pathway_name"),
        }
    if execution.pending_approval is not None:
        summary["pending_approval"] = execution.pending_approval
    if execution.failure:
        summary["failure"] = execution.failure
    if execution.status == "completed" and "finding" in execution.state:
        summary["finding"] = execution.state["finding"]
    return summary
