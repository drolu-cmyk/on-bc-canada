from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.run_learner_progress import build_parser, main


class LearnerProgressCliTests(unittest.TestCase):
    def test_assignment_command_requires_pseudonymous_reference_fields(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["assign", "--instance-id", "learner-path-001"])

    def test_missing_instance_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = main([
                "--db",
                str(Path(tmp) / "learner.sqlite3"),
                "instance",
                "--instance-id",
                "missing-instance",
            ])
            self.assertEqual(2, code)

    def test_submission_parser_keeps_artifact_references_separate_from_types(self):
        args = build_parser().parse_args([
            "submit-mission",
            "--submission-id",
            "submission-001",
            "--instance-id",
            "learner-path-001",
            "--unit-id",
            "agent-mission",
            "--artifact-ref",
            "artifact://report",
            "--artifact-type",
            "evaluation_report",
            "--revision-ref",
            "artifact://revision",
        ])
        self.assertEqual(["artifact://report"], args.artifact_ref)
        self.assertEqual(["evaluation_report"], args.artifact_type)
        self.assertEqual("artifact://revision", args.revision_ref)


if __name__ == "__main__":
    unittest.main()
