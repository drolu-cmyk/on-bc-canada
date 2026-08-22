from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.run_business_operations import build_parser, main


class BusinessOperationsCliTests(unittest.TestCase):
    def test_start_requires_explicit_workstream_action_and_problem(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["start", "--workstream", "growth"])

    def test_live_start_requires_api_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {}, clear=True):
                code = main([
                    "--db",
                    str(Path(tmp) / "business.sqlite3"),
                    "start",
                    "--workstream",
                    "operations",
                    "--action-class",
                    "analysis",
                    "--problem",
                    "Review registration flow.",
                ])
            self.assertEqual(2, code)

    def test_missing_execution_returns_error_without_model_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = main([
                "--db",
                str(Path(tmp) / "business.sqlite3"),
                "status",
                "--execution-id",
                "missing",
            ])
            self.assertEqual(2, code)

    def test_finance_commitment_command_parses_a4_action_class(self):
        args = build_parser().parse_args([
            "start",
            "--workstream",
            "finance",
            "--action-class",
            "financial_commitment",
            "--problem",
            "Evaluate a model-cost ceiling.",
            "--metric",
            "monthly ceiling CAD 500",
        ])
        self.assertEqual("finance", args.workstream)
        self.assertEqual("financial_commitment", args.action_class)
        self.assertEqual(["monthly ceiling CAD 500"], args.metric)


if __name__ == "__main__":
    unittest.main()
