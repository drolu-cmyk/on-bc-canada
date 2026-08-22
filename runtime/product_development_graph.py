"""Product-development graph for accountable agent-assisted platform changes.

The graph coordinates product, experience, interface, copy, brand, engineering,
cloud, security, accessibility, and quality workers. Agents may analyze and
recommend. A release packet reaches an A3 human gate only when deterministic
release assurance finds no blocking review status.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from runtime.graph_kernel import ActorRef, GraphDefinition, GraphEdge, GraphKernel, GraphNode, NodeResult


class ProductDevelopmentProvider(Protocol):
    def normalize(self, request: dict[str, Any]) -> dict[str, Any]: ...
    def analyze_product(self, request: dict[str, Any]) -> dict[str, Any]: ...
    def analyze_experience(self, request: dict[str, Any], product: dict[str, Any]) -> dict[str, Any]: ...
    def design_interface(self, request: dict[str, Any], product: dict[str, Any], experience: dict[str, Any]) -> dict[str, Any]: ...
    def review_copy(self, request: dict[str, Any], product: dict[str, Any], interface: dict[str, Any]) -> dict[str, Any]: ...
    def review_brand(self, request: dict[str, Any], interface: dict[str, Any], copy: dict[str, Any]) -> dict[str, Any]: ...
    def plan_engineering(self, request: dict[str, Any], product: dict[str, Any], experience: dict[str, Any], interface: dict[str, Any]) -> dict[str, Any]: ...
    def review_cloud(self, request: dict[str, Any], engineering: dict[str, Any]) -> dict[str, Any]: ...
    def review_security(self, request: dict[str, Any], engineering: dict[str, Any], cloud: dict[str, Any]) -> dict[str, Any]: ...
    def review_accessibility(self, request: dict[str, Any], experience: dict[str, Any], interface: dict[str, Any]) -> dict[str, Any]: ...
    def plan_quality(
        self,
        request: dict[str, Any],
        product: dict[str, Any],
        engineering: dict[str, Any],
        security: dict[str, Any],
        accessibility: dict[str, Any],
    ) -> dict[str, Any]: ...


@dataclass
class ProductDevelopmentGraph:
    kernel: GraphKernel
    provider: ProductDevelopmentProvider

    @staticmethod
    def definition() -> GraphDefinition:
        def service(actor_id: str, authority: str = "A1") -> ActorRef:
            return ActorRef(actor_id=actor_id, kind="service", authority=authority)

        def agent(actor_id: str) -> ActorRef:
            return ActorRef(actor_id=actor_id, kind="agent", authority="A1")

        return GraphDefinition(
            graph_id="product-development",
            version="0.1.0",
            start_node="normalize_request",
            nodes=(
                GraphNode("normalize_request", service("product-contract"), "product.normalize", "product.request"),
                GraphNode("product_analysis", agent("product-agent"), "product.analysis", "product.analysis"),
                GraphNode("experience_analysis", agent("experience-agent"), "product.experience", "product.experience"),
                GraphNode("interface_design", agent("ui-design-agent"), "product.interface", "product.interface"),
                GraphNode("copy_review", agent("copy-agent"), "product.copy", "product.copy"),
                GraphNode("brand_review", agent("brand-agent"), "product.brand", "product.brand"),
                GraphNode("engineering_plan", agent("engineering-agent"), "product.engineering", "product.engineering"),
                GraphNode("cloud_review", agent("cloud-agent"), "product.cloud", "product.cloud"),
                GraphNode("security_review", agent("security-agent"), "product.security", "product.security"),
                GraphNode("accessibility_review", agent("accessibility-agent"), "product.accessibility", "product.accessibility"),
                GraphNode("quality_plan", agent("quality-agent"), "product.quality", "product.quality"),
                GraphNode("release_assurance", service("release-assurance"), "product.assure", "product.release_assurance"),
                GraphNode(
                    "release_review",
                    ActorRef("release-accountable-human", "human", authority="A3"),
                    approval_reason="Release packet passed automated assurance. Human release authorization is required.",
                ),
                GraphNode("finalize_release", service("release-record", authority="A2"), "product.finalize_release", "product.final"),
                GraphNode("finalize_blocked", service("blocked-release-record"), "product.finalize_blocked", "product.final"),
            ),
            edges=(
                GraphEdge("normalize_request", "product_analysis"),
                GraphEdge("product_analysis", "experience_analysis"),
                GraphEdge("experience_analysis", "interface_design"),
                GraphEdge("interface_design", "copy_review"),
                GraphEdge("copy_review", "brand_review"),
                GraphEdge("brand_review", "engineering_plan"),
                GraphEdge("engineering_plan", "cloud_review"),
                GraphEdge("cloud_review", "security_review"),
                GraphEdge("security_review", "accessibility_review"),
                GraphEdge("accessibility_review", "quality_plan"),
                GraphEdge("quality_plan", "release_assurance"),
                GraphEdge("release_assurance", "release_review", route="review"),
                GraphEdge("release_assurance", "finalize_blocked", route="blocked"),
                GraphEdge("release_review", "finalize_release", route="approved"),
            ),
        )

    def register(self) -> None:
        handlers = {
            "product.normalize": self._normalize,
            "product.analysis": self._product,
            "product.experience": self._experience,
            "product.interface": self._interface,
            "product.copy": self._copy,
            "product.brand": self._brand,
            "product.engineering": self._engineering,
            "product.cloud": self._cloud,
            "product.security": self._security,
            "product.accessibility": self._accessibility,
            "product.quality": self._quality,
            "product.assure": self._assure,
            "product.finalize_release": self._finalize_release,
            "product.finalize_blocked": self._finalize_blocked,
        }
        for name, handler in handlers.items():
            self.kernel.register_handler(name, handler)

        for evaluator_name, key in (
            ("product.request", "request"),
            ("product.analysis", "product_analysis"),
            ("product.experience", "experience_analysis"),
            ("product.interface", "interface_design"),
            ("product.copy", "copy_review"),
            ("product.brand", "brand_review"),
            ("product.engineering", "engineering_plan"),
            ("product.cloud", "cloud_review"),
            ("product.security", "security_review"),
            ("product.accessibility", "accessibility_review"),
            ("product.quality", "quality_plan"),
            ("product.release_assurance", "release_assurance"),
            ("product.final", "release_record"),
        ):
            self.kernel.register_evaluator(
                evaluator_name,
                lambda state, result, required_key=key: (required_key in result.patch, f"{required_key} output required"),
            )

    def start(self, *, execution_id: str, request: dict[str, Any]):
        definition = self.definition()
        execution = self.kernel.start(
            definition,
            execution_id=execution_id,
            state={"input_request": request, "product_status": "started"},
        )
        return definition, self.kernel.run(definition, execution)

    def _normalize(self, state: dict[str, Any]) -> NodeResult:
        request = self.provider.normalize(state["input_request"])
        return NodeResult(patch={"request": request}, evidence=[{"type": "product_request"}])

    def _product(self, state: dict[str, Any]) -> NodeResult:
        result = self.provider.analyze_product(state["request"])
        return NodeResult(patch={"product_analysis": result}, evidence=[{"type": "product_analysis"}])

    def _experience(self, state: dict[str, Any]) -> NodeResult:
        result = self.provider.analyze_experience(state["request"], state["product_analysis"])
        return NodeResult(patch={"experience_analysis": result}, evidence=[{"type": "experience_analysis"}])

    def _interface(self, state: dict[str, Any]) -> NodeResult:
        result = self.provider.design_interface(state["request"], state["product_analysis"], state["experience_analysis"])
        return NodeResult(patch={"interface_design": result}, evidence=[{"type": "interface_design"}])

    def _copy(self, state: dict[str, Any]) -> NodeResult:
        result = self.provider.review_copy(state["request"], state["product_analysis"], state["interface_design"])
        return NodeResult(patch={"copy_review": result}, evidence=[{"type": "copy_review"}])

    def _brand(self, state: dict[str, Any]) -> NodeResult:
        result = self.provider.review_brand(state["request"], state["interface_design"], state["copy_review"])
        return NodeResult(patch={"brand_review": result}, evidence=[{"type": "brand_review"}])

    def _engineering(self, state: dict[str, Any]) -> NodeResult:
        result = self.provider.plan_engineering(
            state["request"], state["product_analysis"], state["experience_analysis"], state["interface_design"]
        )
        return NodeResult(patch={"engineering_plan": result}, evidence=[{"type": "engineering_plan"}])

    def _cloud(self, state: dict[str, Any]) -> NodeResult:
        result = self.provider.review_cloud(state["request"], state["engineering_plan"])
        return NodeResult(patch={"cloud_review": result}, evidence=[{"type": "cloud_review", "status": result.get("status")}])

    def _security(self, state: dict[str, Any]) -> NodeResult:
        result = self.provider.review_security(state["request"], state["engineering_plan"], state["cloud_review"])
        return NodeResult(patch={"security_review": result}, evidence=[{"type": "security_review", "status": result.get("status")}])

    def _accessibility(self, state: dict[str, Any]) -> NodeResult:
        result = self.provider.review_accessibility(state["request"], state["experience_analysis"], state["interface_design"])
        return NodeResult(patch={"accessibility_review": result}, evidence=[{"type": "accessibility_review", "status": result.get("status")}])

    def _quality(self, state: dict[str, Any]) -> NodeResult:
        result = self.provider.plan_quality(
            state["request"],
            state["product_analysis"],
            state["engineering_plan"],
            state["security_review"],
            state["accessibility_review"],
        )
        return NodeResult(patch={"quality_plan": result}, evidence=[{"type": "quality_plan", "status": result.get("status")}])

    @staticmethod
    def _assure(state: dict[str, Any]) -> NodeResult:
        review_keys = ("copy_review", "brand_review", "cloud_review", "security_review", "accessibility_review", "quality_plan")
        blocking: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        for key in review_keys:
            review = state[key]
            status = review.get("status", "block")
            issues = list(review.get("release_blockers", []))
            if status == "block" or issues:
                blocking.append({"review": key, "issues": issues or ["review returned blocking status"]})
            elif status == "warn":
                warnings.append({"review": key, "issues": list(review.get("warnings", []))})
        assurance = {
            "status": "blocked" if blocking else "ready_for_human_review",
            "blocking": blocking,
            "warnings": warnings,
        }
        return NodeResult(
            patch={"release_assurance": assurance},
            evidence=[{"type": "release_assurance", "blocking_review_count": len(blocking)}],
            route="blocked" if blocking else "review",
        )

    @staticmethod
    def _release_packet(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "request": state["request"],
            "product": state["product_analysis"],
            "experience": state["experience_analysis"],
            "interface": state["interface_design"],
            "copy": state["copy_review"],
            "brand": state["brand_review"],
            "engineering": state["engineering_plan"],
            "cloud": state["cloud_review"],
            "security": state["security_review"],
            "accessibility": state["accessibility_review"],
            "quality": state["quality_plan"],
            "assurance": state["release_assurance"],
        }

    @classmethod
    def _finalize_release(cls, state: dict[str, Any]) -> NodeResult:
        record = {"status": "authorized_for_implementation", "packet": cls._release_packet(state)}
        return NodeResult(
            patch={"release_record": record, "product_status": "complete"},
            evidence=[{"type": "release_packet", "status": record["status"]}],
        )

    @classmethod
    def _finalize_blocked(cls, state: dict[str, Any]) -> NodeResult:
        record = {"status": "blocked", "packet": cls._release_packet(state)}
        return NodeResult(
            patch={"release_record": record, "product_status": "blocked"},
            evidence=[{"type": "release_packet", "status": record["status"]}],
        )
