from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.run_learner_assessment import _read_evidence_file, build_parser, main


class LearnerAssessmentCliTests(unittest.TestCase):
    def test_start_requires_submission_id(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["start"])

    def test_live_start_requires_api_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {}, clear=True):
                code = main([
                    "--db",
                    str(root / "assessment.sqlite3"),
                    "--learner-db",
                    str(root / "learner.sqlite3"),
                    "--capability-db",
                    str(root / "capabilities.sqlite3"),
                    "start",
                    "--submission-id",
                    "submission-001",
                ])
            self.assertEqual(2, code)

    def test_status_of_missing_execution_returns_error_without_model_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code = main([
                "--db",
                str(root / "assessment.sqlite3"),
                "--learner-db",
                str(root / "learner.sqlite3"),
                "--capability-db",
                str(root / "capabilities.sqlite3"),
                "status",
                "--execution-id",
                "missing",
            ])
            self.assertEqual(2, code)

    def test_evidence_file_must_be_json_object_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.json"
            path.write_text(json.dumps([{"evidence_ref": "artifact://report", "summary": "bounded evidence"}]), encoding="utf-8")
            self.assertEqual("artifact://report", _read_evidence_file(str(path))[0]["evidence_ref"])
            path.write_text(json.dumps({"evidence_ref": "artifact://report"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON list"):
                _read_evidence_file(str(path))


if __name__ == "__main__":
    unittest.main()
