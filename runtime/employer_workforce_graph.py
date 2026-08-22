"""Organization-level Employer Workforce Graph.

The graph analyzes workflows and bounded AI adoption without individual employee
records or employment decisions. Capability demand remains a research signal and
does not write directly to Work Intelligence or learner curriculum.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from runtime.employer_workforce_context import AggregateMetric, EmployerWorkforceRequest, WorkTask
from runtime.graph_kernel import ActorRef, GraphDefinition, GraphEdge, GraphKernel, GraphNode, NodeResult


class EmployerWorkforceProvider(Protocol):
    def analyze_workflow(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def identify_ai_opportunities(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def analyze_workforce_impact(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def identify_capability_demand(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def analyze_adoption_risk(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def design_pilot(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def define_measurement(self, payload: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class EmployerWorkforceGraph:
    kernel: GraphKernel
    provider: EmployerWorkforceProvider

    @staticmethod
    def definition() -> GraphDefinition:
        def service(actor_id: str) -> ActorRef:
            return ActorRef(actor_id, "service", authority="A1")

        def agent(actor_id: str) -> ActorRef:
            return ActorRef(actor_id, "agent", authority="A1")

        return GraphDefinition(
            graph_id="employer-workforce",
            version="0.1.0",
            start_node="load_request",
            nodes=(
                GraphNode("load_request", service("employer-request-service"), "employer.load", "employer.context"),
                GraphNode("analyse_workflow", agent("employer-workflow-agent"), "employer.workflow", "employer.workflow"),
                GraphNode("identify_ai_opportunities", agent("ai-opportunity-agent"), "employer.opportunities", "employer.opportunities"),
                GraphNode("route_opportunities", service("ai-opportunity-policy"), "employer.route"),
                GraphNode("analyse_workforce_impact", agent("workforce-impact-agent"), "employer.workforce", "employer.workforce"),
                GraphNode("identify_capability_demand", agent("employer-capability-demand-agent"), "employer.capabilities", "employer.capabilities"),
                GraphNode("analyse_adoption_risk", agent("ai-adoption-risk-agent"), "employer.risk", "employer.risk"),
                GraphNode("design_pilot", agent("ai-adoption-pilot-agent"), "employer.pilot", "employer.pilot"),
                GraphNode("define_measurement", agent("ai-adoption-measurement-agent"), "employer.measurement", "employer.measurement"),
                GraphNode("assure_analysis", service("employer-workforce-assurance"), "employer.assure", "employer.assurance"),
                GraphNode("finalize_analysis", service("employer-workforce-record"), "employer.finalize", "employer.final"),
                GraphNode("finalize_no_change", service("employer-workforce-record"), "employer.finalize_no_change", "employer.final"),
            ),
            edges=(
                GraphEdge("load_request", "analyse_workflow"),
                GraphEdge("analyse_workflow", "identify_ai_opportunities"),
                GraphEdge("identify_ai_opportunities", "route_opportunities"),
                GraphEdge("route_opportunities", "analyse_workforce_impact", route="opportunities"),
                GraphEdge("route_opportunities", "finalize_no_change", route="no_change"),
                GraphEdge("analyse_workforce_impact", "identify_capability_demand"),
                GraphEdge("identify_capability_demand", "analyse_adoption_risk"),
                GraphEdge("analyse_adoption_risk", "design_pilot"),
                GraphEdge("design_pilot", "define_measurement"),
                GraphEdge("define_measurement", "assure_analysis"),
                GraphEdge("assure_analysis", "finalize_analysis"),
            ),
        )

    def register(self) -> None:
        self.kernel.register_handler("employer.load", self._load)
        self.kernel.register_handler("employer.workflow", self._workflow)
        self.kernel.register_handler("employer.opportunities", self._opportunities)
        self.kernel.register_handler("employer.route", self._route)
        self.kernel.register_handler("employer.workforce", self._workforce)
        self.kernel.register_handler("employer.capabilities", self._capabilities)
        self.kernel.register_handler("employer.risk", self._risk)
        self.kernel.register_handler("employer.pilot", self._pilot)
        self.kernel.register_handler("employer.measurement", self._measurement)
        self.kernel.register_handler("employer.assure", self._assure)
        self.kernel.register_handler("employer.finalize", self._finalize)
        self.kernel.register_handler("employer.finalize_no_change", self._finalize_no_change)
        self.kernel.register_evaluator("employer.context", self._evaluate_context)
        self.kernel.register_evaluator("employer.workflow", self._evaluate_workflow)
        self.kernel.register_evaluator("employer.opportunities", self._evaluate_opportunities)
        self.kernel.register_evaluator("employer.workforce", self._evaluate_workforce)
        self.kernel.register_evaluator("employer.capabilities", self._evaluate_capabilities)
        self.kernel.register_evaluator("employer.risk", self._evaluate_risk)
        self.kernel.register_evaluator("employer.pilot", self._evaluate_pilot)
        self.kernel.register_evaluator("employer.measurement", self._evaluate_measurement)
        self.kernel.register_evaluator(
            "employer.assurance",
            lambda state, result: (result.patch.get("employer_assurance", {}).get("passed") is True, "employer workforce assurance required"),
        )
        self.kernel.register_evaluator(
            "employer.final",
            lambda state, result: ("employer_workforce_packet" in result.patch, "employer workforce packet required"),
        )

    def start(self, *, execution_id: str, request: EmployerWorkforceRequest):
        definition = self.definition()
        execution = self.kernel.start(
            definition,
            execution_id=execution_id,
            state={"employer_request": request.as_local_record(), "employer_status": "started"},
        )
        return definition, self.kernel.run(definition, execution)

    @staticmethod
    def _request(state: dict[str, Any]) -> EmployerWorkforceRequest:
        payload = state["employer_request"]
        return EmployerWorkforceRequest(
            organization_ref=payload["organization_ref"],
            sector=payload["sector"],
            workflow_name=payload["workflow_name"],
            workflow_purpose=payload["workflow_purpose"],
            tasks=tuple(
                WorkTask(
                    task_id=item["task_id"],
                    description=item["description"],
                    role_labels=tuple(item["role_labels"]),
                    current_tools=tuple(item["current_tools"]),
                    pain_points=tuple(item["pain_points"]),
                )
                for item in payload["tasks"]
            ),
            constraints=tuple(payload["constraints"]),
            baseline_metrics=tuple(
                AggregateMetric(
                    metric_id=item["metric_id"],
                    description=item["description"],
                    value=float(item["value"]),
                    unit=item["unit"],
                )
                for item in payload["baseline_metrics"]
            ),
            desired_outcomes=tuple(payload["desired_outcomes"]),
            data_classification=payload["data_classification"],
        )

    def _base_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._request(state).as_model_payload()

    def _load(self, state: dict[str, Any]) -> NodeResult:
        payload = self._base_payload(state)
        return NodeResult(
            patch={"employer_model_context": payload},
            evidence=[{"type": "organization_workflow_context", "task_count": len(payload["tasks"])}],
        )

    def _workflow(self, state: dict[str, Any]) -> NodeResult:
        output = self.provider.analyze_workflow({"request": state["employer_model_context"]})
        return NodeResult(patch={"workflow_analysis": output}, evidence=[{"type": "workflow_analysis"}])

    def _opportunities(self, state: dict[str, Any]) -> NodeResult:
        output = self.provider.identify_ai_opportunities(
            {"request": state["employer_model_context"], "workflow_analysis": state["workflow_analysis"]}
        )
        return NodeResult(patch={"ai_opportunities": output}, evidence=[{"type": "ai_opportunity_analysis"}])

    @staticmethod
    def _route(state: dict[str, Any]) -> NodeResult:
        opportunities = state["ai_opportunities"].get("opportunities", [])
        return NodeResult(route="opportunities" if opportunities else "no_change")

    def _workforce(self, state: dict[str, Any]) -> NodeResult:
        output = self.provider.analyze_workforce_impact(
            {
                "request": state["employer_model_context"],
                "workflow_analysis": state["workflow_analysis"],
                "ai_opportunities": state["ai_opportunities"],
            }
        )
        return NodeResult(patch={"workforce_impact": output}, evidence=[{"type": "workforce_impact_analysis"}])

    def _capabilities(self, state: dict[str, Any]) -> NodeResult:
        output = self.provider.identify_capability_demand(
            {
                "request": state["employer_model_context"],
                "workflow_analysis": state["workflow_analysis"],
                "ai_opportunities": state["ai_opportunities"],
                "workforce_impact": state["workforce_impact"],
            }
        )
        return NodeResult(patch={"capability_demand": output}, evidence=[{"type": "employer_capability_signal"}])

    def _risk(self, state: dict[str, Any]) -> NodeResult:
        output = self.provider.analyze_adoption_risk(
            {
                "request": state["employer_model_context"],
                "ai_opportunities": state["ai_opportunities"],
                "workforce_impact": state["workforce_impact"],
                "capability_demand": state["capability_demand"],
            }
        )
        return NodeResult(patch={"adoption_risk": output}, evidence=[{"type": "ai_adoption_risk"}])

    def _pilot(self, state: dict[str, Any]) -> NodeResult:
        output = self.provider.design_pilot(
            {
                "request": state["employer_model_context"],
                "ai_opportunities": state["ai_opportunities"],
                "adoption_risk": state["adoption_risk"],
            }
        )
        return NodeResult(patch={"pilot_design": output}, evidence=[{"type": "bounded_pilot_design"}])

    def _measurement(self, state: dict[str, Any]) -> NodeResult:
        output = self.provider.define_measurement(
            {
                "request": state["employer_model_context"],
                "pilot_design": state["pilot_design"],
                "adoption_risk": state["adoption_risk"],
            }
        )
        return NodeResult(patch={"adoption_measurement": output}, evidence=[{"type": "adoption_measurement"}])

    @staticmethod
    def _assure(state: dict[str, Any]) -> NodeResult:
        return NodeResult(
            patch={
                "employer_assurance": {
                    "passed": True,
                    "employee_decision_authorized": False,
                    "production_deployment_authorized": False,
                    "external_contact_authorized": False,
                    "work_intelligence_write_authorized": False,
                    "capability_signals_require_research_validation": True,
                }
            },
            evidence=[{"type": "employer_workforce_boundary_assurance"}],
        )

    @staticmethod
    def _finalize(state: dict[str, Any]) -> NodeResult:
        packet = {
            "organization_ref": state["employer_request"]["organization_ref"],
            "workflow": state["employer_model_context"],
            "workflow_analysis": state["workflow_analysis"],
            "ai_opportunities": state["ai_opportunities"],
            "workforce_impact": state["workforce_impact"],
            "capability_demand": state["capability_demand"],
            "adoption_risk": state["adoption_risk"],
            "pilot_design": state["pilot_design"],
            "adoption_measurement": state["adoption_measurement"],
            "assurance": state["employer_assurance"],
        }
        return NodeResult(
            patch={"employer_workforce_packet": packet, "employer_status": "analysis_ready"},
            evidence=[{"type": "employer_workforce_packet"}],
        )

    @staticmethod
    def _finalize_no_change(state: dict[str, Any]) -> NodeResult:
        packet = {
            "organization_ref": state["employer_request"]["organization_ref"],
            "workflow": state["employer_model_context"],
            "workflow_analysis": state["workflow_analysis"],
            "ai_opportunities": state["ai_opportunities"],
            "outcome": "no_justified_ai_opportunity",
            "assurance": {
                "employee_decision_authorized": False,
                "production_deployment_authorized": False,
                "external_contact_authorized": False,
                "work_intelligence_write_authorized": False,
            },
        }
        return NodeResult(
            patch={"employer_workforce_packet": packet, "employer_status": "no_change"},
            evidence=[{"type": "no_justified_ai_opportunity"}],
        )

    @staticmethod
    def _allowed(state: dict[str, Any]) -> tuple[set[str], set[str], set[str], set[str]]:
        context = state["employer_model_context"]
        task_ids = {item["task_id"] for item in context["tasks"]}
        roles = set(context["role_labels"])
        metric_ids = {item["metric_id"] for item in context["baseline_metrics"]}
        opportunities = {item["opportunity_id"] for item in state.get("ai_opportunities", {}).get("opportunities", [])}
        return task_ids, roles, metric_ids, opportunities

    def _evaluate_context(self, state: dict[str, Any], result: NodeResult) -> tuple[bool, str]:
        payload = result.patch.get("employer_model_context")
        if not isinstance(payload, dict) or not payload.get("tasks"):
            return False, "organization-level workflow context required"
        if "organization_ref" in payload:
            return False, "organization reference must not enter model context"
        forbidden_keys = {
            "employee_id",
            "employee_name",
            "candidate_id",
            "performance_score",
            "compensation",
            "protected_characteristic",
            "email",
            "phone",
        }

        def walk(value: Any) -> bool:
            if isinstance(value, dict):
                if forbidden_keys.intersection(value):
                    return False
                return all(walk(item) for item in value.values())
            if isinstance(value, list):
                return all(walk(item) for item in value)
            return True

        return (walk(payload), "model context contains organization-level work only")

    def _evaluate_workflow(self, state: dict[str, Any], result: NodeResult) -> tuple[bool, str]:
        task_ids, _, _, _ = self._allowed({**state, "ai_opportunities": {"opportunities": []}})
        findings = result.patch.get("workflow_analysis", {}).get("findings", [])
        if not findings:
            return False, "workflow analysis requires at least one task finding"
        if any(item.get("task_id") not in task_ids for item in findings):
            return False, "workflow analysis introduced an unknown task ID"
        return True, "workflow analysis references supplied tasks only"

    def _evaluate_opportunities(self, state: dict[str, Any], result: NodeResult) -> tuple[bool, str]:
        task_ids = {item["task_id"] for item in state["employer_model_context"]["tasks"]}
        opportunities = result.patch.get("ai_opportunities", {}).get("opportunities", [])
        ids = [item.get("opportunity_id") for item in opportunities]
        if len(ids) != len(set(ids)) or any(not value for value in ids):
            return False, "AI opportunity IDs must be non-empty and unique"
        for item in opportunities:
            if not set(item.get("task_ids", [])).issubset(task_ids):
                return False, "AI opportunity introduced an unknown task ID"
        if not opportunities and not result.patch.get("ai_opportunities", {}).get("no_change_reasons"):
            return False, "no-opportunity analysis requires an explicit reason"
        return True, "AI opportunities remain bounded to supplied tasks"

    def _evaluate_workforce(self, state: dict[str, Any], result: NodeResult) -> tuple[bool, str]:
        task_ids, roles, _, _ = self._allowed(state)
        for item in result.patch.get("workforce_impact", {}).get("role_impacts", []):
            if item.get("role_label") not in roles:
                return False, "workforce impact introduced an unknown role label"
            if not set(item.get("affected_task_ids", [])).issubset(task_ids):
                return False, "workforce impact introduced an unknown task ID"
        return True, "workforce impact stays at role and task level"

    def _evaluate_capabilities(self, state: dict[str, Any], result: NodeResult) -> tuple[bool, str]:
        task_ids, _, _, _ = self._allowed(state)
        for item in result.patch.get("capability_demand", {}).get("demands", []):
            if not set(item.get("source_task_ids", [])).issubset(task_ids):
                return False, "capability demand introduced an unknown task ID"
            if item.get("research_validation_required") is not True:
                return False, "employer capability signals must require research validation"
        return True, "capability demand remains a research signal"

    def _evaluate_risk(self, state: dict[str, Any], result: NodeResult) -> tuple[bool, str]:
        _, _, _, opportunities = self._allowed(state)
        for item in result.patch.get("adoption_risk", {}).get("risks", []):
            if item.get("opportunity_id") not in opportunities:
                return False, "adoption risk introduced an unknown AI opportunity"
        return True, "adoption risks reference supplied opportunities only"

    def _evaluate_pilot(self, state: dict[str, Any], result: NodeResult) -> tuple[bool, str]:
        task_ids, _, _, opportunities = self._allowed(state)
        pilot = result.patch.get("pilot_design", {})
        if not set(pilot.get("opportunity_ids", [])).issubset(opportunities):
            return False, "pilot introduced an unknown AI opportunity"
        if not set(pilot.get("task_ids", [])).issubset(task_ids):
            return False, "pilot introduced an unknown task ID"
        if not pilot.get("stop_conditions"):
            return False, "bounded pilot requires stop conditions"
        return True, "pilot remains bounded to reviewed tasks and opportunities"

    def _evaluate_measurement(self, state: dict[str, Any], result: NodeResult) -> tuple[bool, str]:
        _, _, metric_ids, _ = self._allowed(state)
        measures = result.patch.get("adoption_measurement", {}).get("measures", [])
        if not measures:
            return False, "adoption measurement requires at least one organization-level measure"
        for item in measures:
            baseline = item.get("baseline_metric_id")
            if baseline is not None and baseline not in metric_ids:
                return False, "measurement introduced an unknown baseline metric ID"
        return True, "measurement stays at organization level"
