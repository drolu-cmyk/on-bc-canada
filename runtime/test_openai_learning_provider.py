from __future__ import annotations

import unittest
from types import SimpleNamespace

from runtime.openai_learning_provider import (
    EvidenceRequirementOutput,
    LearningDesignContext,
    LearningPathOutput,
    LearningUnitOutput,
    OpenAILearningDesignProvider,
    build_learning_design_agent,
)


class FakeAgent:
    name = "Learning Graph Design Agent"
    tools = []
    output_type = object


class FakeRunner:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def run_sync(self, agent, input, **kwargs):
        self.calls.append((agent, input, kwargs))
        return SimpleNamespace(final_output=self.output)


def context() -> LearningDesignContext:
    return LearningDesignContext(
        pathway_id="applied-ai-systems",
        version="0.1.0",
        title="Applied AI Systems capability path",
        active_capabilities=(
            {
                "capability_id": "agent-evaluation",
                "name": "Agent evaluation",
                "description": "Evaluate bounded agent behaviour against explicit tasks and failure conditions.",
                "target_level": "evaluate",
                "evidence_standards": [{"standard_id": "agent-evaluation-proof"}],
            },
        ),
        existing_modules=(
            {
                "module_id": "AAI-101",
                "title": "Applied AI Foundations: Problems, Data, and Evaluation",
            },
        ),
    )


def valid_output() -> LearningPathOutput:
    return LearningPathOutput(
        pathway_id="applied-ai-systems",
        version="0.1.0",
        title="Applied AI Systems capability path",
        target_capability_ids=["agent-evaluation"],
        units=[
            LearningUnitOutput(
                unit_id="evaluation-sprint",
                kind="sprint",
                title="Evaluation foundations",
                purpose="Define agent tasks, failure conditions, evidence requirements, and human decision boundaries.",
                develops_capability_ids=["agent-evaluation"],
                source_module_ids=["AAI-101"],
            ),
            LearningUnitOutput(
                unit_id="evaluation-mission",
                kind="mission",
                title="Agent evaluation mission",
                purpose="Evaluate a bounded agent, defend the result, and respond to a changed technical scenario.",
                develops_capability_ids=["agent-evaluation"],
                prerequisite_unit_ids=["evaluation-sprint"],
                evidence_requirements=[
                    EvidenceRequirementOutput(
                        capability_id="agent-evaluation",
                        standard_id="agent-evaluation-proof",
                    )
                ],
            ),
        ],
    )


class OpenAILearningDesignProviderTests(unittest.TestCase):
    def test_typed_agent_output_becomes_learning_path_definition(self):
        runner = FakeRunner(valid_output())
        provider = OpenAILearningDesignProvider(agent=FakeAgent(), runner=runner)
        definition = provider.propose(context())
        self.assertEqual("applied-ai-systems", definition.pathway_id)
        self.assertEqual(("agent-evaluation",), definition.target_capability_ids)
        self.assertEqual("mission", definition.units[1].kind)
        self.assertIn('"capability_id": "agent-evaluation"', runner.calls[0][1])
        self.assertIn('"module_id": "AAI-101"', runner.calls[0][1])

    def test_unknown_target_capability_fails_closed(self):
        output = valid_output().model_copy(update={"target_capability_ids": ["invented-capability"]})
        provider = OpenAILearningDesignProvider(agent=FakeAgent(), runner=FakeRunner(output))
        with self.assertRaisesRegex(ValueError, "unknown target capability"):
            provider.propose(context())

    def test_untyped_agent_output_fails_closed(self):
        provider = OpenAILearningDesignProvider(agent=FakeAgent(), runner=FakeRunner({"units": []}))
        with self.assertRaisesRegex(TypeError, "untyped"):
            provider.propose(context())

    def test_live_sdk_agent_contract_constructs_without_api_call(self):
        agent = build_learning_design_agent(model="gpt-5.6-sol")
        self.assertEqual("Learning Graph Design Agent", agent.name)
        self.assertIsNotNone(agent.output_type)
        self.assertEqual([], agent.tools)


if __name__ == "__main__":
    unittest.main()
