from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.run_learner_execution import build_parser, main


class LearnerExecutionCliTests(unittest.TestCase):
    def test_status_command_parses_without_model_access(self):
        args = build_parser().parse_args(["status", "--execution-id", "assessment-001"])
        self.assertEqual("status", args.command)
        self.assertEqual("assessment-001", args.execution_id)

    def test_review_requires_explicit_accept_or_revise(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(
                [
                    "review",
                    "--execution-id",
                    "assessment-001",
                    "--reviewer-id",
                    "reviewer-1",
                    "--note",
                    "Reviewed evidence.",
                ]
            )

    def test_live_start_requires_api_key_before_model_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {}, clear=True):
                code = main(
                    [
                        "--learner-db",
                        str(root / "learner.sqlite3"),
                        "--capability-db",
                        str(root / "capabilities.sqlite3"),
                        "--execution-db",
                        str(root / "graph.sqlite3"),
                        "start",
                        "--submission-id",
                        "submission-001",
                    ]
                )
            self.assertEqual(2, code)

    def test_missing_status_execution_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code = main(
                [
                    "--learner-db",
                    str(root / "learner.sqlite3"),
                    "--capability-db",
                    str(root / "capabilities.sqlite3"),
                    "--execution-db",
                    str(root / "graph.sqlite3"),
                    "status",
                    "--execution-id",
                    "missing",
                ]
            )
            self.assertEqual(2, code)


if __name__ == "__main__":
    unittest.main()
