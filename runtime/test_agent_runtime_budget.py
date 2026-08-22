from __future__ import annotations

import unittest

from runtime.agent_identity_registry import WORKFLOW_RUNTIME_BUDGETS
from runtime.platform_graph_registry import GRAPH_CONTRACTS


def max_agent_calls_on_any_path(definition) -> int:
    nodes = {node.node_id: node for node in definition.nodes}
    outgoing: dict[str, list[str]] = {}
    for edge in definition.edges:
        outgoing.setdefault(edge.source, []).append(edge.target)

    def walk(node_id: str, path: tuple[str, ...]) -> int:
        if node_id in path:
            raise AssertionError(f"graph cycle is not allowed for static model-call budgeting: {node_id}")
        count = 1 if nodes[node_id].actor.kind == "agent" else 0
        targets = outgoing.get(node_id, [])
        if not targets:
            return count
        return count + max(walk(target, (*path, node_id)) for target in targets)

    return walk(definition.start_node, ())


class AgentRuntimeBudgetTests(unittest.TestCase):
    def test_each_graph_budget_matches_maximum_agent_calls_on_a_structural_path(self):
        for work_type, contract in GRAPH_CONTRACTS.items():
            with self.subTest(work_type=work_type):
                observed = max_agent_calls_on_any_path(contract.definition())
                registered = WORKFLOW_RUNTIME_BUDGETS[work_type].max_model_calls_per_execution
                self.assertEqual(observed, registered)

    def test_platform_orchestrator_is_one_model_call_with_no_automatic_retry(self):
        budget = WORKFLOW_RUNTIME_BUDGETS["platform_orchestration"]
        self.assertEqual(1, budget.max_model_calls_per_execution)
        self.assertEqual(0, budget.retry_limit_per_agent)

    def test_all_launch_workflows_disable_automatic_model_retries(self):
        self.assertTrue(all(item.retry_limit_per_agent == 0 for item in WORKFLOW_RUNTIME_BUDGETS.values()))


if __name__ == "__main__":
    unittest.main()
