from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.graph_execution_store import GraphExecutionStore
from runtime.implementation_delivery_runner import resume_implementation_delivery, start_implementation_delivery
from runtime.implementation_workspace import RegisteredVerificationRunner, StagingWorkspace
from runtime.test_implementation_delivery_graph import FakeProvider, authorized_request


class RaisingProvider:
    def normalize(self, request):
        raise AssertionError("resume must not rerun implementation agents")

    def plan_changes(self, request, repository_context):
        raise AssertionError("resume must not rerun implementation agents")

    def generate_changes(self, request, repository_context, plan):
        raise AssertionError("resume must not rerun implementation agents")

    def review_code(self, request, plan, applied_changes, verification):
        raise AssertionError("resume must not rerun implementation agents")

    def review_security(self, request, plan, applied_changes, verification):
        raise AssertionError("resume must not rerun implementation agents")

    def review_quality(self, request, applied_changes, verification):
        raise AssertionError("resume must not rerun implementation agents")


class ImplementationDeliveryRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "runtime").mkdir()
        (self.root / "runtime" / "example.py").write_text("VALUE = 1\n", encoding="utf-8")
        self.store = GraphExecutionStore(self.root / "implementation.sqlite3")
        self.workspace = StagingWorkspace(self.root, allowed_roots=("runtime",))
        self.verifier = RegisteredVerificationRunner(self.root, {"smoke": ("python", "-c", "print('ok')")})

    def tearDown(self):
        self.tmp.cleanup()

    def test_a3_review_survives_restart_without_rerunning_agents(self):
        execution = start_implementation_delivery(
            provider=FakeProvider(),
            execution_store=self.store,
            workspace=self.workspace,
            verifier=self.verifier,
            execution_id="implementation-runner-001",
            request=authorized_request(),
        )
        self.assertEqual("waiting_approval", execution.status)

        completed = resume_implementation_delivery(
            provider=RaisingProvider(),
            execution_store=GraphExecutionStore(self.root / "implementation.sqlite3"),
            workspace=StagingWorkspace(self.root, allowed_roots=("runtime",)),
            verifier=self.verifier,
            execution_id=execution.execution_id,
            approved=True,
            approver_id="merge-deploy-accountable-person",
            note="Reviewed exact staged bytes and verification evidence.",
        )
        self.assertEqual("completed", completed.status)
        self.assertEqual("authorized_for_merge_or_deploy", completed.state["delivery_record"]["status"])
        terminal = self.store.get_terminal_record(execution.execution_id, "delivery_record")
        self.assertEqual("authorized_for_merge_or_deploy", terminal["status"])

    def test_staging_drift_blocks_human_authorization(self):
        execution = start_implementation_delivery(
            provider=FakeProvider(),
            execution_store=self.store,
            workspace=self.workspace,
            verifier=self.verifier,
            execution_id="implementation-runner-drift",
            request=authorized_request(),
        )
        (self.root / "runtime" / "example.py").write_text("VALUE = 99\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed after verification"):
            resume_implementation_delivery(
                provider=RaisingProvider(),
                execution_store=self.store,
                workspace=self.workspace,
                verifier=self.verifier,
                execution_id=execution.execution_id,
                approved=True,
                approver_id="merge-deploy-accountable-person",
                note="Attempt authorization after drift.",
            )
        stored, _ = self.store.load_execution(execution.execution_id)
        self.assertEqual("waiting_approval", stored.status)
        self.assertIsNone(self.store.get_terminal_record(execution.execution_id, "delivery_record"))


if __name__ == "__main__":
    unittest.main()
