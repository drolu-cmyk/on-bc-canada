import unittest

from runtime.graph_kernel import ActorRef, GraphDefinition, GraphEdge, GraphKernel, GraphNode, NodeResult


class GraphKernelTests(unittest.TestCase):
    def test_conditional_path_and_checkpoint(self):
        kernel = GraphKernel()
        kernel.register_handler("start", lambda state: NodeResult(patch={"risk": "high"}, route="high"))
        kernel.register_handler("finish", lambda state: NodeResult(patch={"done": True}))
        graph = GraphDefinition(
            graph_id="test",
            version="1",
            start_node="classify",
            nodes=(
                GraphNode("classify", ActorRef("classifier", "service"), "start"),
                GraphNode("finish", ActorRef("finisher", "service"), "finish"),
            ),
            edges=(GraphEdge("classify", "finish", route="high"),),
        )
        execution = kernel.start(graph, execution_id="exec-1", state={})
        execution = kernel.run(graph, execution)
        self.assertEqual("completed", execution.status)
        self.assertTrue(execution.state["done"])
        self.assertEqual("high", kernel.checkpoint(execution, "classify")["state"]["risk"])

    def test_human_approval_interrupt_and_resume(self):
        kernel = GraphKernel()
        kernel.register_handler("prepare", lambda state: NodeResult(patch={"change": "candidate"}))
        kernel.register_handler("finish", lambda state: NodeResult(patch={"published": True}))
        graph = GraphDefinition(
            graph_id="approval",
            version="1",
            start_node="prepare",
            nodes=(
                GraphNode("prepare", ActorRef("agent", "agent"), "prepare"),
                GraphNode("approve", ActorRef("human", "human", authority="A3"), approval_reason="review"),
                GraphNode("finish", ActorRef("service", "service"), "finish"),
            ),
            edges=(
                GraphEdge("prepare", "approve"),
                GraphEdge("approve", "finish", route="approved"),
            ),
        )
        execution = kernel.run(graph, kernel.start(graph, execution_id="exec-2", state={}))
        self.assertEqual("waiting_approval", execution.status)
        resumed = kernel.decide(graph, execution, approved=True, approver_id="reviewer-1")
        self.assertEqual("completed", resumed.status)
        self.assertTrue(resumed.state["published"])
        self.assertTrue(
            any(event["event_type"] == "graph.approval_decided.v1" for event in kernel.ledger.events)
        )

    def test_evaluator_can_stop_execution(self):
        kernel = GraphKernel()
        kernel.register_handler("bad", lambda state: NodeResult(patch={"value": 0}))
        kernel.register_evaluator(
            "positive",
            lambda state, result: (result.patch["value"] > 0, "value must be positive"),
        )
        graph = GraphDefinition(
            graph_id="eval",
            version="1",
            start_node="check",
            nodes=(GraphNode("check", ActorRef("service", "service"), "bad", "positive"),),
            edges=(),
        )
        execution = kernel.run(graph, kernel.start(graph, execution_id="exec-3", state={}))
        self.assertEqual("failed", execution.status)
        self.assertIn("evaluation failed", execution.failure)


if __name__ == "__main__":
    unittest.main()
