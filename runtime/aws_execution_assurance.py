"""Aggregate privacy-safe execution telemetry from the AWS durable graph store."""
from __future__ import annotations

from typing import Any

from runtime.aws_durable_execution import AwsDurableExecutionConfig, _read_s, _s
from runtime.runtime_assurance import RuntimeAssuranceSnapshotBuilder


EXECUTION_INDEX_NAME = "ExecutionUpdatedIndex"


class DynamoRuntimeExecutionSource:
    """Read only operational fields from execution state items through a GSI."""

    def __init__(
        self,
        *,
        config: AwsDurableExecutionConfig | None = None,
        client: Any | None = None,
    ) -> None:
        self.config = config or AwsDurableExecutionConfig.from_environment()
        if client is None:
            import boto3

            client = boto3.client("dynamodb", region_name=self.config.region)
        self.client = client

    def read_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        start_key: dict[str, Any] | None = None
        while True:
            request: dict[str, Any] = {
                "TableName": self.config.table_name,
                "IndexName": EXECUTION_INDEX_NAME,
                "KeyConditionExpression": "#sk = :state",
                "ExpressionAttributeNames": {"#sk": "sk", "#execution_status": "status"},
                "ExpressionAttributeValues": {":state": _s("STATE")},
                "ProjectionExpression": (
                    "graph_id, graph_version, #execution_status, failure, history_json, "
                    "pending_approval_json, events_json, updated_at"
                ),
            }
            if start_key:
                request["ExclusiveStartKey"] = start_key
            response = self.client.query(**request)
            for item in response.get("Items", []):
                rows.append(
                    {
                        "graph_id": _read_s(item, "graph_id", "") or "",
                        "graph_version": _read_s(item, "graph_version", "") or "",
                        "status": _read_s(item, "status", "ready") or "ready",
                        "failure": _read_s(item, "failure"),
                        "history_json": _read_s(item, "history_json", "[]") or "[]",
                        "pending_approval_json": _read_s(item, "pending_approval_json"),
                        "events_json": _read_s(item, "events_json", "[]") or "[]",
                    }
                )
            start_key = response.get("LastEvaluatedKey")
            if not start_key:
                break
        return rows


def aggregate_dynamo_execution_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    graph_metrics: dict[str, dict[str, Any]] = {}
    for row in rows:
        RuntimeAssuranceSnapshotBuilder._accumulate(graph_metrics, row)

    graphs: list[dict[str, Any]] = []
    for graph_id in sorted(graph_metrics):
        metric = graph_metrics[graph_id]
        executions = metric["execution_count"]
        graphs.append(
            {
                "graph_id": graph_id,
                "versions": sorted(metric["versions"]),
                "execution_count": executions,
                "completed_count": metric["completed_count"],
                "failed_count": metric["failed_count"],
                "waiting_approval_count": metric["waiting_approval_count"],
                "completed_node_count": metric["completed_node_count"],
                "event_count": metric["event_count"],
                "failure_categories": dict(sorted(metric["failure_categories"].items())),
                "completion_rate": round(metric["completed_count"] / executions, 4) if executions else None,
                "failure_rate": round(metric["failed_count"] / executions, 4) if executions else None,
                "human_review_rate": round(metric["waiting_approval_count"] / executions, 4) if executions else None,
                "average_completed_node_count": round(metric["completed_node_count"] / executions, 2)
                if executions
                else None,
            }
        )
    return {
        "source": "aws_dynamodb_execution_store",
        "execution_count": len(rows),
        "graphs": graphs,
    }


def apply_dynamo_executions_to_snapshot(snapshot: dict[str, Any], aggregate: dict[str, Any]) -> dict[str, Any]:
    result = dict(snapshot)
    existing = {row["graph_id"]: row for row in result.get("graphs", [])}
    for graph in aggregate.get("graphs", []):
        graph_id = graph["graph_id"]
        if graph_id in existing:
            raise RuntimeError(f"duplicate runtime execution coverage for graph: {graph_id}")
        existing[graph_id] = graph
    result["graphs"] = [existing[key] for key in sorted(existing)]

    coverage = [
        row
        for row in result.get("source_coverage", [])
        if row.get("store_kind") != "generic_graph"
    ]
    coverage.append(
        {
            "store_kind": "aws_generic_graph",
            "path_present": True,
            "execution_count": int(aggregate.get("execution_count") or 0),
            "source": "dynamodb",
        }
    )
    result["source_coverage"] = coverage
    result["execution_state_source"] = "aws_dynamodb"
    return result
