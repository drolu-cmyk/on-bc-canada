from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.run_career_mobility import build_parser, main


class CareerMobilityCliTests(unittest.TestCase):
    def test_status_command_parses_without_model_access(self):
        args = build_parser().parse_args(["status", "--execution-id", "career-001"])
        self.assertEqual("status", args.command)
        self.assertEqual("career-001", args.execution_id)

    def test_start_requires_api_key_before_model_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {}, clear=True):
                code = main(
                    [
                        "--learner-db",
                        str(root / "learner.sqlite3"),
                        "--capability-db",
                        str(root / "capabilities.sqlite3"),
                        "--work-db",
                        str(root / "work.sqlite3"),
                        "--execution-db",
                        str(root / "graph.sqlite3"),
                        "start",
                        "--instance-id",
                        "learner-career-001",
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
                    "--work-db",
                    str(root / "work.sqlite3"),
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
