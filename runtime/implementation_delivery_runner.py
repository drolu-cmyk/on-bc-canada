"""Durable orchestration for constrained staging implementation and delivery review."""
from __future__ import annotations

from typing import Any

from runtime.graph_execution_store import GraphExecutionStore
from runtime.graph_kernel import GraphExecution, GraphKernel
from runtime.implementation_delivery_graph import ImplementationDeliveryGraph, ImplementationProvider
from runtime.implementation_workspace import RegisteredVerificationRunner, StagingWorkspace


def _terminal_records(execution: GraphExecution) -> dict[str, Any] | None:
    record = execution.state.get("delivery_record")
    return {"delivery_record": record} if record is not None else None


def start_implementation_delivery(
    *,
    provider: ImplementationProvider,
    execution_store: GraphExecutionStore,
    workspace: StagingWorkspace,
    verifier: RegisteredVerificationRunner,
    execution_id: str,
    request: dict[str, Any],
) -> GraphExecution:
    kernel = GraphKernel()
    graph = ImplementationDeliveryGraph(kernel=kernel, provider=provider, workspace=workspace, verifier=verifier)
    graph.register()
    _, execution = graph.start(execution_id=execution_id, request=request)
    execution_store.save_execution(execution, kernel.ledger, terminal_records=_terminal_records(execution))
    return execution


def resume_implementation_delivery(
    *,
    provider: ImplementationProvider,
    execution_store: GraphExecutionStore,
    workspace: StagingWorkspace,
    verifier: RegisteredVerificationRunner,
    execution_id: str,
    approved: bool,
    approver_id: str,
    note: str,
) -> GraphExecution:
    execution, ledger = execution_store.load_execution(execution_id)
    kernel = GraphKernel(ledger=ledger)
    graph = ImplementationDeliveryGraph(kernel=kernel, provider=provider, workspace=workspace, verifier=verifier)
    graph.register()
    definition = graph.definition()
    if execution.graph_id != definition.graph_id or execution.graph_version != definition.version:
        raise ValueError("stored execution does not match the current Implementation and Delivery Graph version")
    if execution.status != "waiting_approval":
        raise ValueError("implementation execution is not waiting for merge/deploy review")
    _assert_staging_integrity(workspace, execution.state.get("applied_changes", []))
    kernel.executions[execution.execution_id] = execution
    execution = kernel.decide(
        definition,
        execution,
        approved=approved,
        approver_id=approver_id,
        note=note,
    )
    execution_store.save_execution(execution, kernel.ledger, terminal_records=_terminal_records(execution))
    return execution


def _assert_staging_integrity(workspace: StagingWorkspace, applied_changes: list[dict[str, Any]]) -> None:
    if not applied_changes:
        raise ValueError("implementation has no staged changes to authorize")
    snapshots = {item.path: item for item in workspace.snapshot([item["path"] for item in applied_changes])}
    drift: list[str] = []
    for change in applied_changes:
        snapshot = snapshots[change["path"]]
        expected_after = change.get("after_sha256")
        if expected_after is None:
            if snapshot.exists:
                drift.append(change["path"])
        elif not snapshot.exists or snapshot.sha256 != expected_after:
            drift.append(change["path"])
    if drift:
        raise ValueError("staging content changed after verification: " + ", ".join(sorted(drift)))


def implementation_delivery_summary(execution: GraphExecution) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "execution_id": execution.execution_id,
        "graph_id": execution.graph_id,
        "graph_version": execution.graph_version,
        "status": execution.status,
        "current_node": execution.current_node,
        "implementation_status": execution.state.get("implementation_status"),
    }
    if execution.pending_approval is not None:
        summary["pending_approval"] = execution.pending_approval
    if execution.failure:
        summary["failure"] = execution.failure
    if "change_assurance" in execution.state:
        summary["change_assurance"] = execution.state["change_assurance"]
    if "delivery_assurance" in execution.state:
        summary["delivery_assurance"] = execution.state["delivery_assurance"]
    if "delivery_record" in execution.state:
        summary["delivery_record"] = execution.state["delivery_record"]
    return summary
