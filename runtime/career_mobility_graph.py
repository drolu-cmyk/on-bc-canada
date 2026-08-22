"""Career Mobility Graph built from human-accepted capability evidence.

The graph provides learner-facing career interpretation only. It does not make
employer decisions, predict hiring, publish profiles, apply to jobs, contact
employers, or make immigration/licensing determinations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from runtime.career_intelligence import CareerIntelligenceBuilder, CareerModelContext
from runtime.graph_kernel import ActorRef, GraphDefinition, GraphEdge, GraphKernel, GraphNode, NodeResult


class CareerMobilityProvider(Protocol):
    def profile(self, context: CareerModelContext) -> dict[str, Any]: ...
    def analyze_role_transitions(self, context: CareerModelContext) -> dict[str, Any]: ...
    def package_evidence(self, context: CareerModelContext) -> dict[str, Any]: ...
    def prepare_interview_practice(self, context: CareerModelContext) -> dict[str, Any]: ...
    def plan_actions(self, context: CareerModelContext) -> dict[str, Any]: ...


@dataclass
class CareerMobilityGraph:
    kernel: GraphKernel
    intelligence: CareerIntelligenceBuilder
    provider: CareerMobilityProvider

    @staticmethod
    def definition() -> GraphDefinition:
        def service(actor_id: str) -> ActorRef:
            return ActorRef(actor_id, "service", authority="A1")

        def agent(actor_id: str) -> ActorRef:
            return ActorRef(actor_id, "agent", authority="A1")

        return GraphDefinition(
            graph_id="career-mobility",
            version="0.1.0",
            start_node="load_career_context",
            nodes=(
                GraphNode("load_career_context", service("career-intelligence-service"), "career.load", "career.context"),
                GraphNode("build_profile", agent("career-profile-agent"), "career.profile", "career.profile"),
                GraphNode("analyse_roles", agent("role-transition-agent"), "career.roles", "career.roles"),
                GraphNode("package_evidence", agent("career-evidence-packaging-agent"), "career.evidence", "career.evidence"),
                GraphNode("prepare_interview", agent("interview-practice-agent"), "career.interview", "career.interview"),
                GraphNode("plan_actions", agent("career-action-agent"), "career.actions", "career.actions"),
                GraphNode("assure_guidance", service("career-guidance-assurance"), "career.assure", "career.assurance"),
                GraphNode("finalize_guidance", service("career-guidance-record"), "career.finalize", "career.final"),
            ),
            edges=(
                GraphEdge("load_career_context", "build_profile"),
                GraphEdge("build_profile", "analyse_roles"),
                GraphEdge("analyse_roles", "package_evidence"),
                GraphEdge("package_evidence", "prepare_interview"),
                GraphEdge("prepare_interview", "plan_actions"),
                GraphEdge("plan_actions", "assure_guidance"),
                GraphEdge("assure_guidance", "finalize_guidance"),
            ),
        )

    def register(self) -> None:
        self.kernel.register_handler("career.load", self._load)
        self.kernel.register_handler("career.profile", self._profile)
        self.kernel.register_handler("career.roles", self._roles)
        self.kernel.register_handler("career.evidence", self._evidence)
        self.kernel.register_handler("career.interview", self._interview)
        self.kernel.register_handler("career.actions", self._actions)
        self.kernel.register_handler("career.assure", self._assure)
        self.kernel.register_handler("career.finalize", self._finalize)
        self.kernel.register_evaluator("career.context", self._evaluate_context)
        self.kernel.register_evaluator("career.profile", self._evaluate_profile)
        self.kernel.register_evaluator("career.roles", self._evaluate_roles)
        self.kernel.register_evaluator("career.evidence", self._evaluate_evidence)
        self.kernel.register_evaluator("career.interview", self._evaluate_interview)
        self.kernel.register_evaluator("career.actions", self._evaluate_actions)
        self.kernel.register_evaluator(
            "career.assurance",
            lambda state, result: (result.patch.get("career_assurance", {}).get("passed") is True, "career guidance assurance required"),
        )
        self.kernel.register_evaluator(
            "career.final",
            lambda state, result: ("career_packet" in result.patch, "career packet required"),
        )

    def start(self, *, execution_id: str, instance_id: str):
        definition = self.definition()
        execution = self.kernel.start(
            definition,
            execution_id=execution_id,
            state={"instance_id": instance_id, "career_status": "started"},
        )
        return definition, self.kernel.run(definition, execution)

    def _load(self, state: dict[str, Any]) -> NodeResult:
        context = self.intelligence.build(state["instance_id"])
        return NodeResult(
            patch={"career_context": context.as_payload()},
            evidence=[
                {
                    "type": "accepted_capability_context",
                    "capability_count": len(context.accepted_capabilities),
                    "role_count": len(context.role_alignments),
                }
            ],
        )

    @staticmethod
    def _context(state: dict[str, Any]) -> CareerModelContext:
        from runtime.career_intelligence import CareerCapabilityEvidence, RoleEvidenceAlignment

        payload = state["career_context"]
        return CareerModelContext(
            pathway_id=payload["pathway_id"],
            learning_version=payload["learning_version"],
            accepted_capabilities=tuple(
                CareerCapabilityEvidence(
                    capability_id=item["capability_id"],
                    capability_name=item["capability_name"],
                    target_level=item["target_level"],
                    standard_id=item["standard_id"],
                    standard_description=item["standard_description"],
                )
                for item in payload["accepted_capabilities"]
            ),
            role_alignments=tuple(
                RoleEvidenceAlignment(
                    role_name=item["role_name"],
                    required_capabilities=tuple(item["required_capabilities"]),
                    signaled_capabilities=tuple(item["signaled_capabilities"]),
                    matched_capabilities=tuple(item["matched_capabilities"]),
                    missing_capabilities=tuple(item["missing_capabilities"]),
                    evidence_alignment=float(item["evidence_alignment"]),
                    relation_ids=tuple(item["relation_ids"]),
                    research_execution_ids=tuple(item["research_execution_ids"]),
                )
                for item in payload["role_alignments"]
            ),
        )

    def _profile(self, state: dict[str, Any]) -> NodeResult:
        output = self.provider.profile(self._context(state))
        return NodeResult(patch={"career_profile": output}, evidence=[{"type": "career_profile_interpretation"}])

    def _roles(self, state: dict[str, Any]) -> NodeResult:
        output = self.provider.analyze_role_transitions(self._context(state))
        return NodeResult(patch={"role_transition": output}, evidence=[{"type": "role_transition_interpretation"}])

    def _evidence(self, state: dict[str, Any]) -> NodeResult:
        output = self.provider.package_evidence(self._context(state))
        return NodeResult(patch={"evidence_packaging": output}, evidence=[{"type": "career_evidence_packaging"}])

    def _interview(self, state: dict[str, Any]) -> NodeResult:
        output = self.provider.prepare_interview_practice(self._context(state))
        return NodeResult(patch={"interview_practice": output}, evidence=[{"type": "interview_practice"}])

    def _actions(self, state: dict[str, Any]) -> NodeResult:
        output = self.provider.plan_actions(self._context(state))
        return NodeResult(patch={"career_actions": output}, evidence=[{"type": "learner_controlled_career_actions"}])

    @staticmethod
    def _assure(state: dict[str, Any]) -> NodeResult:
        return NodeResult(
            patch={
                "career_assurance": {
                    "passed": True,
                    "external_action_authorized": False,
                    "employer_decision_authorized": False,
                    "hiring_prediction_authorized": False,
                    "immigration_or_licensing_decision_authorized": False,
                }
            },
            evidence=[{"type": "career_boundary_assurance"}],
        )

    @staticmethod
    def _finalize(state: dict[str, Any]) -> NodeResult:
        packet = {
            "pathway_id": state["career_context"]["pathway_id"],
            "learning_version": state["career_context"]["learning_version"],
            "accepted_capabilities": state["career_context"]["accepted_capabilities"],
            "role_alignments": state["career_context"]["role_alignments"],
            "career_profile": state["career_profile"],
            "role_transition": state["role_transition"],
            "evidence_packaging": state["evidence_packaging"],
            "interview_practice": state["interview_practice"],
            "career_actions": state["career_actions"],
            "assurance": state["career_assurance"],
        }
        return NodeResult(
            patch={"career_packet": packet, "career_status": "guidance_ready"},
            evidence=[{"type": "career_guidance_packet"}],
        )

    @staticmethod
    def _allowed(state: dict[str, Any]) -> tuple[set[str], set[tuple[str, str]], set[str], dict[str, set[str]]]:
        capabilities = state["career_context"]["accepted_capabilities"]
        capability_ids = {item["capability_id"] for item in capabilities}
        standards = {(item["capability_id"], item["standard_id"]) for item in capabilities}
        role_names = {item["role_name"] for item in state["career_context"]["role_alignments"]}
        role_missing = {
            item["role_name"]: set(item["missing_capabilities"])
            for item in state["career_context"]["role_alignments"]
        }
        return capability_ids, standards, role_names, role_missing

    def _evaluate_context(self, state: dict[str, Any], result: NodeResult) -> tuple[bool, str]:
        payload = result.patch.get("career_context")
        if not isinstance(payload, dict) or not payload.get("accepted_capabilities"):
            return False, "accepted capability context required"
        forbidden_keys = {
            "learner_ref",
            "learner_id",
            "cohort_id",
            "instance_id",
            "submission_id",
            "artifact_refs",
            "artifact_ref",
            "accepted_by",
            "email",
            "name",
            "attendance",
            "support",
            "credential",
            "immigration_status",
        }

        def walk(value: Any) -> bool:
            if isinstance(value, dict):
                if forbidden_keys.intersection(value):
                    return False
                return all(walk(item) for item in value.values())
            if isinstance(value, list):
                return all(walk(item) for item in value)
            return True

        if not walk(payload):
            return False, "career model context contains a prohibited learner field"
        return True, "career context is deidentified and based on accepted evidence"

    def _evaluate_profile(self, state: dict[str, Any], result: NodeResult) -> tuple[bool, str]:
        allowed_ids, _, _, _ = self._allowed(state)
        items = result.patch.get("career_profile", {}).get("demonstrated_capabilities", [])
        returned = [item.get("capability_id") for item in items]
        if set(returned) != allowed_ids or len(returned) != len(set(returned)):
            return False, "career profile must represent each accepted capability exactly once"
        return True, "career profile uses accepted capabilities only"

    def _evaluate_roles(self, state: dict[str, Any], result: NodeResult) -> tuple[bool, str]:
        _, _, allowed_roles, missing_by_role = self._allowed(state)
        roles = result.patch.get("role_transition", {}).get("roles", [])
        seen: set[str] = set()
        for item in roles:
            role = item.get("role_name")
            if role not in allowed_roles or role in seen:
                return False, "role transition output contains an unknown or duplicate role"
            seen.add(role)
            if not set(item.get("capability_gaps", [])).issubset(missing_by_role.get(role, set())):
                return False, "role transition output introduced a capability gap not supported by Work Intelligence"
        return True, "role transition output stays within deterministic role alignments"

    def _evaluate_evidence(self, state: dict[str, Any], result: NodeResult) -> tuple[bool, str]:
        _, allowed_pairs, _, _ = self._allowed(state)
        cards = result.patch.get("evidence_packaging", {}).get("cards", [])
        returned = [(item.get("capability_id"), item.get("standard_id")) for item in cards]
        if set(returned) != allowed_pairs or len(returned) != len(set(returned)):
            return False, "evidence packaging must represent each accepted capability standard exactly once"
        return True, "evidence packaging uses human-accepted capability standards only"

    def _evaluate_interview(self, state: dict[str, Any], result: NodeResult) -> tuple[bool, str]:
        allowed_ids, _, allowed_roles, _ = self._allowed(state)
        for item in result.patch.get("interview_practice", {}).get("questions", []):
            if item.get("role_name") not in allowed_roles:
                return False, "interview practice introduced a role outside Work Intelligence"
            if not set(item.get("capability_ids", [])).issubset(allowed_ids):
                return False, "interview practice introduced capability IDs without accepted evidence"
        return True, "interview practice remains evidence bounded"

    def _evaluate_actions(self, state: dict[str, Any], result: NodeResult) -> tuple[bool, str]:
        allowed_ids, _, allowed_roles, _ = self._allowed(state)
        allowed_types = {"practice", "learning", "portfolio_preparation", "interview_practice", "employer_research"}
        actions = result.patch.get("career_actions", {}).get("actions", [])
        if not actions:
            return False, "career action plan requires at least one learner-controlled action"
        for item in actions:
            if item.get("action_type") not in allowed_types:
                return False, "career action plan contains an external or unsupported action type"
            if not set(item.get("related_role_names", [])).issubset(allowed_roles):
                return False, "career action plan introduced a role outside Work Intelligence"
            if not set(item.get("related_capability_ids", [])).issubset(allowed_ids):
                return False, "career action plan introduced capability IDs without accepted evidence"
        return True, "career actions remain learner controlled and non-executing"
