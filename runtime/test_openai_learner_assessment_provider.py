from __future__ import annotations

import unittest
from types import SimpleNamespace

from runtime.openai_learner_assessment_provider import (
    EvidenceAssessmentOutput,
    EvidenceFinding,
    LearnerAssessmentAgentSet,
    OpenAILearnerAssessmentProvider,
    SubmissionReviewOutput,
    build_learner_assessment_agents,
)
from runtime.test_learner_assessment_graph import request


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


def fake_agents() -> LearnerAssessmentAgentSet:
    return LearnerAssessmentAgentSet(
        review=FakeAgent("review"),
        assessment=FakeAgent("assessment"),
        challenge=FakeAgent("challenge"),
    )


class OpenAILearnerAssessmentProviderTests(unittest.TestCase):
    def test_normalize_requires_standard_coverage(self):
        provider = OpenAILearnerAssessmentProvider(agents=fake_agents(), runner=FakeRunner(None))
        normalized = provider.normalize(request())
        self.assertEqual("submission-assessment-001", normalized["submission"]["submission_id"])
        broken = request()
        broken["standards"] = []
        with self.assertRaisesRegex(ValueError, "evidence standards"):
            provider.normalize(broken)

    def test_typed_review_output_is_returned_without_record_mutation(self):
        output = SubmissionReviewOutput(
            status="ready",
            strengths=["failure cases are explicit"],
            feedback=["explain why the cases are representative"],
        )
        runner = FakeRunner(output)
        provider = OpenAILearnerAssessmentProvider(agents=fake_agents(), runner=runner)
        result = provider.review_submission(request())
        self.assertEqual("ready", result["status"])
        self.assertIn("evidence_material", runner.calls[0][1])

    def test_typed_assessment_preserves_capability_and_standard_ids(self):
        output = EvidenceAssessmentOutput(
            findings=[
                EvidenceFinding(
                    capability_id="agent-evaluation",
                    standard_id="agent-evaluation-proof",
                    verdict="meets",
                    rationale="Evidence demonstrates bounded evaluation judgment.",
                    evidence_refs=["artifact://evaluation-report"],
                    confidence=0.82,
                )
            ],
            overall_note="Evidence is ready for challenge review.",
        )
        provider = OpenAILearnerAssessmentProvider(agents=fake_agents(), runner=FakeRunner(output))
        result = provider.assess_evidence(request(), {"status": "ready"})
        self.assertEqual("agent-evaluation", result["findings"][0]["capability_id"])
        self.assertEqual("agent-evaluation-proof", result["findings"][0]["standard_id"])

    def test_untyped_output_fails_closed(self):
        provider = OpenAILearnerAssessmentProvider(agents=fake_agents(), runner=FakeRunner({"status": "ready"}))
        with self.assertRaisesRegex(TypeError, "untyped"):
            provider.review_submission(request())

    def test_live_agent_contracts_construct_without_tools_or_api_call(self):
        agents = build_learner_assessment_agents(model="gpt-5.6-sol")
        workers = (agents.review, agents.assessment, agents.challenge)
        self.assertEqual(3, len(workers))
        self.assertTrue(all(worker.output_type is not None for worker in workers))
        self.assertTrue(all(worker.tools == [] for worker in workers))


if __name__ == "__main__":
    unittest.main()
