from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.run_research import build_parser, main


class ResearchCliTests(unittest.TestCase):
    def test_status_command_parses_without_model_access(self):
        args = build_parser().parse_args(["status", "--execution-id", "research-1"])
        self.assertEqual("status", args.command)
        self.assertEqual("research-1", args.execution_id)

    def test_start_requires_launch_domain(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["start", "--question", "What capabilities are changing?"])

    def test_start_accepts_applied_ai_domain(self):
        args = build_parser().parse_args([
            "start",
            "--domain",
            "applied-ai-systems",
            "--question",
            "What capabilities are changing?",
        ])
        self.assertEqual("applied-ai-systems", args.domain)

    def test_missing_execution_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = main([
                "--db",
                str(Path(tmp) / "research.sqlite3"),
                "status",
                "--execution-id",
                "missing",
            ])
            self.assertEqual(2, code)

    def test_live_start_requires_api_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {}, clear=True):
                code = main([
                    "--db",
                    str(Path(tmp) / "research.sqlite3"),
                    "start",
                    "--domain",
                    "applied-ai-systems",
                    "--question",
                    "What capabilities are changing?",
                ])
            self.assertEqual(2, code)


if __name__ == "__main__":
    unittest.main()
