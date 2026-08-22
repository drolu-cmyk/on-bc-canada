from __future__ import annotations

import unittest
from types import SimpleNamespace

from runtime.openai_implementation_provider import (
    ChangeSetOutput,
    FileChangeOutput,
    ImplementationAgentSet,
    ImplementationPlanOutput,
    OpenAIImplementationProvider,
    build_implementation_agents,
)


class FakeAgent:
    def __init__(self, name: str):
        self.name = name


class FakeRunner:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def run_sync(self, agent, input, **kwargs):
        self.calls.append((agent.name, input, kwargs))
        return SimpleNamespace(final_output=self.output)


def fake_agents() -> ImplementationAgentSet:
    return ImplementationAgentSet(*[FakeAgent(name) for name in ("planner", "generator", "code", "security", "quality")])


def request():
    return {
        "source_execution_id": "product-001",
        "release_record": {"status": "authorized_for_implementation", "packet": {}},
        "context_paths": ["runtime/example.py"],
        "allowed_verification_ids": ["runtime-tests", "public-copy"],
        "required_verification_ids": ["runtime-tests"],
    }


class OpenAIImplementationProviderTests(unittest.TestCase):
    def test_normalize_requires_authorized_release_and_verification_registry(self):
        provider = OpenAIImplementationProvider(agents=fake_agents(), runner=FakeRunner(None))
        normalized = provider.normalize(request())
        self.assertEqual("Canada", normalized["market"])
        broken = request()
        broken["release_record"] = {"status": "blocked"}
        with self.assertRaisesRegex(ValueError, "authorized product release"):
            provider.normalize(broken)
        broken = request()
        broken["required_verification_ids"] = ["not-allowed"]
        with self.assertRaisesRegex(ValueError, "operator-allowed"):
            provider.normalize(broken)

    def test_typed_plan_preserves_operator_verification_identifiers(self):
        output = ImplementationPlanOutput(
            objective="Update the learner surface.",
            change_slices=["update runtime"],
            files_to_change=["runtime/example.py"],
            verification_ids=["runtime-tests"],
            rollback_note="Restore the previous file hash.",
        )
        runner = FakeRunner(output)
        provider = OpenAIImplementationProvider(agents=fake_agents(), runner=runner)
        result = provider.plan_changes(request(), [{"path": "runtime/example.py", "sha256": "abc", "content": "x"}])
        self.assertEqual(["runtime-tests"], result["verification_ids"])
        self.assertIn("allowed_verification_ids", runner.calls[0][1])

    def test_typed_change_set_requires_update_hash(self):
        with self.assertRaises(ValueError):
            FileChangeOutput(
                operation="update",
                path="runtime/example.py",
                reason="Update example behavior.",
                content="VALUE = 2\n",
            )
        output = ChangeSetOutput(
            changes=[
                FileChangeOutput(
                    operation="update",
                    path="runtime/example.py",
                    reason="Update example behavior.",
                    content="VALUE = 2\n",
                    expected_sha256="a" * 64,
                )
            ],
            implementation_note="bounded change",
        )
        provider = OpenAIImplementationProvider(agents=fake_agents(), runner=FakeRunner(output))
        result = provider.generate_changes(request(), [], {"verification_ids": ["runtime-tests"]})
        self.assertEqual("a" * 64, result["changes"][0]["expected_sha256"])

    def test_untyped_output_fails_closed(self):
        provider = OpenAIImplementationProvider(agents=fake_agents(), runner=FakeRunner({"changes": []}))
        with self.assertRaisesRegex(TypeError, "untyped"):
            provider.generate_changes(request(), [], {"verification_ids": ["runtime-tests"]})

    def test_live_agent_contracts_construct_without_tools_or_api_call(self):
        agents = build_implementation_agents(model="gpt-5.6-sol")
        workers = (agents.planner, agents.generator, agents.code_review, agents.security_review, agents.quality_review)
        self.assertEqual(5, len(workers))
        self.assertTrue(all(worker.output_type is not None for worker in workers))
        self.assertTrue(all(worker.tools == [] for worker in workers))


if __name__ == "__main__":
    unittest.main()
