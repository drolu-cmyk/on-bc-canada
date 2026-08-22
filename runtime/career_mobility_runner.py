"""Durable helpers for learner-facing Career Mobility guidance."""
from __future__ import annotations

from typing import Any

from runtime.capability_graph import CapabilityGraphStore
from runtime.career_intelligence import CareerIntelligenceBuilder
from runtime.career_mobility_graph import CareerMobilityGraph, CareerMobilityProvider
from runtime.graph_execution_store import GraphExecutionStore
from runtime.graph_kernel import GraphExecution, GraphKernel
from runtime.learner_progress_store import LearnerProgressStore
from runtime.work_intelligence import WorkIntelligenceStore


def start_career_mobility(
    *,
    provider: CareerMobilityProvider,
    learner_store: LearnerProgressStore,
    capability_store: CapabilityGraphStore,
    work_store: WorkIntelligenceStore,
    execution_store: GraphExecutionStore,
    execution_id: str,
    instance_id: str,
) -> GraphExecution:
    instance = learner_store.get_instance(instance_id)
    kernel = GraphKernel(
        event_privacy_class="learner_private",
        event_retention_class="quality_record",
        event_learner_id=instance["learner_ref"],
        event_cohort_id=instance["cohort_id"],
    )
    intelligence = CareerIntelligenceBuilder(
        learner_store=learner_store,
        capability_store=capability_store,
        work_store=work_store,
    )
    graph = CareerMobilityGraph(kernel=kernel, intelligence=intelligence, provider=provider)
    graph.register()
    _, execution = graph.start(execution_id=execution_id, instance_id=instance_id)
    terminal = execution.state.get("career_packet")
    execution_store.save_execution(
        execution,
        kernel.ledger,
        terminal_records={"career_guidance": terminal} if terminal is not None else None,
    )
    return execution


def career_mobility_summary(execution: GraphExecution) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "execution_id": execution.execution_id,
        "graph_id": execution.graph_id,
        "graph_version": execution.graph_version,
        "status": execution.status,
        "career_status": execution.state.get("career_status"),
    }
    if execution.failure:
        summary["failure"] = execution.failure
    if execution.status == "completed" and execution.state.get("career_packet") is not None:
        summary["career_packet"] = execution.state["career_packet"]
    return summary
