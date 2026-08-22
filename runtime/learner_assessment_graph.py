"""Learner mission assessment graph with human capability-evidence acceptance.

Agents review, assess, and challenge supplied learner evidence. Deterministic
assurance enforces the active capability evidence standard. A model can never
accept capability evidence into the learner record.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from runtime.graph_kernel import ActorRef, GraphDefinition, GraphEdge, GraphKernel, GraphNode, NodeResult


class LearnerAssessmentProvider(Protocol):
    def normalize(self, request: dict[str, Any]) -> dict[str, Any]: ...
    def review_submission(self, request: dict[str, Any]) -> dict[str, Any]: ...
    def assess_evidence(self, request: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]: ...
    def challenge_assessment(
        self,
        request: dict[str, Any],
        review: dict[str, Any],
        assessment: dict[str, Any],
    ) -> dict[str, Any]: ...


@dataclass
class LearnerAssessmentGraph:
    kernel: GraphKernel
    provider: LearnerAssessmentProvider

    @staticmethod
    def definition() -> GraphDefinition:
        def service(actor_id: str) -> ActorRef:
            return ActorRef(actor_id=actor_id, kind="service", authority="A1")

        def agent(actor_id: str) -> ActorRef:
            return ActorRef(actor_id=actor_id, kind="agent", authority="A1")

        return GraphDefinition(
            graph_id="learner-mission-assessment",
            version="0.1.0",
            start_node="normalize_submission",
            nodes=(
                GraphNode("normalize_submission", service("assessment-contract"), "assessment.normalize", "assessment.request"),
                GraphNode("submission_review", agent("submission-review-agent"), "assessment.review", "assessment.review"),
                GraphNode("evidence_assessment", agent("evidence-assessment-agent"), "assessment.assess", "assessment.assessment"),
                GraphNode("assessment_challenge", agent("evidence-challenge-agent"), "assessment.challenge", "assessment.challenge"),
                GraphNode("evidence_assurance", service("evidence-assurance"), "assessment.assure", "assessment.assurance"),
                GraphNode(
                    "capability_evidence_review",
                    ActorRef("assessment-accountable-human", "human", authority="A3"),
                    approval_reason="Capability evidence passed automated assurance. Human acceptance is required.",
                ),
                GraphNode("finalize_accepted", service("assessment-record"), "assessment.finalize_accepted", "assessment.final"),
                GraphNode("finalize_action", service("assessment-record"), "assessment.finalize_action", "assessment.final"),
                GraphNode("finalize_not_ready", service("assessment-record"), "assessment.finalize_not_ready", "assessment.final"),
            ),
            edges=(
                GraphEdge("normalize_submission", "submission_review"),
                GraphEdge("submission_review", "evidence_assessment"),
                GraphEdge("evidence_assessment", "assessment_challenge"),
                GraphEdge("assessment_challenge", "evidence_assurance"),
                GraphEdge("evidence_assurance", "capability_evidence_review", route="human_review"),
                GraphEdge("evidence_assurance", "finalize_action", route="learner_action"),
                GraphEdge("evidence_assurance", "finalize_not_ready", route="not_ready"),
                GraphEdge("capability_evidence_review", "finalize_accepted", route="approved"),
            ),
        )

    def register(self) -> None:
        handlers = {
            "assessment.normalize": self._normalize,
            "assessment.review": self._review,
            "assessment.assess": self._assess,
            "assessment.challenge": self._challenge,
            "assessment.assure": self._assure,
            "assessment.finalize_accepted": self._finalize_accepted,
            "assessment.finalize_action": self._finalize_action,
            "assessment.finalize_not_ready": self._finalize_not_ready,
        }
        for name, handler in handlers.items():
            self.kernel.register_handler(name, handler)

        self.kernel.register_evaluator(
            "assessment.request",
            lambda state, result: (
                bool(result.patch.get("assessment_request", {}).get("submission", {}).get("submission_id"))
                and bool(result.patch.get("assessment_request", {}).get("standards")),
                "submission and evidence standards required",
            ),
        )
        self.kernel.register_evaluator(
            "assessment.review",
            lambda state, result: (
                result.patch.get("review", {}).get("status") in {"ready", "action_recommended"},
                "typed submission review required",
            ),
        )
        self.kernel.register_evaluator(
            "assessment.assessment",
            lambda state, result: (
                isinstance(result.patch.get("assessment", {}).get("findings"), list),
                "typed evidence findings required",
            ),
        )
        self.kernel.register_evaluator(
            "assessment.challenge",
            lambda state, result: (
                result.patch.get("challenge", {}).get("status") in {"clear", "concern"},
                "assessment challenge result required",
            ),
        )
        self.kernel.register_evaluator(
            "assessment.assurance",
            lambda state, result: (
                "evidence_assurance" in result.patch and result.route in {"human_review", "learner_action", "not_ready"},
                "deterministic evidence assurance route required",
            ),
        )
        self.kernel.register_evaluator(
            "assessment.final",
            lambda state, result: ("assessment_record" in result.patch, "assessment terminal record required"),
        )

    def start(self, *, execution_id: str, request: dict[str, Any]):
        definition = self.definition()
        execution = self.kernel.start(
            definition,
            execution_id=execution_id,
            state={"input_request": request, "assessment_status": "started"},
        )
        return definition, self.kernel.run(definition, execution)

    def _normalize(self, state: dict[str, Any]) -> NodeResult:
        request = self.provider.normalize(state["input_request"])
        return NodeResult(
            patch={"assessment_request": request},
            evidence=[{"type": "learner_submission_contract", "submission_id": request["submission"]["submission_id"]}],
        )

    def _review(self, state: dict[str, Any]) -> NodeResult:
        review = self.provider.review_submission(state["assessment_request"])
        return NodeResult(
            patch={"review": review},
            evidence=[{"type": "submission_review", "status": review.get("status")}],
        )

    def _assess(self, state: dict[str, Any]) -> NodeResult:
        assessment = self.provider.assess_evidence(state["assessment_request"], state["review"])
        return NodeResult(
            patch={"assessment": assessment},
            evidence=[{"type": "evidence_assessment", "finding_count": len(assessment.get("findings", []))}],
        )

    def _challenge(self, state: dict[str, Any]) -> NodeResult:
        challenge = self.provider.challenge_assessment(
            state["assessment_request"], state["review"], state["assessment"]
        )
        return NodeResult(
            patch={"challenge": challenge},
            evidence=[{"type": "assessment_challenge", "status": challenge.get("status")}],
        )

    @staticmethod
    def _assure(state: dict[str, Any]) -> NodeResult:
        request = state["assessment_request"]
        submission = request["submission"]
        standards = request["standards"]
        requirements = submission["mission_requirements"]
        findings = state["assessment"].get("findings", [])
        review = state["review"]
        challenge = state["challenge"]

        required_pairs = {(item["capability_id"], item["standard_id"]) for item in requirements}
        finding_map = {
            (item.get("capability_id"), item.get("standard_id")): item
            for item in findings
            if item.get("capability_id") and item.get("standard_id")
        }
        standard_map = {
            (item["capability_id"], item["standard_id"]): item
            for item in standards
        }

        missing_actions: list[str] = []
        blocking_reasons: list[str] = []
        artifact_types = set(submission.get("artifact_types", []))

        for pair in sorted(required_pairs):
            standard = standard_map.get(pair)
            if standard is None:
                blocking_reasons.append(f"missing active evidence standard: {pair[0]}:{pair[1]}")
                continue
            accepted_types = set(standard.get("artifact_types", []))
            if accepted_types and not (artifact_types & accepted_types):
                missing_actions.append(f"submit an accepted artifact type for {pair[0]}:{pair[1]}")
            if standard.get("requires_revision") and not submission.get("revision_ref"):
                missing_actions.append(f"provide revision evidence for {pair[0]}:{pair[1]}")
            if standard.get("requires_defense") and not submission.get("defense_response_ref"):
                missing_actions.append(f"provide defense evidence for {pair[0]}:{pair[1]}")
            if standard.get("requires_changed_scenario") and not submission.get("changed_scenario_response_ref"):
                missing_actions.append(f"respond to a changed scenario for {pair[0]}:{pair[1]}")

            finding = finding_map.get(pair)
            if finding is None:
                blocking_reasons.append(f"assessment did not cover {pair[0]}:{pair[1]}")
            elif finding.get("verdict") != "meets":
                blocking_reasons.append(
                    f"assessment verdict for {pair[0]}:{pair[1]} is {finding.get('verdict', 'missing')}"
                )

        extra_findings = sorted(set(finding_map) - required_pairs)
        if extra_findings:
            blocking_reasons.append("assessment introduced capability evidence outside the mission requirements")
        if review.get("status") == "action_recommended":
            missing_actions.extend(review.get("learner_actions", []))
        if challenge.get("status") == "concern":
            blocking_reasons.extend(challenge.get("concerns", []))

        missing_actions = sorted(set(item for item in missing_actions if item))
        blocking_reasons = sorted(set(item for item in blocking_reasons if item))
        if missing_actions:
            route = "learner_action"
            status = "learner_action_required"
        elif blocking_reasons:
            route = "not_ready"
            status = "evidence_not_ready"
        else:
            route = "human_review"
            status = "ready_for_human_review"

        assurance = {
            "status": status,
            "required_pairs": [f"{capability_id}:{standard_id}" for capability_id, standard_id in sorted(required_pairs)],
            "learner_actions": missing_actions,
            "blocking_reasons": blocking_reasons,
        }
        return NodeResult(
            patch={"evidence_assurance": assurance},
            evidence=[
                {
                    "type": "learner_evidence_assurance",
                    "status": status,
                    "learner_action_count": len(missing_actions),
                    "blocking_reason_count": len(blocking_reasons),
                }
            ],
            route=route,
        )

    @staticmethod
    def _record(state: dict[str, Any], status: str) -> dict[str, Any]:
        return {
            "status": status,
            "submission_id": state["assessment_request"]["submission"]["submission_id"],
            "review": state["review"],
            "assessment": state["assessment"],
            "challenge": state["challenge"],
            "assurance": state["evidence_assurance"],
        }

    @classmethod
    def _finalize_accepted(cls, state: dict[str, Any]) -> NodeResult:
        record = cls._record(state, "accepted_capability_evidence")
        return NodeResult(
            patch={"assessment_record": record, "assessment_status": "accepted"},
            evidence=[{"type": "learner_assessment_record", "status": record["status"]}],
        )

    @classmethod
    def _finalize_action(cls, state: dict[str, Any]) -> NodeResult:
        record = cls._record(state, "learner_action_required")
        return NodeResult(
            patch={"assessment_record": record, "assessment_status": "learner_action_required"},
            evidence=[{"type": "learner_assessment_record", "status": record["status"]}],
        )

    @classmethod
    def _finalize_not_ready(cls, state: dict[str, Any]) -> NodeResult:
        record = cls._record(state, "evidence_not_ready")
        return NodeResult(
            patch={"assessment_record": record, "assessment_status": "evidence_not_ready"},
            evidence=[{"type": "learner_assessment_record", "status": record["status"]}],
        )
