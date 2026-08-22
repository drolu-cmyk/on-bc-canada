"""Durable start and resume helpers for learner mission assessment."""
from __future__ import annotations

from typing import Any

from runtime.capability_graph import CapabilityGraphStore
from runtime.graph_execution_store import GraphExecutionStore
from runtime.graph_kernel import GraphExecution, GraphKernel
from runtime.learner_execution_graph import LearnerExecutionGraph, LearnerSupportProvider
from runtime.learner_progress_store import LearnerProgressStore


def _kernel_for_submission(
    *,
    progress_store: LearnerProgressStore,
    submission_id: str,
    ledger=None,
) -> GraphKernel:
    submission = progress_store.get_submission(submission_id)
    instance = progress_store.get_instance(submission["instance_id"])
    return GraphKernel(
        ledger=ledger,
        event_privacy_class="learner_private",
        event_retention_class="quality_record",
        event_learner_id=instance["learner_ref"],
        event_cohort_id=instance["cohort_id"],
    )


def _terminal_records(execution: GraphExecution) -> dict[str, Any] | None:
    record = execution.state.get("assessment_record")
    return {"learner_assessment": record} if record is not None else None


def start_learner_assessment(
    *,
    provider: LearnerSupportProvider,
    progress_store: LearnerProgressStore,
    capability_store: CapabilityGraphStore,
    execution_store: GraphExecutionStore,
    execution_id: str,
    submission_id: str,
) -> GraphExecution:
    kernel = _kernel_for_submission(progress_store=progress_store, submission_id=submission_id)
    graph = LearnerExecutionGraph(
        kernel=kernel,
        progress_store=progress_store,
        capability_store=capability_store,
        provider=provider,
    )
    graph.register()
    _, execution = graph.start(execution_id=execution_id, submission_id=submission_id)
    execution_store.save_execution(
        execution,
        kernel.ledger,
        terminal_records=_terminal_records(execution),
    )
    return execution


def resume_learner_assessment(
    *,
    provider: LearnerSupportProvider,
    progress_store: LearnerProgressStore,
    capability_store: CapabilityGraphStore,
    execution_store: GraphExecutionStore,
    execution_id: str,
    accepted: bool,
    reviewer_id: str,
    note: str,
) -> GraphExecution:
    if not reviewer_id.strip() or not note.strip():
        raise ValueError("learner evidence review requires a named reviewer and review note")
    execution, ledger = execution_store.load_execution(execution_id)
    if execution.graph_id != "learner-execution":
        raise ValueError("stored execution is not a learner assessment")
    submission_id = execution.state["submission_id"]
    kernel = _kernel_for_submission(
        progress_store=progress_store,
        submission_id=submission_id,
        ledger=ledger,
    )
    graph = LearnerExecutionGraph(
        kernel=kernel,
        progress_store=progress_store,
        capability_store=capability_store,
        provider=provider,
    )
    graph.register()
    definition = graph.definition()
    if execution.graph_version != definition.version:
        raise ValueError("stored learner assessment does not match the current graph version")
    kernel.executions[execution.execution_id] = execution
    execution = kernel.decide(
        definition,
        execution,
        approved=accepted,
        approver_id=reviewer_id,
        note=note,
    )
    execution_store.save_execution(
        execution,
        kernel.ledger,
        terminal_records=_terminal_records(execution),
    )
    return execution


def learner_assessment_summary(execution: GraphExecution) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "execution_id": execution.execution_id,
        "graph_id": execution.graph_id,
        "graph_version": execution.graph_version,
        "status": execution.status,
        "current_node": execution.current_node,
        "submission_id": execution.state.get("submission_id"),
        "assessment_status": execution.state.get("assessment_status"),
    }
    if execution.pending_approval is not None:
        summary["review"] = execution.pending_approval
    if execution.failure:
        summary["failure"] = execution.failure
    if execution.status == "completed" and execution.state.get("assessment_record") is not None:
        summary["assessment_record"] = execution.state["assessment_record"]
    return summary
