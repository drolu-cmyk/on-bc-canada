from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from runtime.run_platform_harness import build_parser, main


class PlatformHarnessCliTests(unittest.TestCase):
    def test_audit_runs_without_model_access(self):
        code = main(["audit"])
        self.assertEqual(0, code)

    def test_route_allows_bounded_analysis(self):
        code = main([
            "route",
            "--workflow-key",
            "employer_workforce",
            "--mode",
            "analyze",
            "--effect",
            "analysis",
            "--data-class",
            "organization_aggregate",
        ])
        self.assertEqual(0, code)

    def test_route_blocks_external_execution(self):
        code = main([
            "route",
            "--workflow-key",
            "business_operations",
            "--mode",
            "execute",
            "--effect",
            "external_contact",
            "--data-class",
            "internal_operational",
        ])
        self.assertEqual(2, code)

    def test_model_context_blocks_private_learner_reference_for_career_agent(self):
        code = main([
            "model-context",
            "--workflow-key",
            "career_mobility",
            "--data-class",
            "learner_private_reference",
        ])
        self.assertEqual(2, code)

    def test_handoff_blocks_employer_direct_to_work_intelligence(self):
        code = main([
            "handoff",
            "--source-workflow-key",
            "employer_workforce",
            "--target-kind",
            "store",
            "--target-id",
            "work-intelligence",
            "--data-class",
            "capability_signal",
        ])
        self.assertEqual(2, code)

    def test_live_propose_requires_api_key_before_model_call(self):
        with patch.dict(os.environ, {}, clear=True):
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

    def test_route_requires_mode_and_effect(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["route", "--workflow-key", "research_evidence"])


if __name__ == "__main__":
    unittest.main()
