from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime.graph_kernel import GraphExecution
from runtime.run_capability_graph import build_parser, main
from runtime.work_intelligence import WorkIntelligenceStore


def completed_execution() -> GraphExecution:
    return GraphExecution(
        execution_id="research-cli-capability-001",
        graph_id="canadian-work-research",
        graph_version="0.2.0",
        current_node="finalize_finding",
        status="completed",
        history=[
            {"node_id": "curriculum_review", "actor_id": "accountable-human", "approved": True},
            {"node_id": "finalize_finding"},
        ],
        state={
            "research_status": "complete",
            "sources": [
                {
                    "source_id": "s1",
                    "publisher": "Canada Job Bank",
                    "title": "Applied AI role",
                    "url": "https://example.invalid/s1",
                }
            ],
            "capabilities": [
                {
                    "capability": "Agent evaluation",
                    "description": "Evaluate agent behaviour against tasks and failure conditions.",
                    "evidence_source_ids": ["s1"],
                    "relevant_roles": ["Applied AI Developer"],
                    "relevance": "core",
                    "tool_neutral": True,
                }
            ],
            "labour_market": {"signals": []},
            "technology": {"signals": []},
            "finding": {
                "question": "What capabilities matter?",
                "domain_id": "applied-ai-systems",
                "pathway_name": "Applied AI Systems",
                "confidence": 0.76,
                "curriculum_impact": {"recommendation": "increase", "requires_human_review": True},
            },
        },
    )


class CapabilityGraphCliTests(unittest.TestCase):
    def test_draft_command_parses_reviewed_definition_fields(self):
        args = build_parser().parse_args([
            "draft-from-work",
            "--pathway-id",
            "applied-ai-systems",
            "--pathway-name",
            "Applied AI Systems",
            "--capability-id",
            "agent-evaluation",
            "--capability-name",
            "Agent evaluation",
            "--description",
            "Evaluate a bounded agent against explicit tasks and failure criteria.",
            "--target-level",
            "evaluate",
            "--evidence-standard",
            json.dumps({
                "standard_id": "agent-evaluation-proof",
                "description": "Produce an evaluation report and defend the result against a changed scenario.",
                "artifact_types": ["evaluation_report", "oral_defense"],
                "minimum_level": "evaluate",
                "requires_defense": True,
            }),
        ])
        self.assertEqual("draft-from-work", args.command)
        self.assertEqual("evaluate", args.target_level)
        self.assertEqual("agent-evaluation", args.capability_id)

    def test_missing_capability_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = main([
                "--db",
                str(Path(tmp) / "capabilities.sqlite3"),
                "inspect",
                "--capability-id",
                "missing",
            ])
            self.assertEqual(2, code)

    def test_draft_and_activate_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work_db = root / "work.sqlite3"
            capability_db = root / "capabilities.sqlite3"
            work = WorkIntelligenceStore(work_db)
            work.ingest_research_execution(
                completed_execution(),
                pathway_id="applied-ai-systems",
                pathway_name="Applied AI Systems",
            )
            standard = json.dumps({
                "standard_id": "agent-evaluation-proof",
                "description": "Produce an evaluation report and defend the result against a changed scenario.",
                "artifact_types": ["evaluation_report", "oral_defense"],
                "minimum_level": "evaluate",
                "requires_defense": True,
                "requires_changed_scenario": True,
            })
            draft_code = main([
                "--db",
                str(capability_db),
                "--work-db",
                str(work_db),
                "draft-from-work",
                "--pathway-id",
                "applied-ai-systems",
                "--pathway-name",
                "Applied AI Systems",
                "--capability-id",
                "agent-evaluation",
                "--capability-name",
                "Agent evaluation",
                "--description",
                "Evaluate a bounded agent against explicit tasks, evidence criteria, and failure conditions.",
                "--target-level",
                "evaluate",
                "--evidence-standard",
                standard,
            ])
            self.assertEqual(0, draft_code)

            activate_code = main([
                "--db",
                str(capability_db),
                "activate",
                "--capability-id",
                "agent-evaluation",
                "--approver-id",
                "curriculum-accountable-person",
                "--note",
                "Reviewed evidence and verification standard.",
            ])
            self.assertEqual(0, activate_code)

            pathway_code = main([
                "--db",
                str(capability_db),
                "pathway",
                "--pathway-id",
                "applied-ai-systems",
                "--status",
                "active",
            ])
            self.assertEqual(0, pathway_code)


if __name__ == "__main__":
    unittest.main()
