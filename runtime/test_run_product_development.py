from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.run_product_development import build_parser, main


class ProductDevelopmentCliTests(unittest.TestCase):
    def test_start_requires_problem(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["start"])

    def test_live_start_requires_api_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {}, clear=True):
                code = main([
                    "--db",
                    str(Path(tmp) / "product.sqlite3"),
                    "start",
                    "--problem",
                    "Improve learner home.",
                ])
            self.assertEqual(2, code)

    def test_missing_execution_returns_error_without_model_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = main([
                "--db",
                str(Path(tmp) / "product.sqlite3"),
                "status",
                "--execution-id",
                "missing",
            ])
            self.assertEqual(2, code)


if __name__ == "__main__":
    unittest.main()
