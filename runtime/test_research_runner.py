from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.research_runner import execution_summary, resume_research, start_research
from runtime.research_store import ResearchStore


class FakeProvider:
    def normalize(self, question):
        return {"question": question.strip(), "geography": "Canada", "scope": "technical work"}

    def discover(self, research):
        return [
            {"source_id": "s1", "publisher": "Employer 1"},
            {"source_id": "s2", "publisher": "Employer 2"},
        ]

    def collect(self, research, sources):
        return [
            {"source_id": "s1", "publisher": "Employer 1", "claim": "agent evaluation"},
            {"source_id": "s2", "publisher": "Employer 2", "claim": "permission design"},
        ]

    def analyze_labour_market(self, research, evidence):
        return {"signals": [{"role": "Applied AI Developer", "signal": "repeated"}]}

    def analyze_technology(self, research, evidence):
        return {"signals": [{"technology": "agent harness", "maturity": "growing"}]}

    def extract_capabilities(self, research, evidence, labour_market, technology):
        return [{"capability": "agent evaluation"}]

    def challenge(self, research, capabilities, evidence):
        return {"status": "challenged", "contradictions": [], "limitations": []}

    def score(self, research, evidence, challenge):
        return {"confidence": 0.78, "source_diversity": 2}

    def assess_curriculum_impact(self, research, capabilities, score):
        return {
            "recommendation": "increase",
            "requires_human_review": True,
            "reason": "validated gap",
        }


class ResearchRunnerTests(unittest.TestCase):
    def test_process_restart_can_resume_from_human_gate_without_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ResearchStore(Path(tmp) / "research.sqlite3")
            provider = FakeProvider()
            started = start_research(
                provider=provider,
                store=store,
                execution_id="research-001",
                question="What capabilities are changing?",
            )
            self.assertEqual("waiting_approval", started.status)
            events_before = len(store.load_execution("research-001")[1].events)

            resumed = resume_research(
                provider=provider,
                store=store,
                execution_id="research-001",
                approved=True,
                approver_id="accountable-human",
                note="Approved for programme review.",
            )
            self.assertEqual("completed", resumed.status)
            self.assertEqual("complete", resumed.state["research_status"])
            self.assertEqual(0.78, store.get_finding("research-001")["confidence"])
            events_after = len(store.load_execution("research-001")[1].events)
            self.assertGreater(events_after, events_before)
            self.assertEqual("completed", execution_summary(resumed)["status"])

    def test_denial_is_persisted_as_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ResearchStore(Path(tmp) / "research.sqlite3")
            provider = FakeProvider()
            start_research(
                provider=provider,
                store=store,
                execution_id="research-002",
                question="What capabilities are changing?",
            )
            denied = resume_research(
                provider=provider,
                store=store,
                execution_id="research-002",
                approved=False,
                approver_id="accountable-human",
                note="Evidence is not strong enough.",
            )
            self.assertEqual("failed", denied.status)
            restored, _ = store.load_execution("research-002")
            self.assertEqual("failed", restored.status)
            self.assertIn("approval denied", restored.failure)


if __name__ == "__main__":
    unittest.main()
