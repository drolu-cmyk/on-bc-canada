from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.control_plane import EventLedger
from runtime.graph_kernel import GraphExecution
from runtime.research_store import ResearchStore
from runtime.run_work_intelligence import build_parser, main


class WorkIntelligenceCliTests(unittest.TestCase):
    def test_inspect_command_parses(self):
        args = build_parser().parse_args(
            ["inspect", "--entity-type", "capability", "--name", "Agent evaluation"]
        )
        self.assertEqual("inspect", args.command)
        self.assertEqual("capability", args.entity_type)

    def test_missing_entity_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = main(
                [
                    "--work-db",
                    str(Path(tmp) / "work.sqlite3"),
                    "inspect",
                    "--entity-type",
                    "capability",
                    "--name",
                    "Missing capability",
                ]
            )
            self.assertEqual(2, code)

    def test_completed_research_can_be_ingested_from_research_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            research_db = Path(tmp) / "research.sqlite3"
            work_db = Path(tmp) / "work.sqlite3"
            execution = GraphExecution(
                execution_id="research-cli-001",
                graph_id="canadian-work-research",
                graph_version="0.2.0",
                current_node="finalize_finding",
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
                            "evidence_source_ids": ["s1"],
                            "relevant_roles": ["Applied AI Developer"],
                            "relevance": "core",
                            "tool_neutral": True,
                        }
                    ],
                    "labour_market": {"signals": []},
                    "technology": {"signals": []},
                    "finding": {
                        "confidence": 0.75,
                        "curriculum_impact": {
                            "recommendation": "no_change",
                            "requires_human_review": False,
                        },
                    },
                },
                status="completed",
            )
            ResearchStore(research_db).save_execution(execution, EventLedger())
            code = main(
                [
                    "--work-db",
                    str(work_db),
                    "ingest",
                    "--research-db",
                    str(research_db),
                    "--execution-id",
                    "research-cli-001",
                    "--pathway-id",
                    "applied-ai-systems",
                    "--pathway-name",
                    "Applied AI Systems",
                ]
            )
            self.assertEqual(0, code)
            self.assertEqual(
                0,
                main(
                    [
                        "--work-db",
                        str(work_db),
                        "inspect",
                        "--entity-type",
                        "capability",
                        "--name",
                        "Agent evaluation",
                    ]
                ),
            )


if __name__ == "__main__":
    unittest.main()
