from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.run_learning_graph import build_parser, main


class LearningGraphCliTests(unittest.TestCase):
    def test_design_command_requires_capability(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args([
                "design",
                "--pathway-id",
                "applied-ai-systems",
                "--version",
                "0.1.0",
                "--title",
                "Applied AI Systems capability path",
            ])

    def test_live_design_requires_api_key_before_model_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {}, clear=True):
                code = main([
                    "--db",
                    str(root / "learning.sqlite3"),
                    "--capability-db",
                    str(root / "capabilities.sqlite3"),
                    "design",
                    "--pathway-id",
                    "applied-ai-systems",
                    "--version",
                    "0.1.0",
                    "--title",
                    "Applied AI Systems capability path",
                    "--capability",
                    "agent-evaluation",
                ])
            self.assertEqual(2, code)

    def test_missing_path_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code = main([
                "--db",
                str(root / "learning.sqlite3"),
                "--capability-db",
                str(root / "capabilities.sqlite3"),
                "inspect",
                "--pathway-id",
                "applied-ai-systems",
                "--version",
                "missing",
            ])
            self.assertEqual(2, code)


if __name__ == "__main__":
    unittest.main()
