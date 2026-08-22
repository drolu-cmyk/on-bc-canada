from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from runtime.aws_runtime_observability import AWS_OBSERVABILITY_ENABLED_ENV
from runtime.control_plane import EventLedger
from runtime.graph_execution_store import GraphExecutionStore
from runtime.graph_kernel import GraphExecution
from runtime.run_runtime_assurance import build_parser, main


class RuntimeAssuranceCliTests(unittest.TestCase):
    def test_start_requires_api_key_with_local_telemetry(self):
        with tempfile.TemporaryDirectory() as directory:
            execution_db = Path(directory) / "graphs.sqlite3"
            research_db = Path(directory) / "missing-research.sqlite3"
            errors = io.StringIO()
            with patch.dict(os.environ, {}, clear=True), redirect_stderr(errors):
                code = main([
                    "--execution-db", str(execution_db),
                    "--research-db", str(research_db),
                    "--telemetry-source", "local",
                    "start",
                ])
        self.assertEqual(2, code)
        self.assertIn("OPENAI_API_KEY", errors.getvalue())

    def test_parser_defaults_to_aws_only_when_centralized_observability_is_enabled(self):
        with patch.dict(os.environ, {AWS_OBSERVABILITY_ENABLED_ENV: "1"}, clear=True):
            enabled = build_parser().parse_args(["start"])
        with patch.dict(os.environ, {}, clear=True):
            disabled = build_parser().parse_args(["start"])
        self.assertEqual("aws", enabled.telemetry_source)
        self.assertEqual("local", disabled.telemetry_source)

    def test_explicit_local_source_overrides_aws_environment_default(self):
        with patch.dict(os.environ, {AWS_OBSERVABILITY_ENABLED_ENV: "1"}, clear=True):
            args = build_parser().parse_args(["--telemetry-source", "local", "start"])
        self.assertEqual("local", args.telemetry_source)

    def test_status_is_model_free(self):
        with tempfile.TemporaryDirectory() as directory:
            execution_db = Path(directory) / "graphs.sqlite3"
            store = GraphExecutionStore(execution_db)
            execution = GraphExecution(
                execution_id="runtime-assurance-status-001",
                graph_id="runtime-assurance",
                graph_version="0.1.0",
                current_node="finalize_runtime_assurance",
                state={
                    "runtime_assurance_status": "completed",
                    "runtime_assurance_packet": {
                        "boundary": "assurance and recommendation only; no runtime mutation"
                    },
                },
                status="completed",
            )
            store.save_execution(execution, EventLedger())
            output = io.StringIO()
            with patch.dict(os.environ, {}, clear=True), redirect_stdout(output):
                code = main([
                    "--execution-db", str(execution_db),
                    "status",
                    "--execution-id", "runtime-assurance-status-001",
                ])
        self.assertEqual(0, code)
        payload = json.loads(output.getvalue())
        self.assertEqual("completed", payload["status"])
        self.assertEqual("runtime-assurance", payload["graph_id"])
        self.assertIn("no runtime mutation", payload["runtime_assurance_packet"]["boundary"])

    def test_parser_requires_command(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args([])


if __name__ == "__main__":
    unittest.main()
