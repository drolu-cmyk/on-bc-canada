from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.run_implementation_delivery import VERIFICATION_REGISTRY, build_parser, main


class ImplementationDeliveryCliTests(unittest.TestCase):
    def test_workspace_and_allow_root_are_required(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["status", "--execution-id", "implementation-001"])

    def test_start_requires_api_key_before_product_lookup_or_model_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "runtime").mkdir()
            with patch.dict(os.environ, {}, clear=True):
                code = main([
                    "--db",
                    str(root / "implementation.sqlite3"),
                    "--workspace-root",
                    str(root),
                    "--allow-root",
                    "runtime",
                    "start",
                    "--product-db",
                    str(root / "product.sqlite3"),
                    "--product-execution-id",
                    "product-001",
                    "--context-path",
                    "runtime/example.py",
                    "--required-verification",
                    "runtime-tests",
                ])
            self.assertEqual(2, code)

    def test_verification_choices_are_fixed_registry_ids(self):
        args = build_parser().parse_args([
            "--workspace-root",
            "/tmp/example-workspace",
            "--allow-root",
            "runtime",
            "start",
            "--product-db",
            "/tmp/product.sqlite3",
            "--product-execution-id",
            "product-001",
            "--context-path",
            "runtime/example.py",
            "--required-verification",
            "runtime-tests",
        ])
        self.assertIn(args.required_verification[0], VERIFICATION_REGISTRY)
        with self.assertRaises(SystemExit):
            build_parser().parse_args([
                "--workspace-root",
                "/tmp/example-workspace",
                "--allow-root",
                "runtime",
                "start",
                "--product-db",
                "/tmp/product.sqlite3",
                "--product-execution-id",
                "product-001",
                "--context-path",
                "runtime/example.py",
                "--required-verification",
                "rm-everything",
            ])


if __name__ == "__main__":
    unittest.main()
