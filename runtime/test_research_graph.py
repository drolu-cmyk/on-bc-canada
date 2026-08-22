import unittest

from runtime.graph_kernel import GraphKernel
from runtime.research_graph import ResearchGraph


class FakeProvider:
    def normalize(self, question):
        return {
            "question": question.strip(),
            "geography": "Canada",
            "scope": "technical work",
            "domain": {
                "domain_id": "applied-ai-systems",
                "pathway_name": "Applied AI Systems",
            },
        }

    def discover(self, research):
        return [
            {"source_id": "job-1", "publisher": "Example Employer"},
            {"source_id": "job-2", "publisher": "Example Employer 2"},
        ]

    def collect(self, research, sources):
        return [
            {"source_id": "job-1", "claim": "role requires agent evaluation", "geography": "Ontario"},
            {"source_id": "job-2", "claim": "role requires tool permission design", "geography": "Canada"},
        ]

    def analyze_labour_market(self, research, evidence):
        return {
            "signals": [
                {
                    "role": "Applied AI Developer",
                    "capability_hint": "agent evaluation",
                    "geography": "Canada",
                    "signal": "repeated",
                    "source_ids": ["job-1", "job-2"],
                    "note": "deterministic fixture",
                }
            ],
            "concentration_risks": [],
        }

    def analyze_technology(self, research, evidence):
        return {
            "signals": [
                {
                    "technology": "agent evaluation harness",
                    "relationship": "supports reliable autonomous workflows",
                    "maturity": "growing",
                    "source_ids": ["job-1"],
                    "note": "deterministic fixture",
                }
            ],
            "substitution_notes": ["learning outcome stays tool-neutral"],
        }

    def extract_capabilities(self, research, evidence, labour_market, technology):
        return [
            {"capability": "agent evaluation", "support": 1},
            {"capability": "tool permission design", "support": 1},
        ]

    def challenge(self, research, capabilities, evidence):
        return {
            "status": "challenged",
            "contradictions": [],
            "limitations": ["small deterministic fixture"],
        }

    def score(self, research, evidence, challenge):
        return {"confidence": 0.82, "source_diversity": 2, "freshness": "current"}

    def assess_curriculum_impact(self, research, capabilities, score):
        return {
            "recommendation": "increase",
            "requires_human_review": True,
            "reason": "capability is material to the pathway",
        }


class ResearchGraphTests(unittest.TestCase):
    def test_research_change_stops_for_human_review_then_finalizes(self):
        kernel = GraphKernel()
        research = ResearchGraph(kernel=kernel, provider=FakeProvider())
        research.register()
        definition, execution = research.start(
            execution_id="research-1",
            question="What capabilities are Canadian employers asking Applied AI practitioners to demonstrate?",
        )
        self.assertEqual("waiting_approval", execution.status)
        self.assertEqual("curriculum_review", execution.current_node)
        self.assertEqual(0.82, execution.state["evidence_score"]["confidence"])
        self.assertEqual("repeated", execution.state["labour_market"]["signals"][0]["signal"])
        self.assertEqual("growing", execution.state["technology"]["signals"][0]["maturity"])
        self.assertEqual("applied-ai-systems", execution.state["research"]["domain"]["domain_id"])
        self.assertNotIn("finding", execution.state)

        execution = kernel.decide(
            definition,
            execution,
            approved=True,
            approver_id="curriculum-accountable-person",
            note="Approved for pathway review, not automatic publication.",
        )
        self.assertEqual("completed", execution.status)
        self.assertEqual("complete", execution.state["research_status"])
        self.assertEqual(2, execution.state["finding"]["source_count"])
        self.assertEqual("applied-ai-systems", execution.state["finding"]["domain_id"])
        self.assertEqual("Applied AI Systems", execution.state["finding"]["pathway_name"])
        self.assertEqual("increase", execution.state["finding"]["curriculum_impact"]["recommendation"])


if __name__ == "__main__":
    unittest.main()
