from __future__ import annotations

import importlib.util
import unittest
from types import SimpleNamespace

from runtime.career_intelligence import CareerCapabilityEvidence, CareerModelContext, RoleEvidenceAlignment
from runtime.openai_career_mobility_provider import (
    CapabilityPositioning,
    CareerAction,
    CareerActionPlanOutput,
    CareerAgentSet,
    CareerProfileOutput,
    EvidenceCard,
    EvidencePackagingOutput,
    InterviewPracticeOutput,
    InterviewQuestion,
    OpenAICareerMobilityProvider,
    RoleAnalysis,
    RoleTransitionOutput,
    build_career_agents,
)


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


def context() -> CareerModelContext:
    return CareerModelContext(
        pathway_id="applied-ai-systems",
        learning_version="0.1.0",
        accepted_capabilities=(
            CareerCapabilityEvidence(
                capability_id="agent-evaluation",
                capability_name="Agent evaluation",
                target_level="evaluate",
                standard_id="agent-evaluation-proof",
                standard_description="Evaluate a bounded agent against defined tasks, failure conditions, and evidence criteria.",
            ),
        ),
        role_alignments=(
            RoleEvidenceAlignment(
                role_name="Applied AI Developer",
                required_capabilities=("Agent evaluation",),
                signaled_capabilities=(),
                matched_capabilities=("Agent evaluation",),
                missing_capabilities=(),
                evidence_alignment=1.0,
                relation_ids=("rel-1",),
                research_execution_ids=("research-1",),
            ),
        ),
    )


class OpenAICareerMobilityProviderTests(unittest.TestCase):
    def setUp(self):
        self.agents = CareerAgentSet(*[FakeAgent(name) for name in ("profile", "roles", "evidence", "interview", "actions")])

    def test_typed_workers_use_bounded_career_context(self):
        runner = FakeRunner(
            [
                CareerProfileOutput(
                    positioning_summary="Evidence-backed Applied AI capability.",
                    demonstrated_capabilities=[
                        CapabilityPositioning(
                            capability_id="agent-evaluation",
                            statement="Can explain and defend bounded agent evaluation decisions.",
                            evidence_boundary="Human-accepted capability evidence; raw artifact not supplied to agent.",
                        )
                    ],
                ),
                RoleTransitionOutput(
                    roles=[
                        RoleAnalysis(
                            role_name="Applied AI Developer",
                            evidence_based_strengths=["Agent evaluation"],
                            capability_gaps=[],
                            interpretation="Evidence overlap only, not hiring likelihood.",
                        )
                    ],
                    note="Learner-facing role interpretation.",
                ),
                EvidencePackagingOutput(
                    cards=[
                        EvidenceCard(
                            capability_id="agent-evaluation",
                            standard_id="agent-evaluation-proof",
                            label="Agent evaluation",
                            proof_prompt="Explain the decision, evidence, failure condition, and revision.",
                        )
                    ],
                    portfolio_structure=["Problem", "Decision", "Evidence"],
                    note="Learner supplies actual artifact claims.",
                ),
                InterviewPracticeOutput(
                    questions=[
                        InterviewQuestion(
                            role_name="Applied AI Developer",
                            question="How did you define and test an agent failure condition?",
                            capability_ids=["agent-evaluation"],
                            what_to_demonstrate="Reasoning and evidence boundaries.",
                        )
                    ],
                    practice_method="Answer from actual accepted evidence.",
                ),
                CareerActionPlanOutput(
                    actions=[
                        CareerAction(
                            action_type="interview_practice",
                            action="Practice one evidence-backed response.",
                            related_role_names=["Applied AI Developer"],
                            related_capability_ids=["agent-evaluation"],
                        )
                    ],
                    sequencing_note="Practice before employer research.",
                    boundary_note="No application or employer contact is executed.",
                ),
            ]
        )
        provider = OpenAICareerMobilityProvider(agents=self.agents, runner=runner)
        ctx = context()
        self.assertEqual("agent-evaluation", provider.profile(ctx)["demonstrated_capabilities"][0]["capability_id"])
        self.assertEqual("Applied AI Developer", provider.analyze_role_transitions(ctx)["roles"][0]["role_name"])
        self.assertEqual("agent-evaluation-proof", provider.package_evidence(ctx)["cards"][0]["standard_id"])
        self.assertEqual("Applied AI Developer", provider.prepare_interview_practice(ctx)["questions"][0]["role_name"])
        self.assertEqual("interview_practice", provider.plan_actions(ctx)["actions"][0]["action_type"])
        self.assertEqual(5, len(runner.calls))
        serialized = "\n".join(call[1] for call in runner.calls)
        self.assertIn("agent-evaluation", serialized)
        self.assertIn("Applied AI Developer", serialized)
        for prohibited in ("learner_ref", "cohort_id", "submission_id", "artifact_refs", "accepted_by"):
            self.assertNotIn(prohibited, serialized)
        self.assertTrue(all(call[2]["max_turns"] == 6 for call in runner.calls))

    def test_free_form_output_fails_closed(self):
        provider = OpenAICareerMobilityProvider(agents=self.agents, runner=FakeRunner(["career advice"] ))
        with self.assertRaises(TypeError):
            provider.profile(context())

    @unittest.skipUnless(importlib.util.find_spec("agents"), "openai-agents not installed")
    def test_current_sdk_agents_construct_without_api_call(self):
        agents = build_career_agents(model="gpt-5.6-sol")
        self.assertEqual("Career Profile Agent", agents.profile_agent.name)
        self.assertEqual("Role Transition Agent", agents.role_transition_agent.name)
        self.assertEqual("Career Evidence Packaging Agent", agents.evidence_packaging_agent.name)
        self.assertEqual("Interview Practice Agent", agents.interview_practice_agent.name)
        self.assertEqual("Career Action Agent", agents.action_plan_agent.name)
        self.assertTrue(all(not agent.tools for agent in (
            agents.profile_agent,
            agents.role_transition_agent,
            agents.evidence_packaging_agent,
            agents.interview_practice_agent,
            agents.action_plan_agent,
        )))


if __name__ == "__main__":
    unittest.main()
