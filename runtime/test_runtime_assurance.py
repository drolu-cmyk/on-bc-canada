from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.graph_kernel import GraphKernel
from runtime.runtime_assurance import RuntimeAssuranceSnapshotBuilder, RuntimeStoreSource
from runtime.runtime_assurance_graph import RuntimeAssuranceGraph


class FakeRuntimeAssuranceProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def analyze_reliability(self, snapshot):
        self.calls.append("reliability")
        return {
            "status": "degraded",
            "signals": [
                {
                    "graph_id": "product-development",
                    "severity": "high",
                    "signal": "Repeated evaluated failure is present in the aggregate execution record.",
                    "evidence": ["failed_count=1", "failure_categories.evaluation_failure=1"],
                    "recommended_action": "Inspect the failing release-control path before more executions.",
                }
            ],
            "telemetry_gaps": ["model_token_usage", "provider_latency"],
            "summary": "A bounded reliability concern is present.",
        }

    def analyze_controls(self, snapshot, reliability):
        self.calls.append("controls")
        return {
            "status": "intervention_recommended",
            "signals": [
                {
                    "control_area": "failure_handling",
                    "severity": "high",
                    "signal": "The aggregate failure requires accountable review.",
                    "evidence": ["product-development failure_rate > 0"],
                    "recommended_action": "Create a Product Development remediation problem for human-reviewed implementation.",
                    "requires_human_change": True,
                }
            ],
            "summary": "Human review is recommended; no runtime control is changed here.",
        }


