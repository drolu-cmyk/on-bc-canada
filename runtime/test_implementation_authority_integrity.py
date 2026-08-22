from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.graph_kernel import GraphKernel
from runtime.implementation_delivery_graph import ImplementationDeliveryGraph
from runtime.implementation_workspace import RegisteredVerificationRunner, StagingWorkspace
from runtime.test_implementation_delivery_graph import FakeProvider, authorized_request


class UnregisteredVerificationProvider(FakeProvider):
    def plan_changes(self, request, repository_context):
        plan = super().plan_changes(request, repository_context)
        plan["verification_ids"] = ["smoke", "arbitrary-command"]
        return plan


class OutsidePlanChangeProvider(FakeProvider):
    def plan_changes(self, request, repository_context):
        plan = super().plan_changes(request, repository_context)
        plan["files_to_change"] = ["runtime/example.py"]
        return plan

    def generate_changes(self, request, repository_context, plan):
        result = super().generate_changes(request, repository_context, plan)
        result["changes"][0]["path"] = "runtime/other.py"
        result["changes"][0]["operation"] = "create"
        result["changes"][0]["expected_sha256"] = None
        return result


class ImplementationAuthorityIntegrityTests(unittest.TestCase):
    def graph(self, root: Path, provider):
        kernel = GraphKernel()
        workspace = StagingWorkspace(root, allowed_roots=("runtime",))
        verifier = RegisteredVerificationRunner(root, {"smoke": ("python", "-c", "print('ok')")})
        graph = ImplementationDeliveryGraph(kernel=kernel, provider=provider, workspace=workspace, verifier=verifier)
        graph.register()
        return graph

    def test_unregistered_verification_fails_before_change_generation_or_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "runtime").mkdir()
            target = root / "runtime" / "example.py"
            target.write_text("VALUE = 1\n", encoding="utf-8")
            graph = self.graph(root, UnregisteredVerificationProvider())
            _, execution = graph.start(execution_id="implementation-unregistered-verification", request=authorized_request())
            self.assertEqual("failed", execution.status)
            self.assertIn("unregistered verification", execution.failure)
            self.assertEqual("VALUE = 1\n", target.read_text(encoding="utf-8"))
            self.assertNotIn("generated_changes", execution.state)

    def test_generated_path_outside_plan_is_blocked_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "runtime").mkdir()
            target = root / "runtime" / "example.py"
            target.write_text("VALUE = 1\n", encoding="utf-8")
            graph = self.graph(root, OutsidePlanChangeProvider())
            _, execution = graph.start(execution_id="implementation-outside-plan", request=authorized_request())
            self.assertEqual("completed", execution.status)
            self.assertEqual("blocked", execution.state["delivery_record"]["status"])
            self.assertFalse((root / "runtime" / "other.py").exists())
            self.assertEqual("VALUE = 1\n", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
