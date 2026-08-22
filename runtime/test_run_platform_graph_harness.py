from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from runtime.run_platform_graph_harness import build_parser, main


class PlatformGraphHarnessCliTests(unittest.TestCase):
    def test_validate_command_returns_success_for_current_registry(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["validate"])
        self.assertEqual(0, code)
        payload = json.loads(buffer.getvalue())
        self.assertTrue(payload["passed"])
        self.assertEqual(8, len(payload["graphs"]))
        self.assertTrue(payload["dispatch_cases"]["passed"])

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

    def test_dispatch_allows_bounded_employer_analysis(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main([
                "dispatch",
                "--work-type",
                "employer_workforce",
                "--mode",
                "analyze",
                "--effect",
                "analysis",
                "--data-class",
                "organization_workflow",
                "--data-class",
                "aggregate_metrics",
            ])
        self.assertEqual(0, code)
        payload = json.loads(buffer.getvalue())
        self.assertTrue(payload["allowed"])
        self.assertEqual("employer-workforce", payload["graph_id"])

    def test_dispatch_blocks_external_execution(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main([
                "dispatch",
                "--work-type",
                "business_operations",
                "--mode",
                "execute",
                "--effect",
                "external_contact",
                "--data-class",
                "operational",
            ])
        self.assertEqual(2, code)
        payload = json.loads(buffer.getvalue())
        self.assertFalse(payload["allowed"])

    def test_model_context_blocks_private_learner_reference_for_career_agent(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main([
                "model-context",
                "--work-type",
                "career_mobility",
                "--data-class",
                "learner_private_reference",
            ])
        self.assertEqual(2, code)
        payload = json.loads(buffer.getvalue())
        self.assertFalse(payload["allowed"])

    def test_handoff_blocks_employer_direct_to_work_intelligence(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main([
                "handoff",
                "--source-work-type",
                "employer_workforce",
                "--target-kind",
                "store",
                "--target-id",
                "work-intelligence",
                "--data-class",
                "capability_signal",
            ])
        self.assertEqual(2, code)
        payload = json.loads(buffer.getvalue())
        self.assertFalse(payload["allowed"])

    def test_live_propose_requires_api_key_before_model_call(self):
        errors = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stderr(errors):
            code = main([
                "propose",
                "--objective",
                "Research a new agent capability signal.",
                "--mode",
                "analyze",
                "--effect",
                "analysis",
                "--data-class",
                "public_research",
            ])
        self.assertEqual(2, code)
        self.assertIn("OPENAI_API_KEY", errors.getvalue())

    def test_parser_requires_command(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args([])


if __name__ == "__main__":
    unittest.main()
