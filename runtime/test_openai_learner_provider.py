from __future__ import annotations

import importlib.util
import unittest
from types import SimpleNamespace

from runtime.openai_learner_provider import (
    CoachingOutput,
    LearnerAgentSet,
    LearnerModelContext,
    OpenAILearnerSupportProvider,
    ProgressOutput,
    ReviewChecklistItem,
    ReviewChecklistOutput,
    build_learner_agents,
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


def context() -> LearnerModelContext:
    return LearnerModelContext(
        pathway_id="applied-ai-systems",
        learning_version="0.1.0",
        unit_id="supplier-agent-mission",
        unit_kind="mission",
        unit_title="Supplier review agent mission",
        unit_purpose="Evaluate and constrain a supplier-review agent against reviewed evidence standards.",
        attempt_number=1,
        unit_status_counts={"completed": 2, "in_progress": 1},
        artifact_types=("evaluation_report",),
        readiness_complete=True,
        readiness_requirements=(
            {
                "capability_id": "agent-evaluation",
                "standard_id": "agent-evaluation-proof",
                "standard_description": "Evaluate a bounded agent against explicit tasks and failure conditions.",
                "minimum_level": "evaluate",
                "accepted_artifact_types": ["evaluation_report"],
                "artifact_type_present": True,
                "revision_required": True,
                "revision_present": True,
                "defense_required": True,
                "defense_present": True,
                "changed_scenario_required": True,
                "changed_scenario_present": True,
            },
        ),
    )


class OpenAILearnerSupportProviderTests(unittest.TestCase):
    def setUp(self):
        self.agents = LearnerAgentSet(
            FakeAgent("coach"),
            FakeAgent("progress"),
            FakeAgent("review"),
        )

    def test_typed_workers_use_only_deidentified_context(self):
        runner = FakeRunner(
            [
                CoachingOutput(
                    focus="Evidence preparation",
                    next_actions=["Check each evidence requirement."],
                    note="No grading performed.",
                ),
                ProgressOutput(
                    status="ready_for_review",
                    rationale="Metadata requirements are present.",
                    recommended_next_step="Human evidence review",
                ),
                ReviewChecklistOutput(
                    summary="Human review checklist",
                    checklist=[
                        ReviewChecklistItem(
                            capability_id="agent-evaluation",
                            standard_id="agent-evaluation-proof",
                            review_question="Does the raw evidence demonstrate the required evaluation work?",
                        )
                    ],
                ),
            ]
        )
        provider = OpenAILearnerSupportProvider(agents=self.agents, runner=runner)
        ctx = context()
        coaching = provider.coach(ctx)
        progress = provider.analyze_progress(ctx)
        checklist = provider.prepare_human_review(ctx)

        self.assertEqual("Evidence preparation", coaching["focus"])
        self.assertEqual("ready_for_review", progress["status"])
        self.assertEqual("agent-evaluation-proof", checklist["checklist"][0]["standard_id"])
        self.assertEqual(3, len(runner.calls))
        serialized = "\n".join(call[1] for call in runner.calls)
        self.assertIn("applied-ai-systems", serialized)
        self.assertIn("evaluation_report", serialized)
        for prohibited in ("learner_ref", "cohort_id", "artifact_refs", "submission_id", "attendance", "support"):
            self.assertNotIn(prohibited, serialized)

    def test_free_form_output_fails_closed(self):
        runner = FakeRunner(["looks good"])
        provider = OpenAILearnerSupportProvider(agents=self.agents, runner=runner)
        with self.assertRaises(TypeError):
            provider.coach(context())

    @unittest.skipUnless(importlib.util.find_spec("agents"), "openai-agents not installed")
    def test_current_sdk_agents_construct_without_api_call(self):
        agents = build_learner_agents(model="gpt-5.6-sol")
        self.assertEqual("Learning Coach Agent", agents.coach_agent.name)
        self.assertEqual("Learner Progress Agent", agents.progress_agent.name)
        self.assertEqual("Human Review Preparation Agent", agents.review_preparation_agent.name)
        self.assertFalse(agents.coach_agent.tools)
        self.assertFalse(agents.progress_agent.tools)
        self.assertFalse(agents.review_preparation_agent.tools)


if __name__ == "__main__":
    unittest.main()
