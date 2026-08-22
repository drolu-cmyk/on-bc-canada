from __future__ import annotations

import importlib.util
import unittest
from types import SimpleNamespace

from runtime.openai_employer_workforce_provider import (
    AIOpportunity,
    AIOpportunityOutput,
    AdoptionMeasurementOutput,
    AdoptionRisk,
    AdoptionRiskOutput,
    CapabilityDemand,
    CapabilityDemandOutput,
    EmployerWorkforceAgentSet,
    MeasurementItem,
    OpenAIEmployerWorkforceProvider,
    PilotDesignOutput,
    RoleImpact,
    WorkforceImpactOutput,
    WorkflowAnalysisOutput,
    WorkflowFinding,
    build_employer_workforce_agents,
)
from runtime.test_employer_workforce_context import employer_request


class FakeAgent:
    def __init__(self, name: str):
        self.name = name


class FakeRunner:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def run_sync(self, agent, input, **kwargs):
        self.calls.append((agent.name, input, kwargs))
        return SimpleNamespace(final_output=self.outputs.pop(0))


class OpenAIEmployerWorkforceProviderTests(unittest.TestCase):
    def setUp(self):
        self.agents = EmployerWorkforceAgentSet(
            *[FakeAgent(name) for name in ("workflow", "opportunity", "workforce", "capability", "risk", "pilot", "measurement")]
        )

    def test_typed_workers_receive_organization_level_context(self):
        runner = FakeRunner(
            [
                WorkflowAnalysisOutput(
                    workflow_summary="Bounded organization workflow.",
                    findings=[
                        WorkflowFinding(
                            task_id="review-intake",
                            issue="Repeated classification work.",
                        )
                    ],
                ),
                AIOpportunityOutput(
                    opportunities=[
                        AIOpportunity(
                            opportunity_id="classification-assist",
                            task_ids=["review-intake"],
                            pattern="assist",
                            value_hypothesis="Support consistent categories.",
                            automation_boundary="Staff retain final decision.",
                            evidence_needed=["correction rate"],
                        )
                    ]
                ),
                WorkforceImpactOutput(
                    role_impacts=[
                        RoleImpact(
                            role_label="Intake Coordinator",
                            affected_task_ids=["review-intake"],
                            change_type="assist",
                            work_change="Review and correct bounded suggestions.",
                            human_decisions_preserved=["Final category"],
                        )
                    ]
                ),
                CapabilityDemandOutput(
                    demands=[
                        CapabilityDemand(
                            capability_name="AI classification review",
                            observable_work="Evaluate category suggestions against defined workflow criteria.",
                            source_task_ids=["review-intake"],
                            priority="core",
                            research_validation_required=True,
                        )
                    ],
                    note="Research validation required.",
                ),
                AdoptionRiskOutput(
                    risks=[
                        AdoptionRisk(
                            opportunity_id="classification-assist",
                            risk_type="human_oversight",
                            risk="Over-reliance on suggestions.",
                            mitigation="Require explicit confirmation.",
                            stop_condition="Confirmation can be bypassed.",
                        )
                    ]
                ),
                PilotDesignOutput(
                    pilot_id="classification-pilot",
                    opportunity_ids=["classification-assist"],
                    task_ids=["review-intake"],
                    pilot_scope="Bounded test with staff confirmation.",
                    success_measures=["correction rate"],
                    stop_conditions=["Material quality regression"],
                    required_human_approvals=["Pilot start"],
                ),
                AdoptionMeasurementOutput(
                    measures=[
                        MeasurementItem(
                            measure_id="correction-rate",
                            definition="Share of suggestions corrected during the bounded test.",
                            baseline_metric_id=None,
                            interpretation="Interpret with case-mix and label stability.",
                        )
                    ],
                    decision_rules=["Do not increase autonomy without meeting quality and oversight criteria."],
                ),
            ]
        )
        provider = OpenAIEmployerWorkforceProvider(agents=self.agents, runner=runner)
        base = employer_request().as_model_payload()
        workflow = provider.analyze_workflow({"request": base})
        opportunity = provider.identify_ai_opportunities({"request": base, "workflow_analysis": workflow})
        workforce = provider.analyze_workforce_impact({"request": base, "ai_opportunities": opportunity})
        capability = provider.identify_capability_demand({"request": base, "workforce_impact": workforce})
        risk = provider.analyze_adoption_risk({"request": base, "ai_opportunities": opportunity, "capability_demand": capability})
        pilot = provider.design_pilot({"request": base, "ai_opportunities": opportunity, "adoption_risk": risk})
        measurement = provider.define_measurement({"request": base, "pilot_design": pilot})

        self.assertEqual("review-intake", workflow["findings"][0]["task_id"])
        self.assertEqual("classification-assist", opportunity["opportunities"][0]["opportunity_id"])
        self.assertEqual("Intake Coordinator", workforce["role_impacts"][0]["role_label"])
        self.assertTrue(capability["demands"][0]["research_validation_required"])
        self.assertEqual("human_oversight", risk["risks"][0]["risk_type"])
        self.assertEqual("classification-pilot", pilot["pilot_id"])
        self.assertEqual("correction-rate", measurement["measures"][0]["measure_id"])
        self.assertEqual(7, len(runner.calls))
        serialized = "\n".join(call[1] for call in runner.calls)
        self.assertNotIn("org-canada-001", serialized)
        self.assertNotIn("employee_id", serialized)
        self.assertIn("Community intake triage", serialized)
        self.assertTrue(all(call[2]["max_turns"] == 7 for call in runner.calls))

    def test_free_form_output_fails_closed(self):
        provider = OpenAIEmployerWorkforceProvider(agents=self.agents, runner=FakeRunner(["automate it"]))
        with self.assertRaises(TypeError):
            provider.analyze_workflow({"request": employer_request().as_model_payload()})

    @unittest.skipUnless(importlib.util.find_spec("agents"), "openai-agents not installed")
    def test_current_sdk_agents_construct_without_api_call(self):
        agents = build_employer_workforce_agents(model="gpt-5.6-sol")
        self.assertEqual("Employer Workflow Agent", agents.workflow_agent.name)
        self.assertEqual("AI Opportunity Agent", agents.ai_opportunity_agent.name)
        self.assertEqual("Workforce Impact Agent", agents.workforce_impact_agent.name)
        self.assertEqual("Employer Capability Demand Agent", agents.capability_demand_agent.name)
        self.assertEqual("AI Adoption Risk Agent", agents.adoption_risk_agent.name)
        self.assertEqual("AI Adoption Pilot Agent", agents.pilot_design_agent.name)
        self.assertEqual("AI Adoption Measurement Agent", agents.measurement_agent.name)
        self.assertTrue(all(not agent.tools for agent in (
            agents.workflow_agent,
            agents.ai_opportunity_agent,
            agents.workforce_impact_agent,
            agents.capability_demand_agent,
            agents.adoption_risk_agent,
            agents.pilot_design_agent,
            agents.measurement_agent,
        )))


if __name__ == "__main__":
    unittest.main()
