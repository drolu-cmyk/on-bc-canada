from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from runtime.graph_kernel import GraphKernel
from runtime.implementation_delivery_graph import ImplementationDeliveryGraph
from runtime.implementation_workspace import RegisteredVerificationRunner, StagingWorkspace


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def authorized_request():
    return {
        "source_execution_id": "product-001",
        "release_record": {
            "status": "authorized_for_implementation",
            "packet": {"product": {"problem": "Improve learner home"}},
        },
        "context_paths": ["runtime/example.py"],
        "allowed_verification_ids": ["smoke"],
        "required_verification_ids": ["smoke"],
    }


class FakeProvider:
    def __init__(self, *, review_status="pass", blocker=None, generated_secret=False):
        self.review_status = review_status
        self.blocker = blocker
        self.generated_secret = generated_secret

    def normalize(self, request):
        if request["release_record"]["status"] != "authorized_for_implementation":
            raise ValueError("implementation requires authorized release")
        return request

    def plan_changes(self, request, repository_context):
        return {
            "objective": "Update staging example",
            "change_slices": ["update example"],
            "files_to_change": ["runtime/example.py"],
            "verification_ids": ["smoke"],
            "risks": [],
            "rollback_note": "restore the previous file hash",
        }

    def generate_changes(self, request, repository_context, plan):
        snapshot = repository_context[0]
        content = 'OPENAI_API_KEY="sk-proj-abcdefghijklmnopqrstuvwxyz123456"\n' if self.generated_secret else "VALUE = 2\n"
        return {
            "changes": [
                {
                    "operation": "update",
                    "path": "runtime/example.py",
                    "reason": "Implement the authorized learner-home behavior.",
                    "content": content,
                    "expected_sha256": snapshot["sha256"],
                }
            ],
            "implementation_note": "fixture change",
        }

    def _review(self):
        return {
            "status": self.review_status,
            "summary": "review complete",
            "blockers": [self.blocker] if self.blocker else [],
            "warnings": [],
            "findings": [],
        }

    def review_code(self, request, plan, applied_changes, verification):
        return self._review()

    def review_security(self, request, plan, applied_changes, verification):
        return self._review()

    def review_quality(self, request, applied_changes, verification):
        return self._review()


class ImplementationDeliveryGraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "runtime").mkdir()
        (self.root / "runtime" / "example.py").write_text("VALUE = 1\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def graph(self, provider=None, verification_command=None):
        kernel = GraphKernel()
        workspace = StagingWorkspace(self.root, allowed_roots=("runtime",))
        verifier = RegisteredVerificationRunner(
            self.root,
            {"smoke": verification_command or ("python", "-c", "print('ok')")},
        )
        graph = ImplementationDeliveryGraph(
            kernel=kernel,
            provider=provider or FakeProvider(),
            workspace=workspace,
            verifier=verifier,
        )
        graph.register()
        return kernel, graph

    def test_verified_staging_change_stops_at_a3_before_merge_or_deploy(self):
        kernel, graph = self.graph()
        definition, execution = graph.start(execution_id="implementation-1", request=authorized_request())
        self.assertEqual("waiting_approval", execution.status)
        self.assertEqual("merge_deploy_review", execution.current_node)
        self.assertEqual("A3", execution.pending_approval["authority"])
        self.assertEqual("VALUE = 2\n", (self.root / "runtime" / "example.py").read_text(encoding="utf-8"))
        self.assertTrue(all(item["passed"] for item in execution.state["verification_results"]))

        execution = kernel.decide(
            definition,
            execution,
            approved=True,
            approver_id="merge-deploy-accountable-person",
            note="Reviewed staging changes and verification evidence.",
        )
        self.assertEqual("completed", execution.status)
        self.assertEqual("authorized_for_merge_or_deploy", execution.state["delivery_record"]["status"])

    def test_secret_like_change_is_blocked_before_staging_mutation(self):
        _, graph = self.graph(provider=FakeProvider(generated_secret=True))
        _, execution = graph.start(execution_id="implementation-secret", request=authorized_request())
        self.assertEqual("completed", execution.status)
        self.assertEqual("blocked", execution.state["delivery_record"]["status"])
        self.assertEqual("VALUE = 1\n", (self.root / "runtime" / "example.py").read_text(encoding="utf-8"))
        self.assertNotIn("applied_changes", execution.state)

    def test_failed_registered_verification_blocks_delivery(self):
        _, graph = self.graph(verification_command=("python", "-c", "raise SystemExit(7)"))
        _, execution = graph.start(execution_id="implementation-test-fail", request=authorized_request())
        self.assertEqual("completed", execution.status)
        self.assertEqual("blocked", execution.state["delivery_record"]["status"])
        self.assertTrue(any("failed registered verifications" in item for item in execution.state["delivery_assurance"]["blockers"]))
        self.assertIsNone(execution.pending_approval)

    def test_blocking_security_or_code_review_prevents_a3(self):
        provider = FakeProvider(review_status="block", blocker="material review defect")
        _, graph = self.graph(provider=provider)
        _, execution = graph.start(execution_id="implementation-review-block", request=authorized_request())
        self.assertEqual("completed", execution.status)
        self.assertEqual("blocked", execution.state["delivery_record"]["status"])
        self.assertIsNone(execution.pending_approval)

    def test_a2_side_effects_are_services_and_model_workers_remain_a1(self):
        definition = ImplementationDeliveryGraph.definition()
        agents = [node for node in definition.nodes if node.actor.kind == "agent"]
        self.assertTrue(all(node.actor.authority == "A1" for node in agents))
        apply_node = next(node for node in definition.nodes if node.node_id == "apply_staging_changes")
        verify_node = next(node for node in definition.nodes if node.node_id == "run_verification")
        human = next(node for node in definition.nodes if node.node_id == "merge_deploy_review")
        self.assertEqual("A2", apply_node.actor.authority)
        self.assertEqual("service", apply_node.actor.kind)
        self.assertEqual("A2", verify_node.actor.authority)
        self.assertEqual("A3", human.actor.authority)


if __name__ == "__main__":
    unittest.main()
