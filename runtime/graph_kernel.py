"""Small provider-neutral graph runtime for accountable autonomous work.

The graph owns sequencing and authority. A node may be deterministic code, an
agent, or a human decision. Model providers are adapters behind node handlers;
they are not the workflow engine.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from runtime.control_plane import EventLedger

ActorKind = Literal["service", "agent", "human"]
ExecutionStatus = Literal["ready", "running", "waiting_approval", "completed", "failed"]


@dataclass(frozen=True)
class ActorRef:
    actor_id: str
    kind: ActorKind
    authority: str = "A1"


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    actor: ActorRef
    handler: str | None = None
    evaluator: str | None = None
    approval_reason: str | None = None

    def __post_init__(self) -> None:
        if self.actor.kind == "human" and self.handler is not None:
            raise ValueError("human nodes cannot execute automated handlers")
        if self.actor.kind != "human" and not self.handler:
            raise ValueError("automated nodes require a handler")


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    route: str | None = None


@dataclass(frozen=True)
class GraphDefinition:
    graph_id: str
    version: str
    start_node: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]

    def __post_init__(self) -> None:
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("graph node IDs must be unique")
        if self.start_node not in node_ids:
            raise ValueError("start node is missing")
        for edge in self.edges:
            if edge.source not in node_ids or edge.target not in node_ids:
                raise ValueError("edge references an unknown node")


@dataclass
class NodeResult:
    patch: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    route: str | None = None


@dataclass
class GraphExecution:
    execution_id: str
    graph_id: str
    graph_version: str
    current_node: str
    state: dict[str, Any]
    status: ExecutionStatus = "ready"
    history: list[dict[str, Any]] = field(default_factory=list)
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    pending_approval: dict[str, Any] | None = None
    failure: str | None = None


Handler = Callable[[dict[str, Any]], NodeResult]
Evaluator = Callable[[dict[str, Any], NodeResult], tuple[bool, str]]


class GraphKernel:
    """Execute one graph deterministically around injected reasoning handlers."""

    def __init__(self, *, program_id: str = "applied-ai-training-canada", ledger: EventLedger | None = None) -> None:
        self.program_id = program_id
        self.ledger = ledger or EventLedger()
        self.handlers: dict[str, Handler] = {}
        self.evaluators: dict[str, Evaluator] = {}
        self.executions: dict[str, GraphExecution] = {}

    def register_handler(self, name: str, handler: Handler) -> None:
        if not name or name in self.handlers:
            raise ValueError("handler name must be non-empty and unique")
        self.handlers[name] = handler

    def register_evaluator(self, name: str, evaluator: Evaluator) -> None:
        if not name or name in self.evaluators:
            raise ValueError("evaluator name must be non-empty and unique")
        self.evaluators[name] = evaluator

    def start(self, definition: GraphDefinition, *, execution_id: str, state: dict[str, Any]) -> GraphExecution:
        existing = self.executions.get(execution_id)
        if existing:
            return existing
        execution = GraphExecution(
            execution_id=execution_id,
            graph_id=definition.graph_id,
            graph_version=definition.version,
            current_node=definition.start_node,
            state=deepcopy(state),
        )
        self.executions[execution_id] = execution
        self._event(execution, "graph.execution_started.v1", {"start_node": definition.start_node})
        return execution

    def run(self, definition: GraphDefinition, execution: GraphExecution, *, max_steps: int = 100) -> GraphExecution:
        self._assert_definition(definition, execution)
        if execution.status in {"completed", "failed", "waiting_approval"}:
            return execution
        execution.status = "running"
        for _ in range(max_steps):
            node = self._node(definition, execution.current_node)
            if node.actor.kind == "human":
                execution.status = "waiting_approval"
                execution.pending_approval = {
                    "node_id": node.node_id,
                    "reason": node.approval_reason or "human decision required",
                    "authority": node.actor.authority,
                }
                self._event(execution, "graph.approval_requested.v1", execution.pending_approval)
                return execution

            handler = self.handlers.get(node.handler or "")
            if not handler:
                return self._fail(execution, f"handler not registered: {node.handler}")

            self._event(execution, "graph.node_started.v1", {"node_id": node.node_id, "actor_id": node.actor.actor_id})
            try:
                result = handler(deepcopy(execution.state))
            except Exception as exc:
                return self._fail(execution, f"node {node.node_id} failed: {exc}")

            if node.evaluator:
                evaluator = self.evaluators.get(node.evaluator)
                if not evaluator:
                    return self._fail(execution, f"evaluator not registered: {node.evaluator}")
                passed, reason = evaluator(deepcopy(execution.state), result)
                self._event(
                    execution,
                    "graph.evaluation_completed.v1",
                    {"node_id": node.node_id, "passed": passed, "reason": reason},
                )
                if not passed:
                    return self._fail(execution, f"evaluation failed at {node.node_id}: {reason}")

            execution.state.update(deepcopy(result.patch))
            execution.history.append({
                "node_id": node.node_id,
                "actor_id": node.actor.actor_id,
                "route": result.route,
                "evidence": deepcopy(result.evidence),
            })
            execution.checkpoints.append({
                "node_id": node.node_id,
                "state": deepcopy(execution.state),
                "history_length": len(execution.history),
            })
            self._event(
                execution,
                "graph.node_completed.v1",
                {"node_id": node.node_id, "route": result.route, "evidence_count": len(result.evidence)},
            )

            next_node = self._next(definition, node.node_id, result.route)
            if next_node is None:
                execution.status = "completed"
                self._event(execution, "graph.execution_completed.v1", {"final_node": node.node_id})
                return execution
            execution.current_node = next_node

        return self._fail(execution, f"max steps exceeded: {max_steps}")

    def decide(
        self,
        definition: GraphDefinition,
        execution: GraphExecution,
        *,
        approved: bool,
        approver_id: str,
        note: str = "",
    ) -> GraphExecution:
        self._assert_definition(definition, execution)
        if execution.status != "waiting_approval" or not execution.pending_approval:
            raise ValueError("execution is not waiting for approval")
        node_id = execution.pending_approval["node_id"]
        self._event(
            execution,
            "graph.approval_decided.v1",
            {"node_id": node_id, "approved": approved, "approver_id": approver_id, "note": note},
        )
        execution.history.append({"node_id": node_id, "actor_id": approver_id, "approved": approved, "note": note})
        execution.checkpoints.append({
            "node_id": node_id,
            "state": deepcopy(execution.state),
            "history_length": len(execution.history),
        })
        execution.pending_approval = None
        if not approved:
            return self._fail(execution, f"human approval denied at {node_id}")
        next_node = self._next(definition, node_id, "approved")
        if next_node is None:
            execution.status = "completed"
            self._event(execution, "graph.execution_completed.v1", {"final_node": node_id})
            return execution
        execution.current_node = next_node
        execution.status = "ready"
        return self.run(definition, execution)

    @staticmethod
    def checkpoint(execution: GraphExecution, node_id: str) -> dict[str, Any] | None:
        for item in reversed(execution.checkpoints):
            if item["node_id"] == node_id:
                return deepcopy(item)
        return None

    @staticmethod
    def _node(definition: GraphDefinition, node_id: str) -> GraphNode:
        return next(node for node in definition.nodes if node.node_id == node_id)

    @staticmethod
    def _next(definition: GraphDefinition, source: str, route: str | None) -> str | None:
        edges = [edge for edge in definition.edges if edge.source == source]
        if not edges:
            return None
        routed = [edge for edge in edges if edge.route == route]
        if routed:
            if len(routed) > 1:
                raise ValueError(f"ambiguous routed edges from {source}: {route}")
            return routed[0].target
        defaults = [edge for edge in edges if edge.route is None]
        if len(defaults) == 1:
            return defaults[0].target
        if len(defaults) > 1:
            raise ValueError(f"ambiguous default edges from {source}")
        raise ValueError(f"no edge from {source} for route {route!r}")

    def _event(self, execution: GraphExecution, event_type: str, payload: dict[str, Any]) -> None:
        sequence = len(self.ledger.events) + 1
        self.ledger.append(
            event_type=event_type,
            program_id=self.program_id,
            producer="graph-runtime",
            actor_id="graph-kernel",
            correlation_id=f"corr-{execution.execution_id}",
            idempotency_key=f"graph:{execution.execution_id}:{event_type}:{sequence}",
            payload={"graph_id": execution.graph_id, "graph_version": execution.graph_version, **payload},
            privacy_class="internal_operational",
            retention_class="quality_record",
        )

    def _fail(self, execution: GraphExecution, reason: str) -> GraphExecution:
        execution.status = "failed"
        execution.failure = reason
        self._event(execution, "graph.execution_failed.v1", {"reason": reason, "node_id": execution.current_node})
        return execution

    @staticmethod
    def _assert_definition(definition: GraphDefinition, execution: GraphExecution) -> None:
        if definition.graph_id != execution.graph_id or definition.version != execution.graph_version:
            raise ValueError("graph definition does not match execution")
