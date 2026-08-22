"""Implementation and delivery graph for authorized product release packets.

Agents design and generate changes from supplied repository context. Deterministic
services validate and apply those changes only inside a constrained staging
workspace, run registered verification commands, and stop at A3 before merge or
production deployment.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

from runtime.graph_kernel import ActorRef, GraphDefinition, GraphEdge, GraphKernel, GraphNode, NodeResult
from runtime.implementation_workspace import FileChange, RegisteredVerificationRunner, StagingWorkspace


class ImplementationProvider(Protocol):
    def normalize(self, request: dict[str, Any]) -> dict[str, Any]: ...
    def plan_changes(self, request: dict[str, Any], repository_context: list[dict[str, Any]]) -> dict[str, Any]: ...
    def generate_changes(
        self,
        request: dict[str, Any],
        repository_context: list[dict[str, Any]],
        plan: dict[str, Any],
    ) -> dict[str, Any]: ...
    def review_code(
        self,
        request: dict[str, Any],
        plan: dict[str, Any],
        applied_changes: list[dict[str, Any]],
        verification: list[dict[str, Any]],
    ) -> dict[str, Any]: ...
    def review_security(
        self,
        request: dict[str, Any],
        plan: dict[str, Any],
        applied_changes: list[dict[str, Any]],
        verification: list[dict[str, Any]],
    ) -> dict[str, Any]: ...
    def review_quality(
        self,
        request: dict[str, Any],
        applied_changes: list[dict[str, Any]],
        verification: list[dict[str, Any]],
    ) -> dict[str, Any]: ...


@dataclass
class ImplementationDeliveryGraph:
    kernel: GraphKernel
    provider: ImplementationProvider
    workspace: StagingWorkspace
    verifier: RegisteredVerificationRunner

    @staticmethod
    def definition() -> GraphDefinition:
        def service(actor_id: str, authority: str = "A1") -> ActorRef:
            return ActorRef(actor_id=actor_id, kind="service", authority=authority)

        def agent(actor_id: str) -> ActorRef:
            return ActorRef(actor_id=actor_id, kind="agent", authority="A1")

        return GraphDefinition(
            graph_id="implementation-delivery",
            version="0.1.0",
            start_node="normalize_request",
            nodes=(
                GraphNode("normalize_request", service("implementation-contract"), "implementation.normalize", "implementation.request"),
                GraphNode("repository_context", service("staging-context"), "implementation.context", "implementation.context"),
                GraphNode("change_plan", agent("implementation-design-agent"), "implementation.plan", "implementation.plan"),
                GraphNode("change_generation", agent("code-generation-agent"), "implementation.generate", "implementation.changes"),
                GraphNode("change_assurance", service("change-assurance"), "implementation.assure_changes", "implementation.change_assurance"),
                GraphNode("apply_staging_changes", service("staging-change-executor", authority="A2"), "implementation.apply", "implementation.applied"),
                GraphNode("run_verification", service("registered-verification-runner", authority="A2"), "implementation.verify", "implementation.verification"),
                GraphNode("code_review", agent("code-review-agent"), "implementation.code_review", "implementation.review"),
                GraphNode("security_review", agent("implementation-security-agent"), "implementation.security_review", "implementation.review"),
                GraphNode("quality_review", agent("implementation-quality-agent"), "implementation.quality_review", "implementation.review"),
                GraphNode("delivery_assurance", service("delivery-assurance"), "implementation.delivery_assurance", "implementation.delivery_assurance"),
                GraphNode(
                    "merge_deploy_review",
                    ActorRef("merge-deploy-accountable-human", "human", authority="A3"),
                    approval_reason="Verified staging changes require human authorization before merge or production deployment.",
                ),
                GraphNode("finalize_candidate", service("delivery-record"), "implementation.finalize_candidate", "implementation.final"),
                GraphNode("finalize_blocked", service("delivery-record"), "implementation.finalize_blocked", "implementation.final"),
            ),
            edges=(
                GraphEdge("normalize_request", "repository_context"),
                GraphEdge("repository_context", "change_plan"),
                GraphEdge("change_plan", "change_generation"),
                GraphEdge("change_generation", "change_assurance"),
                GraphEdge("change_assurance", "apply_staging_changes", route="apply"),
                GraphEdge("change_assurance", "finalize_blocked", route="blocked"),
                GraphEdge("apply_staging_changes", "run_verification"),
                GraphEdge("run_verification", "code_review"),
                GraphEdge("code_review", "security_review"),
                GraphEdge("security_review", "quality_review"),
                GraphEdge("quality_review", "delivery_assurance"),
                GraphEdge("delivery_assurance", "merge_deploy_review", route="review"),
                GraphEdge("delivery_assurance", "finalize_blocked", route="blocked"),
                GraphEdge("merge_deploy_review", "finalize_candidate", route="approved"),
            ),
        )

    def register(self) -> None:
        handlers = {
            "implementation.normalize": self._normalize,
            "implementation.context": self._context,
            "implementation.plan": self._plan,
            "implementation.generate": self._generate,
            "implementation.assure_changes": self._assure_changes,
            "implementation.apply": self._apply,
            "implementation.verify": self._verify,
            "implementation.code_review": self._code_review,
            "implementation.security_review": self._security_review,
            "implementation.quality_review": self._quality_review,
            "implementation.delivery_assurance": self._delivery_assurance,
            "implementation.finalize_candidate": self._finalize_candidate,
            "implementation.finalize_blocked": self._finalize_blocked,
        }
        for name, handler in handlers.items():
            self.kernel.register_handler(name, handler)

        validators = {
            "implementation.request": lambda result: bool(result.patch.get("request", {}).get("release_record")),
            "implementation.context": lambda result: isinstance(result.patch.get("repository_context"), list),
            "implementation.plan": lambda result: bool(result.patch.get("implementation_plan", {}).get("verification_ids")),
            "implementation.changes": lambda result: isinstance(result.patch.get("generated_changes"), list),
            "implementation.change_assurance": lambda result: result.route in {"apply", "blocked"},
            "implementation.applied": lambda result: isinstance(result.patch.get("applied_changes"), list),
            "implementation.verification": lambda result: isinstance(result.patch.get("verification_results"), list),
            "implementation.review": lambda result: result.patch.get("latest_review", {}).get("status") in {"pass", "warn", "block"},
            "implementation.delivery_assurance": lambda result: result.route in {"review", "blocked"},
            "implementation.final": lambda result: "delivery_record" in result.patch,
        }
        for name, validator in validators.items():
            self.kernel.register_evaluator(
                name,
                lambda state, result, check=validator, evaluator_name=name: (check(result), f"{evaluator_name} output required"),
            )

    def start(self, *, execution_id: str, request: dict[str, Any]):
        definition = self.definition()
        execution = self.kernel.start(
            definition,
            execution_id=execution_id,
            state={"input_request": request, "implementation_status": "started", "reviews": {}},
        )
        return definition, self.kernel.run(definition, execution)

    def _normalize(self, state: dict[str, Any]) -> NodeResult:
        request = self.provider.normalize(state["input_request"])
        return NodeResult(
            patch={"request": request},
            evidence=[{"type": "authorized_implementation_request", "source_execution_id": request.get("source_execution_id")}],
        )

    def _context(self, state: dict[str, Any]) -> NodeResult:
        snapshots = [asdict(item) for item in self.workspace.snapshot(state["request"]["context_paths"])]
        return NodeResult(
            patch={"repository_context": snapshots},
            evidence=[{"type": "repository_context", "file_count": len(snapshots)}],
        )

    def _plan(self, state: dict[str, Any]) -> NodeResult:
        plan = self.provider.plan_changes(state["request"], state["repository_context"])
        required = set(state["request"].get("required_verification_ids", []))
        allowed = set(state["request"].get("allowed_verification_ids", []))
        planned = set(plan.get("verification_ids", []))
        if not required.issubset(planned):
            raise ValueError("implementation design omitted an operator-required verification")
        if not planned.issubset(allowed):
            raise ValueError("implementation design selected an unregistered verification")
        authorized_paths = set(state["request"]["context_paths"])
        planned_paths = set(plan.get("files_to_change", []))
        if not planned_paths or not planned_paths.issubset(authorized_paths):
            raise ValueError("implementation design selected a path outside the operator-authorized context")
        return NodeResult(
            patch={"implementation_plan": plan},
            evidence=[{"type": "implementation_design", "verification_count": len(planned)}],
        )

    def _generate(self, state: dict[str, Any]) -> NodeResult:
        generated = self.provider.generate_changes(
            state["request"], state["repository_context"], state["implementation_plan"]
        )
        return NodeResult(
            patch={"generated_changes": list(generated.get("changes", []))},
            evidence=[{"type": "generated_change_set", "file_count": len(generated.get("changes", []))}],
        )

    def _assure_changes(self, state: dict[str, Any]) -> NodeResult:
        try:
            changes = [FileChange(**item) for item in state["generated_changes"]]
            planned_paths = set(state["implementation_plan"].get("files_to_change", []))
            changed_paths = {item.path for item in changes}
            if not changed_paths.issubset(planned_paths):
                raise ValueError("generated change set contains a path outside the implementation design")
            validated = self.workspace.validate_changes(changes)
            assurance = {
                "status": "ready",
                "blockers": [],
                "validated_paths": [item[0].path for item in validated],
            }
            route = "apply"
        except (TypeError, ValueError) as exc:
            assurance = {"status": "blocked", "blockers": [str(exc)], "validated_paths": []}
            route = "blocked"
        return NodeResult(
            patch={"change_assurance": assurance},
            evidence=[{"type": "change_assurance", "status": assurance["status"]}],
            route=route,
        )

    def _apply(self, state: dict[str, Any]) -> NodeResult:
        changes = [FileChange(**item) for item in state["generated_changes"]]
        applied = [asdict(item) for item in self.workspace.apply_changes(changes)]
        return NodeResult(
            patch={"applied_changes": applied},
            evidence=[{"type": "staging_changes_applied", "file_count": len(applied)}],
        )

    def _verify(self, state: dict[str, Any]) -> NodeResult:
        verification_ids = state["implementation_plan"]["verification_ids"]
        results = [asdict(item) for item in self.verifier.run(verification_ids)]
        return NodeResult(
            patch={"verification_results": results},
            evidence=[
                {
                    "type": "registered_verification",
                    "verification_count": len(results),
                    "failed_count": sum(1 for item in results if not item["passed"]),
                }
            ],
        )

    def _store_review(self, state: dict[str, Any], kind: str, review: dict[str, Any]) -> NodeResult:
        reviews = dict(state.get("reviews", {}))
        reviews[kind] = review
        return NodeResult(
            patch={"reviews": reviews, "latest_review": review},
            evidence=[{"type": f"{kind}_review", "status": review.get("status")}],
        )

    def _code_review(self, state: dict[str, Any]) -> NodeResult:
        review = self.provider.review_code(
            state["request"], state["implementation_plan"], state["applied_changes"], state["verification_results"]
        )
        return self._store_review(state, "code", review)

    def _security_review(self, state: dict[str, Any]) -> NodeResult:
        review = self.provider.review_security(
            state["request"], state["implementation_plan"], state["applied_changes"], state["verification_results"]
        )
        return self._store_review(state, "security", review)

    def _quality_review(self, state: dict[str, Any]) -> NodeResult:
        review = self.provider.review_quality(state["request"], state["applied_changes"], state["verification_results"])
        return self._store_review(state, "quality", review)

    @staticmethod
    def _delivery_assurance(state: dict[str, Any]) -> NodeResult:
        blockers: list[str] = []
        failed_verifications = [item["verification_id"] for item in state["verification_results"] if not item["passed"]]
        if failed_verifications:
            blockers.append("failed registered verifications: " + ", ".join(sorted(failed_verifications)))
        for kind, review in state["reviews"].items():
            if review.get("status") == "block":
                blockers.extend(f"{kind}: {item}" for item in review.get("blockers", []) or ["blocking review status"])
            else:
                blockers.extend(f"{kind}: {item}" for item in review.get("blockers", []))
        assurance = {
            "status": "blocked" if blockers else "ready_for_human_review",
            "blockers": blockers,
            "warnings": [
                f"{kind}: {warning}"
                for kind, review in state["reviews"].items()
                for warning in review.get("warnings", [])
            ],
        }
        return NodeResult(
            patch={"delivery_assurance": assurance},
            evidence=[{"type": "delivery_assurance", "blocker_count": len(blockers)}],
            route="blocked" if blockers else "review",
        )

    @staticmethod
    def _packet(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_execution_id": state["request"].get("source_execution_id"),
            "release_record": state["request"]["release_record"],
            "implementation_design": state["implementation_plan"],
            "generated_changes": state["generated_changes"],
            "applied_changes": state.get("applied_changes", []),
            "verification_results": state.get("verification_results", []),
            "reviews": state.get("reviews", {}),
            "delivery_assurance": state.get("delivery_assurance", state.get("change_assurance")),
        }

    @classmethod
    def _finalize_candidate(cls, state: dict[str, Any]) -> NodeResult:
        record = {"status": "authorized_for_merge_or_deploy", "packet": cls._packet(state)}
        return NodeResult(
            patch={"delivery_record": record, "implementation_status": "authorized_for_merge_or_deploy"},
            evidence=[{"type": "delivery_record", "status": record["status"]}],
        )

    @classmethod
    def _finalize_blocked(cls, state: dict[str, Any]) -> NodeResult:
        record = {"status": "blocked", "packet": cls._packet(state)}
        return NodeResult(
            patch={"delivery_record": record, "implementation_status": "blocked"},
            evidence=[{"type": "delivery_record", "status": "blocked"}],
        )
