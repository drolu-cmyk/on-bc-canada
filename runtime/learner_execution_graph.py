"""Learner execution graph for coaching, evidence readiness, and human review.

Raw learner submissions never enter model context. Deterministic code derives a
small deidentified context from the learner progress store and reviewed capability
standards. Agents may coach and prepare review. A human decides whether mission
evidence is accepted; a denial routes to another learner iteration, not a system
failure.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from runtime.capability_graph import CapabilityGraphStore
from runtime.graph_kernel import ActorRef, GraphDefinition, GraphEdge, GraphKernel, GraphNode, NodeResult
from runtime.learner_progress_store import LearnerProgressStore
from runtime.openai_learner_provider import LearnerModelContext


class LearnerSupportProvider(Protocol):
    def coach(self, context: LearnerModelContext) -> dict[str, Any]: ...
    def analyze_progress(self, context: LearnerModelContext) -> dict[str, Any]: ...
    def prepare_human_review(self, context: LearnerModelContext) -> dict[str, Any]: ...


@dataclass
class LearnerExecutionGraph:
    kernel: GraphKernel
    progress_store: LearnerProgressStore
    capability_store: CapabilityGraphStore
    provider: LearnerSupportProvider

    @staticmethod
    def definition() -> GraphDefinition:
        def service(actor_id: str) -> ActorRef:
            return ActorRef(actor_id, "service", authority="A1")

        def agent(actor_id: str) -> ActorRef:
            return ActorRef(actor_id, "agent", authority="A1")

        return GraphDefinition(
            graph_id="learner-execution",
            version="0.1.0",
            start_node="load_deidentified_context",
            nodes=(
                GraphNode(
                    "load_deidentified_context",
                    service("learner-context-service"),
                    "learner.load_context",
                    "learner.context_privacy",
                ),
                GraphNode("coach", agent("learning-coach-agent"), "learner.coach", "learner.coach_output"),
                GraphNode("analyse_progress", agent("learner-progress-agent"), "learner.progress", "learner.progress_output"),
                GraphNode(
                    "prepare_human_review",
                    agent("human-review-preparation-agent"),
                    "learner.review_checklist",
                    "learner.review_output",
                ),
                GraphNode("route_readiness", service("evidence-readiness-policy"), "learner.route_readiness"),
                GraphNode("mark_learner_action", service("learner-progress-service"), "learner.mark_action"),
                GraphNode("mark_human_review", service("learner-progress-service"), "learner.mark_human_review"),
                GraphNode(
                    "human_assessment",
                    ActorRef("capability-evidence-reviewer", "human", authority="A3"),
                    approval_reason="Review the raw mission evidence against the supplied evidence standards.",
                ),
                GraphNode("accept_evidence", service("learner-evidence-service"), "learner.accept_evidence"),
                GraphNode("request_revision", service("learner-evidence-service"), "learner.request_revision"),
                GraphNode("finalize_action", service("learner-record-service"), "learner.finalize_action"),
                GraphNode("finalize_acceptance", service("learner-record-service"), "learner.finalize_acceptance"),
                GraphNode("finalize_revision", service("learner-record-service"), "learner.finalize_revision"),
            ),
            edges=(
                GraphEdge("load_deidentified_context", "coach"),
                GraphEdge("coach", "analyse_progress"),
                GraphEdge("analyse_progress", "prepare_human_review"),
                GraphEdge("prepare_human_review", "route_readiness"),
                GraphEdge("route_readiness", "mark_human_review", route="ready"),
                GraphEdge("route_readiness", "mark_learner_action", route="not_ready"),
                GraphEdge("mark_learner_action", "finalize_action"),
                GraphEdge("mark_human_review", "human_assessment"),
                GraphEdge("human_assessment", "accept_evidence", route="approved"),
                GraphEdge("human_assessment", "request_revision", route="denied"),
                GraphEdge("accept_evidence", "finalize_acceptance"),
                GraphEdge("request_revision", "finalize_revision"),
            ),
        )

    def register(self) -> None:
        self.kernel.register_handler("learner.load_context", self._load_context)
        self.kernel.register_handler("learner.coach", self._coach)
        self.kernel.register_handler("learner.progress", self._progress)
        self.kernel.register_handler("learner.review_checklist", self._review_checklist)
        self.kernel.register_handler("learner.route_readiness", self._route_readiness)
        self.kernel.register_handler("learner.mark_action", self._mark_action)
        self.kernel.register_handler("learner.mark_human_review", self._mark_human_review)
        self.kernel.register_handler("learner.accept_evidence", self._accept_evidence)
        self.kernel.register_handler("learner.request_revision", self._request_revision)
        self.kernel.register_handler("learner.finalize_action", self._finalize_action)
        self.kernel.register_handler("learner.finalize_acceptance", self._finalize_acceptance)
        self.kernel.register_handler("learner.finalize_revision", self._finalize_revision)
        self.kernel.register_evaluator("learner.context_privacy", self._evaluate_context_privacy)
        self.kernel.register_evaluator(
            "learner.coach_output",
            lambda state, result: (bool(result.patch.get("coaching", {}).get("next_actions")), "coaching actions required"),
        )
        self.kernel.register_evaluator(
            "learner.progress_output",
            lambda state, result: ("status" in result.patch.get("progress_analysis", {}), "progress status required"),
        )
        self.kernel.register_evaluator(
            "learner.review_output",
            lambda state, result: (bool(result.patch.get("review_checklist", {}).get("checklist")), "review checklist required"),
        )

    def start(self, *, execution_id: str, submission_id: str):
        submission = self.progress_store.get_submission(submission_id)
        if submission["status"] != "submitted":
            raise ValueError("learner assessment starts only from a newly submitted mission attempt")
        definition = self.definition()
        execution = self.kernel.start(
            definition,
            execution_id=execution_id,
            state={
                "submission_id": submission_id,
                "assessment_execution_id": execution_id,
                "assessment_status": "started",
            },
        )
        return definition, self.kernel.run(definition, execution)

    def _load_context(self, state: dict[str, Any]) -> NodeResult:
        submission = self.progress_store.get_submission(state["submission_id"])
        instance = self.progress_store.get_instance(submission["instance_id"])
        mission = next(
            item for item in instance["path_snapshot"]["units"] if item["unit_id"] == submission["unit_id"]
        )
        status_counts: dict[str, int] = {}
        for unit in instance["units"]:
            status_counts[unit["status"]] = status_counts.get(unit["status"], 0) + 1

        requirements: list[dict[str, Any]] = []
        for requirement in submission["mission_requirements"]:
            capability = self.capability_store.get(requirement["capability_id"])
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
                    f"mission requirement no longer resolves to an evidence standard: {requirement['capability_id']}:{requirement['standard_id']}"
                )
            artifact_type_present = bool(set(submission["artifact_types"]) & set(standard["artifact_types"]))
            requirements.append(
                {
                    "capability_id": requirement["capability_id"],
                    "standard_id": requirement["standard_id"],
                    "standard_description": standard["description"],
                    "minimum_level": standard["minimum_level"],
                    "accepted_artifact_types": list(standard["artifact_types"]),
                    "artifact_type_present": artifact_type_present,
                    "revision_required": bool(standard["requires_revision"]),
                    "revision_present": bool(submission.get("revision_ref")),
                    "defense_required": bool(standard["requires_defense"]),
                    "defense_present": bool(submission.get("defense_response_ref")),
                    "changed_scenario_required": bool(standard["requires_changed_scenario"]),
                    "changed_scenario_present": bool(submission.get("changed_scenario_response_ref")),
                }
            )

        def requirement_ready(item: dict[str, Any]) -> bool:
            return (
                item["artifact_type_present"]
                and (not item["revision_required"] or item["revision_present"])
                and (not item["defense_required"] or item["defense_present"])
                and (not item["changed_scenario_required"] or item["changed_scenario_present"])
            )

        readiness_complete = bool(requirements) and all(requirement_ready(item) for item in requirements)
        context = LearnerModelContext(
            pathway_id=instance["pathway_id"],
            learning_version=instance["learning_version"],
            unit_id=submission["unit_id"],
            unit_kind="mission",
            unit_title=mission["title"],
            unit_purpose=mission["purpose"],
            attempt_number=int(submission["attempt_number"]),
            unit_status_counts=status_counts,
            artifact_types=tuple(submission["artifact_types"]),
            readiness_complete=readiness_complete,
            readiness_requirements=tuple(requirements),
        )
        self._assert_context_is_deidentified(context.as_payload(), submission=submission, instance=instance)
        self.progress_store.set_submission_assessment_state(
            state["submission_id"],
            status="assessment_in_progress",
            assessment_execution_id=state["assessment_execution_id"],
        )
        return NodeResult(
            patch={
                "model_context": context.as_payload(),
                "readiness": {
                    "complete": readiness_complete,
                    "requirement_count": len(requirements),
                    "missing_count": sum(1 for item in requirements if not requirement_ready(item)),
                },
            },
            evidence=[{"type": "deidentified_context", "readiness_complete": readiness_complete}],
        )

    @staticmethod
    def _context(state: dict[str, Any]) -> LearnerModelContext:
        payload = state["model_context"]
        return LearnerModelContext(
            pathway_id=payload["pathway_id"],
            learning_version=payload["learning_version"],
            unit_id=payload["unit_id"],
            unit_kind=payload["unit_kind"],
            unit_title=payload["unit_title"],
            unit_purpose=payload["unit_purpose"],
            attempt_number=int(payload["attempt_number"]),
            unit_status_counts=dict(payload["unit_status_counts"]),
            artifact_types=tuple(payload["artifact_types"]),
            readiness_complete=bool(payload["readiness_complete"]),
            readiness_requirements=tuple(payload["readiness_requirements"]),
        )

    def _coach(self, state: dict[str, Any]) -> NodeResult:
        output = self.provider.coach(self._context(state))
        return NodeResult(patch={"coaching": output}, evidence=[{"type": "deidentified_coaching"}])

    def _progress(self, state: dict[str, Any]) -> NodeResult:
        output = self.provider.analyze_progress(self._context(state))
        return NodeResult(patch={"progress_analysis": output}, evidence=[{"type": "deidentified_progress_analysis"}])

    def _review_checklist(self, state: dict[str, Any]) -> NodeResult:
        output = self.provider.prepare_human_review(self._context(state))
        allowed = {
            (item["capability_id"], item["standard_id"])
            for item in state["model_context"]["readiness_requirements"]
        }
        checklist = output.get("checklist", [])
        returned = {(item.get("capability_id"), item.get("standard_id")) for item in checklist}
        if returned != allowed or len(checklist) != len(returned):
            raise ValueError("human review preparation must cover each required capability evidence standard exactly once")
        return NodeResult(patch={"review_checklist": output}, evidence=[{"type": "human_review_checklist"}])

    @staticmethod
    def _route_readiness(state: dict[str, Any]) -> NodeResult:
        ready = bool(state["readiness"]["complete"])
        return NodeResult(route="ready" if ready else "not_ready")

    def _mark_action(self, state: dict[str, Any]) -> NodeResult:
        self.progress_store.set_submission_assessment_state(
            state["submission_id"],
            status="learner_action_required",
            assessment_execution_id=state["assessment_execution_id"],
        )
        return NodeResult(patch={"assessment_status": "learner_action_required"})

    def _mark_human_review(self, state: dict[str, Any]) -> NodeResult:
        self.progress_store.set_submission_assessment_state(
            state["submission_id"],
            status="human_review",
            assessment_execution_id=state["assessment_execution_id"],
        )
        return NodeResult(patch={"assessment_status": "human_review"})

    def _accept_evidence(self, state: dict[str, Any]) -> NodeResult:
        decision = state.get("human_decisions", {}).get("human_assessment")
        if not decision or decision.get("approved") is not True:
            raise ValueError("accepted evidence requires the graph human-review authorization record")
        self.progress_store.accept_mission_evidence(
            state["submission_id"],
            assessment_execution_id=state["assessment_execution_id"],
            accepted_by=decision["approver_id"],
            note=decision.get("note", ""),
        )
        return NodeResult(patch={"assessment_status": "accepted"})

    def _request_revision(self, state: dict[str, Any]) -> NodeResult:
        decision = state.get("human_decisions", {}).get("human_assessment")
        if not decision or decision.get("approved") is not False:
            raise ValueError("revision route requires the graph human-review decision record")
        self.progress_store.reject_mission_evidence(
            state["submission_id"],
            assessment_execution_id=state["assessment_execution_id"],
            rejected_by=decision["approver_id"],
            note=decision.get("note", "Evidence requires another learner iteration."),
        )
        return NodeResult(patch={"assessment_status": "revision_required"})

    @staticmethod
    def _assessment_record(state: dict[str, Any], status: str) -> dict[str, Any]:
        return {
            "submission_id": state["submission_id"],
            "assessment_execution_id": state["assessment_execution_id"],
            "status": status,
            "readiness": state["readiness"],
            "coaching": state["coaching"],
            "progress_analysis": state["progress_analysis"],
            "review_checklist": state["review_checklist"],
        }

    def _finalize_action(self, state: dict[str, Any]) -> NodeResult:
        return NodeResult(
            patch={"assessment_record": self._assessment_record(state, "learner_action_required")},
            evidence=[{"type": "learner_action_record"}],
        )

    def _finalize_acceptance(self, state: dict[str, Any]) -> NodeResult:
        return NodeResult(
            patch={"assessment_record": self._assessment_record(state, "accepted")},
            evidence=[{"type": "human_accepted_capability_evidence"}],
        )

    def _finalize_revision(self, state: dict[str, Any]) -> NodeResult:
        return NodeResult(
            patch={"assessment_record": self._assessment_record(state, "revision_required")},
            evidence=[{"type": "human_revision_record"}],
        )

    def _evaluate_context_privacy(self, state: dict[str, Any], result: NodeResult) -> tuple[bool, str]:
        payload = result.patch.get("model_context")
        if not isinstance(payload, dict):
            return False, "deidentified model context required"
        try:
            submission = self.progress_store.get_submission(state["submission_id"])
            instance = self.progress_store.get_instance(submission["instance_id"])
            self._assert_context_is_deidentified(payload, submission=submission, instance=instance)
        except ValueError as exc:
            return False, str(exc)
        return True, "model context excludes learner identity and raw evidence references"

    @staticmethod
    def _assert_context_is_deidentified(
        payload: dict[str, Any],
        *,
        submission: dict[str, Any],
        instance: dict[str, Any],
    ) -> None:
        forbidden_keys = {
            "learner_ref",
            "learner_id",
            "cohort_id",
            "submission_id",
            "artifact_refs",
            "revision_ref",
            "defense_response_ref",
            "changed_scenario_response_ref",
            "attendance",
            "support",
            "credential",
        }

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                if forbidden_keys.intersection(value):
                    raise ValueError("model context contains a prohibited learner record field")
                for nested in value.values():
                    walk(nested)
            elif isinstance(value, list):
                for nested in value:
                    walk(nested)

        walk(payload)
        serialized = repr(payload)
        forbidden_values = [
            instance.get("learner_ref"),
            instance.get("cohort_id"),
            submission.get("submission_id"),
            *submission.get("artifact_refs", []),
            submission.get("revision_ref"),
            submission.get("defense_response_ref"),
            submission.get("changed_scenario_response_ref"),
        ]
        for value in forbidden_values:
            if value and str(value) in serialized:
                raise ValueError("model context contains a prohibited learner identifier or evidence reference")