class RuntimeAssuranceSnapshotTests(unittest.TestCase):
    def _generic_store(self, directory: str) -> Path:
        path = Path(directory) / "graphs.sqlite3"
        with sqlite3.connect(path) as connection:
            connection.execute(
                """
                CREATE TABLE graph_executions (
                    execution_id TEXT PRIMARY KEY,
                    graph_id TEXT NOT NULL,
                    graph_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    failure TEXT,
                    history_json TEXT NOT NULL,
                    pending_approval_json TEXT,
                    events_json TEXT NOT NULL
                )
                """
            )
            connection.executemany(
                "INSERT INTO graph_executions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        "prod-1",
                        "product-development",
                        "0.1.0",
                        "completed",
                        None,
                        json.dumps([{"node": 1}, {"node": 2}, {"node": 3}]),
                        None,
                        json.dumps([1, 2, 3, 4, 5]),
                    ),
                    (
                        "prod-2",
                        "product-development",
                        "0.1.0",
                        "failed",
                        "evaluation failed at security_review: release blocker",
                        json.dumps([{"node": 1}, {"node": 2}]),
                        None,
                        json.dumps([1, 2, 3, 4]),
                    ),
                    (
                        "learner-1",
                        "learner-execution",
                        "0.1.0",
                        "waiting_approval",
                        None,
                        json.dumps([{"node": 1}, {"node": 2}, {"node": 3}]),
                        json.dumps({"node_id": "human_assessment", "authority": "A3"}),
                        json.dumps([1, 2, 3, 4]),
                    ),
                ],
            )
        return path

    def _research_store(self, directory: str) -> Path:
        path = Path(directory) / "research.sqlite3"
        with sqlite3.connect(path) as connection:
            connection.execute(
                """
                CREATE TABLE research_executions (
                    execution_id TEXT PRIMARY KEY,
                    graph_id TEXT NOT NULL,
                    graph_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    failure TEXT,
                    history_json TEXT NOT NULL,
                    pending_approval_json TEXT,
                    events_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT INTO research_executions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "research-1",
                    "canadian-work-research",
                    "0.2.0",
                    "completed",
                    None,
                    json.dumps([{"node": index} for index in range(9)]),
                    None,
                    json.dumps(list(range(14))),
                ),
            )
        return path

    def test_snapshot_is_aggregate_json_safe_and_marks_telemetry_gaps(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            snapshot = RuntimeAssuranceSnapshotBuilder(
                (
                    RuntimeStoreSource(self._generic_store(directory), "generic_graph"),
                    RuntimeStoreSource(self._research_store(directory), "research"),
                )
            ).build()
        json.dumps(snapshot, sort_keys=True)
        product = next(item for item in snapshot["graphs"] if item["graph_id"] == "product-development")
        self.assertEqual(2, product["execution_count"])
        self.assertEqual(1, product["completed_count"])
        self.assertEqual(1, product["failed_count"])
        self.assertEqual(0.5, product["failure_rate"])
        self.assertEqual(1, product["failure_categories"]["evaluation_failure"])
        learner = next(item for item in snapshot["graphs"] if item["graph_id"] == "learner-execution")
        self.assertEqual(1, learner["waiting_approval_count"])
        self.assertFalse(snapshot["model_runtime"]["path_present"])
        self.assertFalse(snapshot["telemetry_coverage"]["model_token_usage"])
        self.assertFalse(snapshot["telemetry_coverage"]["model_monetary_cost"])
        self.assertFalse(snapshot["telemetry_coverage"]["provider_latency"])
        encoded = json.dumps(snapshot, sort_keys=True)
        self.assertNotIn("pending_approval_json", encoded)
        self.assertNotIn("history_json", encoded)

    def test_missing_store_is_reported_as_coverage_gap(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            snapshot = RuntimeAssuranceSnapshotBuilder(
                (RuntimeStoreSource(Path(directory) / "missing.sqlite3", "generic_graph"),)
            ).build()
        self.assertEqual([], snapshot["graphs"])
        self.assertFalse(snapshot["source_coverage"][0]["path_present"])


class RuntimeAssuranceGraphTests(unittest.TestCase):
    @staticmethod
    def _snapshot():
        return {
            "snapshot_version": "0.2.0",
            "graphs": [
                {
                    "graph_id": "product-development",
                    "versions": ["0.1.0"],
                    "execution_count": 2,
                    "completed_count": 1,
                    "failed_count": 1,
                    "waiting_approval_count": 0,
                    "failure_rate": 0.5,
                    "failure_categories": {"evaluation_failure": 1},
                }
            ],
            "source_coverage": [{"store_kind": "generic_graph", "path_present": True, "execution_count": 2}],
            "model_runtime": {"path_present": False, "reason": "telemetry_store_not_found", "workflows": []},
            "runtime_controls": {"disabled_agent_token_count": 0, "disabled_work_types": []},
            "telemetry_coverage": {
                "execution_status": True,
                "graph_version": True,
                "node_completion": True,
                "human_approval_state": True,
                "failure_reason_category": True,
                "event_count": True,
                "model_token_usage": False,
                "model_monetary_cost": False,
                "provider_latency": False,
                "tool_call_latency": False,
                "trace_sampling": False,
                "hosted_tool_latency": False,
            },
            "model_boundary": {
                "contains_learner_identity": False,
                "contains_raw_graph_state": False,
                "contains_prompts_or_model_outputs": False,
                "contains_tool_arguments_or_outputs": False,
                "contains_credentials": False,
            },
        }

    def test_intervention_recommendation_completes_without_runtime_mutation(self):
        provider = FakeRuntimeAssuranceProvider()
        graph = RuntimeAssuranceGraph(GraphKernel(), provider)
        graph.register()
        definition, execution = graph.start(execution_id="runtime-assurance-001", snapshot=self._snapshot())
        self.assertEqual("completed", execution.status)
        self.assertEqual(["reliability", "controls"], provider.calls)
        packet = execution.state["runtime_assurance_packet"]
        self.assertTrue(packet["human_runtime_action_recommended"])
        self.assertEqual("assurance and recommendation only; no runtime mutation", packet["boundary"])
        self.assertFalse(packet["assurance"]["agent_self_modification"])
        self.assertFalse(packet["assurance"]["runtime_policy_mutation"])
        self.assertEqual("runtime-assurance", definition.graph_id)

    def test_raw_graph_state_boundary_failure_prevents_agents(self):
        provider = FakeRuntimeAssuranceProvider()
        graph = RuntimeAssuranceGraph(GraphKernel(), provider)
        graph.register()
        snapshot = self._snapshot()
        snapshot["model_boundary"]["contains_raw_graph_state"] = True
        _, execution = graph.start(execution_id="runtime-assurance-002", snapshot=snapshot)
        self.assertEqual("failed", execution.status)
        self.assertIn("aggregate telemetry boundary", execution.failure)
        self.assertEqual([], provider.calls)

    def test_tool_payload_boundary_failure_prevents_agents(self):
        provider = FakeRuntimeAssuranceProvider()
        graph = RuntimeAssuranceGraph(GraphKernel(), provider)
        graph.register()
        snapshot = self._snapshot()
        snapshot["model_boundary"]["contains_tool_arguments_or_outputs"] = True
        _, execution = graph.start(execution_id="runtime-assurance-003", snapshot=snapshot)
        self.assertEqual("failed", execution.status)
        self.assertIn("aggregate telemetry boundary", execution.failure)
        self.assertEqual([], provider.calls)


if __name__ == "__main__":
    unittest.main()
