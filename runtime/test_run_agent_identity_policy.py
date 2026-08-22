from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from runtime.agent_identity_registry import DISABLED_AGENT_IDS_ENV
from runtime.run_agent_identity_policy import build_parser, main


class AgentIdentityPolicyCliTests(unittest.TestCase):
    def test_validate_constructs_sdk_agents_without_model_call(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["validate"])
        self.assertEqual(0, code)
        payload = json.loads(buffer.getvalue())
        self.assertTrue(payload["passed"])
        self.assertEqual(38, payload["registered_identity_count"])
        self.assertEqual(38, payload["sdk_agent_count"])

    def test_manifest_is_read_only_and_includes_workflow_budgets(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["manifest"])
        self.assertEqual(0, code)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(38, len(payload["identities"]))
        self.assertEqual(7, len(payload["workflow_budgets"]))
        self.assertIn("read-only", payload["write_controls"])

    def test_status_reports_runtime_disable(self):
        buffer = io.StringIO()
        with patch.dict(os.environ, {DISABLED_AGENT_IDS_ENV: "marketing-agent"}, clear=True), redirect_stdout(buffer):
            code = main(["status", "--agent-id", "marketing-agent"])
        self.assertEqual(0, code)
        payload = json.loads(buffer.getvalue())
        self.assertFalse(payload["enabled"])
        self.assertEqual("marketing-agent", payload["identity"]["actor_id"])

    def test_unknown_identity_fails_closed(self):
        errors = io.StringIO()
        with redirect_stderr(errors):
            code = main(["status", "--agent-id", "missing-agent"])
        self.assertEqual(2, code)
        self.assertIn("not found", errors.getvalue())

    def test_parser_requires_command(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args([])


if __name__ == "__main__":
    unittest.main()
