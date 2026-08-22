from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from runtime.run_platform_graph_harness import build_parser, main


class PlatformGraphHarnessCliTests(unittest.TestCase):
    def test_validate_command_returns_success_for_current_registry(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["validate"])
        self.assertEqual(0, code)
        payload = json.loads(buffer.getvalue())
        self.assertTrue(payload["passed"])
        self.assertEqual(6, len(payload["graphs"]))

    def test_route_returns_explicit_contract_without_model_classification(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["route", "--work-type", "learner_execution"])
        self.assertEqual(0, code)
        payload = json.loads(buffer.getvalue())
        self.assertEqual("learner-execution", payload["graph_id"])
        self.assertEqual([{"node_id": "human_assessment", "authority": "A3"}], payload["human_gates"])

    def test_unknown_route_fails_closed(self):
        errors = io.StringIO()
        with redirect_stderr(errors):
            code = main(["route", "--work-type", "unknown"])
        self.assertEqual(2, code)
        self.assertIn("unknown platform work type", errors.getvalue())

    def test_parser_requires_command(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args([])


if __name__ == "__main__":
    unittest.main()
