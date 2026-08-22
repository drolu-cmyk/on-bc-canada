from __future__ import annotations

import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from runtime.control_plane import EventLedger
from runtime.graph_execution_store import GraphExecutionStore
from runtime.graph_kernel import GraphExecution
from runtime.run_outcomes_intelligence import build_parser, main


class OutcomesIntelligenceCliTests(unittest.TestCase):
    @staticmethod
    def _empty_learner_store(path: Path) -> None:
        with sqlite3.connect(path) as connection:
            connection.executescript(
                """
                CREATE TABLE learner_path_instances (
                    instance_id TEXT PRIMARY KEY,
                    pathway_id TEXT NOT NULL,
                    learning_version TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE learner_unit_progress (instance_id TEXT, kind TEXT, status TEXT);
                CREATE TABLE learner_submissions (instance_id TEXT, attempt_number INTEGER, status TEXT);
                CREATE TABLE learner_capability_evidence (instance_id TEXT, capability_id TEXT);
                """
            )

    def test_start_requires_api_key_after_local_privacy_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            learner_db = Path(directory) / "learners.sqlite3"
            execution_db = Path(directory) / "graphs.sqlite3"
            self._empty_learner_store(learner_db)
            errors = io.StringIO()
            with patch.dict(os.environ, {}, clear=True), redirect_stderr(errors):
                code = main([
                    "--learner-db", str(learner_db),
                    "--execution-db", str(execution_db),
                    "start",
                ])
        self.assertEqual(2, code)
        self.assertIn("OPENAI_API_KEY", errors.getvalue())

    def test_status_is_model_free(self):
        with tempfile.TemporaryDirectory() as directory:
            execution_db = Path(directory) / "graphs.sqlite3"
            store = GraphExecutionStore(execution_db)
            execution = GraphExecution(
                execution_id="outcomes-status-001",
                graph_id="outcomes-intelligence",
                graph_version="0.1.0",
                current_node="finalize_outcomes",
                state={
                    "outcomes_status": "completed",
                    "outcomes_packet": {"boundary": "aggregate programme intelligence only"},
                },
                status="completed",
            )
            store.save_execution(execution, EventLedger())
            output = io.StringIO()
            with patch.dict(os.environ, {}, clear=True), redirect_stdout(output):
                code = main([
                    "--execution-db", str(execution_db),
                    "status",
                    "--execution-id", "outcomes-status-001",
                ])
        self.assertEqual(0, code)
        payload = json.loads(output.getvalue())
        self.assertEqual("completed", payload["status"])
        self.assertEqual("outcomes-intelligence", payload["graph_id"])
        self.assertEqual("aggregate programme intelligence only", payload["outcomes_packet"]["boundary"])

    def test_parser_requires_command(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args([])


if __name__ == "__main__":
    unittest.main()
