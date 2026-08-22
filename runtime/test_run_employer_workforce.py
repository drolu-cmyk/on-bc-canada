from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.run_employer_workforce import _load_request, build_parser, main


class EmployerWorkforceCliTests(unittest.TestCase):
    def test_status_command_parses_without_model_access(self):
        args = build_parser().parse_args(["status", "--execution-id", "employer-001"])
        self.assertEqual("status", args.command)
        self.assertEqual("employer-001", args.execution_id)

    def test_start_requires_api_key_before_model_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request_path = root / "request.json"
            request_path.write_text("{}", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                code = main(
                    [
                        "--execution-db",
                        str(root / "graph.sqlite3"),
                        "start",
                        "--request-file",
                        str(request_path),
                    ]
                )
            self.assertEqual(2, code)

    def test_request_file_builds_organization_level_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "request.json"
            path.write_text(
                json.dumps(
                    {
                        "organization_ref": "org-cli-001",
                        "sector": "Services",
                        "workflow_name": "Request review",
                        "workflow_purpose": "Review incoming organization requests and route them to an internal service queue.",
                        "tasks": [
                            {
                                "task_id": "review-request",
                                "description": "Review each organization request and select the appropriate internal service category.",
                                "role_labels": ["Operations Analyst"],
                                "current_tools": ["Case system"],
                                "pain_points": ["Repeated classification"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            request = _load_request(str(path))
            self.assertEqual("org-cli-001", request.organization_ref)
            self.assertEqual("review-request", request.tasks[0].task_id)
            self.assertNotIn("organization_ref", request.as_model_payload())

    def test_missing_status_execution_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = main(
                [
                    "--execution-db",
                    str(Path(tmp) / "graph.sqlite3"),
                    "status",
                    "--execution-id",
                    "missing",
                ]
            )
            self.assertEqual(2, code)


if __name__ == "__main__":
    unittest.main()
