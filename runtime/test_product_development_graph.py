from __future__ import annotations

import unittest

from runtime.graph_kernel import GraphKernel
from runtime.product_development_graph import ProductDevelopmentGraph


class FakeProvider:
    def __init__(self, *, security_status="pass", security_blockers=None):
        self.security_status = security_status
        self.security_blockers = security_blockers or []

    def normalize(self, request):
        return {"problem": request["problem"].strip(), "market": "Canada", "release_authority": "human"}

    def analyze_product(self, request):
        return {
            "problem": request["problem"],
            "primary_users": ["learner"],
            "user_jobs": ["see what work requires attention"],
            "desired_outcome": "clear next action",
            "in_scope": ["learner home"],
            "out_of_scope": [],
            "success_signals": ["learner can identify next action"],
            "assumptions_to_test": [],
        }

    def analyze_experience(self, request, product):
        return {
            "key_tasks": ["identify next action"],
            "journey_steps": ["open home", "review current work", "continue"],
            "friction_risks": [],
            "information_architecture": ["current work", "capability map"],
            "research_gaps": [],
        }

    def design_interface(self, request, product, experience):
        return {
            "design_direction": "task-first learner workspace",
            "surfaces": [{"surface": "home", "purpose": "show next work"}],
            "interaction_rules": ["one primary action per current task"],
            "responsive_rules": ["core action remains visible on narrow screens"],
            "design_system_needs": ["status language"],
        }

    @staticmethod
    def review(status="pass", blockers=None):
        return {
            "status": status,
            "summary": "review complete",
            "release_blockers": blockers or [],
            "warnings": [],
            "recommendations": [],
        }

    def review_copy(self, request, product, interface):
        return self.review()

    def review_brand(self, request, interface, copy):
        return self.review()

    def plan_engineering(self, request, product, experience, interface):
        return {
            "architecture_summary": "extend current Next.js learner surface",
            "components": ["learner home"],
            "data_changes": [],
            "api_changes": [],
            "agent_changes": [],
            "migration_risks": [],
            "implementation_slices": ["render current work", "add empty states"],
            "rollback_strategy": "revert the feature commit",
        }

    def review_cloud(self, request, engineering):
        return self.review()

    def review_security(self, request, engineering, cloud):
        return self.review(self.security_status, self.security_blockers)

    def review_accessibility(self, request, experience, interface):
        return self.review()

    def plan_quality(self, request, product, engineering, security, accessibility):
        return self.review()


class ProductDevelopmentGraphTests(unittest.TestCase):
    def test_ready_packet_stops_at_a3_release_review_then_finalizes(self):
        kernel = GraphKernel()
        graph = ProductDevelopmentGraph(kernel=kernel, provider=FakeProvider())
        graph.register()
        definition, execution = graph.start(
            execution_id="product-1",
            request={"problem": "Learners cannot quickly see what work requires attention."},
        )
        self.assertEqual("waiting_approval", execution.status)
        self.assertEqual("release_review", execution.current_node)
        self.assertEqual("A3", execution.pending_approval["authority"])
        self.assertEqual("ready_for_human_review", execution.state["release_assurance"]["status"])
        self.assertNotIn("release_record", execution.state)

        execution = kernel.decide(
            definition,
            execution,
            approved=True,
            approver_id="release-accountable-person",
            note="Release packet reviewed for implementation.",
        )
        self.assertEqual("completed", execution.status)
        self.assertEqual("authorized_for_implementation", execution.state["release_record"]["status"])
        self.assertEqual("complete", execution.state["product_status"])

    def test_security_blocker_prevents_human_release_gate(self):
        kernel = GraphKernel()
        graph = ProductDevelopmentGraph(
            kernel=kernel,
            provider=FakeProvider(
                security_status="block",
                security_blockers=["agent would receive shared production administrator credentials"],
            ),
        )
        graph.register()
        _, execution = graph.start(
            execution_id="product-2",
            request={"problem": "Add an autonomous production maintenance action."},
        )
        self.assertEqual("completed", execution.status)
        self.assertEqual("blocked", execution.state["release_record"]["status"])
        self.assertEqual("blocked", execution.state["product_status"])
        self.assertIsNone(execution.pending_approval)
        blocking_reviews = {item["review"] for item in execution.state["release_assurance"]["blocking"]}
        self.assertIn("security_review", blocking_reviews)

    def test_release_packet_contains_all_specialist_outputs(self):
        kernel = GraphKernel()
        graph = ProductDevelopmentGraph(kernel=kernel, provider=FakeProvider())
        graph.register()
        definition, execution = graph.start(
            execution_id="product-3",
            request={"problem": "Improve the learner capability view."},
        )
        execution = kernel.decide(
            definition,
            execution,
            approved=True,
            approver_id="release-accountable-person",
            note="Reviewed.",
        )
        packet = execution.state["release_record"]["packet"]
        self.assertEqual(
            {
                "request",
                "product",
                "experience",
                "interface",
                "copy",
                "brand",
                "engineering",
                "cloud",
                "security",
                "accessibility",
                "quality",
                "assurance",
            },
            set(packet),
        )

    def test_specialist_agents_are_a1_and_release_human_is_a3(self):
        definition = ProductDevelopmentGraph.definition()
        agent_nodes = [node for node in definition.nodes if node.actor.kind == "agent"]
        self.assertGreaterEqual(len(agent_nodes), 10)
        self.assertTrue(all(node.actor.authority == "A1" for node in agent_nodes))
        release = next(node for node in definition.nodes if node.node_id == "release_review")
        self.assertEqual("human", release.actor.kind)
        self.assertEqual("A3", release.actor.authority)


if __name__ == "__main__":
    unittest.main()
