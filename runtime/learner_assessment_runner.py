"""Durable learner mission assessment orchestration and progress synchronization."""
from __future__ import annotations

from typing import Any

from runtime.capability_graph import CapabilityGraphStore
from runtime.graph_execution_store import GraphExecutionStore
from runtime.graph_kernel import GraphExecution, GraphKernel
from runtime.learner_assessment_graph import LearnerAssessmentGraph, LearnerAssessmentProvider
from runtime.learner_progress_store import LearnerProgressStore


def _build_request(
    *,
    progress: LearnerProgressStore,
    capabilities: CapabilityGraphStore,
    submission_id: str,
    evidence_material: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    submission = progress.get_submission(submission_id)
    instance = progress.get_instance(submission["instance_id"])
    mission = next(
        unit for unit in instance["path_snapshot"]["units"] if unit["unit_id"] == submission["unit_id"]
    )
    standards: list[dict[str, Any]] = []
    for requirement in submission["mission_requirements"]:
        capability = capabilities.get(requirement["capability_id"])
        standard = next(
            (
                item
                for item in capability["evidence_standards"]
                if item["standard_id"] == requirement["standard_id"]
            ),
            None,
        )
        if standard is None:
            raise ValueError(
                f"capability evidence standard not found: {requirement['capability_id']}:{requirement['standard_id']}"
            )
        standards.append(
            {
                "capability_id": requirement["capability_id"],
                "capability_name": capability["name"],
                "capability_description": capability["description"],
                "capability_status": capability["status"],
                "target_level": capability["target_level"],
                "standard_id": standard["standard_id"],
                "description": standard["description"],
                "artifact_types": standard["artifact_types"],
                "minimum_level": standard["minimum_level"],
                "requires_defense": standard["requires_defense"],
                "requires_revision": standard["requires_revision"],
                "requires_changed_scenario": standard["requires_changed_scenario"],
            }
        )
    request = {
        "submission": submission,
        "mission": {
            "unit_id": mission["unit_id"],
            "title": mission["title"],
            "purpose": mission["purpose"],
            "develops_capability_ids": mission["develops_capability_ids"],
            "evidence_requirements": mission["evidence_requirements"],
        },
        "standards": standards,
        "evidence_material": evidence_material,
    }
    return request, submission, instance


def _terminal_records(execution: GraphExecution) -> dict[str, Any] | None:
    record = execution.state.get("assessment_record")
    return {"assessment_record": record} if record is not None else None


def start_learner_assessment(
    *,
    provider: LearnerAssessmentProvider,
    execution_store: GraphExecutionStore,
    progress_store: LearnerProgressStore,
    capability_store: CapabilityGraphStore,
    execution_id: str,
    submission_id: str,
    evidence_material: list[dict[str, Any]],
) -> GraphExecution:
    request, submission, instance = _build_request(
        progress=progress_store,
        capabilities=capability_store,
        submission_id=submission_id,
        evidence_material=evidence_material,
    )
    progress_store.set_submission_assessment_state(
        submission_id,
        status="assessment_in_progress",
        assessment_execution_id=execution_id,
    )
    kernel = GraphKernel(
        event_privacy_class="learner_private",
        event_retention_class="quality_record",
        event_learner_id=instance["learner_ref"],
        event_cohort_id=instance["cohort_id"],
    )
    graph = LearnerAssessmentGraph(kernel=kernel, provider=provider)
    graph.register()
    _, execution = graph.start(execution_id=execution_id, request=request)
    execution_store.save_execution(execution, kernel.ledger, terminal_records=_terminal_records(execution))
    _sync_nonhuman_state(execution, progress_store, submission_id)
    return execution


def resume_learner_assessment(
    *,
    provider: LearnerAssessmentProvider,
    execution_store: GraphExecutionStore,
    progress_store: LearnerProgressStore,
    execution_id: str,
    approved: bool,
    approver_id: str,
    note: str,
) -> GraphExecution:
    execution, ledger = execution_store.load_execution(execution_id)
    submission_id = execution.state["assessment_request"]["submission"]["submission_id"]
    submission = progress_store.get_submission(submission_id)
    instance = progress_store.get_instance(submission["instance_id"])
    kernel = GraphKernel(
        ledger=ledger,
        event_privacy_class="learner_private",
        event_retention_class="quality_record",
        event_learner_id=instance["learner_ref"],
        event_cohort_id=instance["cohort_id"],
    )
    graph = LearnerAssessmentGraph(kernel=kernel, provider=provider)
    graph.register()
    definition = graph.definition()
    if execution.graph_id != definition.graph_id or execution.graph_version != definition.version:
        raise ValueError("stored execution does not match the current learner assessment graph version")
    kernel.executions[execution.execution_id] = execution
    execution = kernel.decide(
        definition,
        execution,
        approved=approved,
        approver_id=approver_id,
        note=note,
    )
    execution_store.save_execution(execution, kernel.ledger, terminal_records=_terminal_records(execution))
    if approved and execution.status == "completed":
        progress_store.accept_mission_evidence(
            submission_id,
            assessment_execution_id=execution_id,
            accepted_by=approver_id,
            note=note,
        )
    elif not approved and execution.status == "failed":
        progress_store.reject_mission_evidence(
            submission_id,
            assessment_execution_id=execution_id,
            rejected_by=approver_id,
            note=note,
        )
    return execution


def _sync_nonhuman_state(
    execution: GraphExecution,
    progress_store: LearnerProgressStore,
    submission_id: str,
) -> None:
    if execution.status == "waiting_approval":
        progress_store.set_submission_assessment_state(
            submission_id,
            status="human_review",
            assessment_execution_id=execution.execution_id,
        )
        return
    record = execution.state.get("assessment_record")
    if execution.status != "completed" or not record:
        return
    status_map = {
        "learner_action_required": "learner_action_required",
        "evidence_not_ready": "evidence_not_ready",
    }
    submission_status = status_map.get(record.get("status"))
    if submission_status:
        progress_store.set_submission_assessment_state(
            submission_id,
            status=submission_status,
            assessment_execution_id=execution.execution_id,
        )


def learner_assessment_summary(execution: GraphExecution) -> dict[str, Any]:
    submission_id = None
    if "assessment_request" in execution.state:
        submission_id = execution.state["assessment_request"]["submission"].get("submission_id")
    summary: dict[str, Any] = {
        "execution_id": execution.execution_id,
        "graph_id": execution.graph_id,
        "graph_version": execution.graph_version,
        "status": execution.status,
        "current_node": execution.current_node,
        "submission_id": submission_id,
        "assessment_status": execution.state.get("assessment_status"),
    }
    if execution.pending_approval is not None:
        summary["pending_approval"] = execution.pending_approval
    if execution.failure:
        summary["failure"] = execution.failure
    if "evidence_assurance" in execution.state:
        summary["evidence_assurance"] = execution.state["evidence_assurance"]
    if "assessment_record" in execution.state:
        summary["assessment_record"] = execution.state["assessment_record"]
    return summary
