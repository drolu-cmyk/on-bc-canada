"""AWS production observability for privacy-safe model runtime telemetry.

The centralized record is one trace summary per governed model run. It contains
operational metadata and numeric usage/latency facts only. Prompts, model output,
tool arguments, tool output, learner content, direct execution IDs, and secrets
are never added to the CloudWatch event.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


AWS_OBSERVABILITY_ENABLED_ENV = "SOZOROCK_AWS_OBSERVABILITY_ENABLED"
AWS_OBSERVABILITY_REGION_ENV = "SOZOROCK_AWS_OBSERVABILITY_REGION"
AWS_TELEMETRY_LOG_GROUP_ENV = "SOZOROCK_AWS_TELEMETRY_LOG_GROUP"
AWS_TELEMETRY_LOG_STREAM_ENV = "SOZOROCK_AWS_TELEMETRY_LOG_STREAM"
AWS_OBSERVABILITY_ENVIRONMENT_ENV = "SOZOROCK_AWS_OBSERVABILITY_ENVIRONMENT"
AWS_ASSURANCE_LOOKBACK_MINUTES_ENV = "SOZOROCK_AWS_ASSURANCE_LOOKBACK_MINUTES"

DEFAULT_REGION = "ca-central-1"
DEFAULT_LOG_GROUP = "/sozorock/canada/runtime/model-telemetry"
DEFAULT_LOG_STREAM = "model-runtime"
DEFAULT_ENVIRONMENT = "pilot"
DEFAULT_LOOKBACK_MINUTES = 1440
METRIC_NAMESPACE = "SozoRock/CanadaPlatform"
TELEMETRY_CLASS = "privacy_safe_model_runtime"
SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class AwsObservabilityConfig:
    region: str = DEFAULT_REGION
    log_group: str = DEFAULT_LOG_GROUP
    log_stream: str = DEFAULT_LOG_STREAM
    environment: str = DEFAULT_ENVIRONMENT
    lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES

    @classmethod
    def from_environment(cls) -> "AwsObservabilityConfig":
        raw_lookback = os.getenv(AWS_ASSURANCE_LOOKBACK_MINUTES_ENV, str(DEFAULT_LOOKBACK_MINUTES)).strip()
        try:
            lookback = int(raw_lookback)
        except ValueError as exc:
            raise RuntimeError(f"{AWS_ASSURANCE_LOOKBACK_MINUTES_ENV} must be an integer") from exc
        if lookback < 5 or lookback > 43200:
            raise RuntimeError(f"{AWS_ASSURANCE_LOOKBACK_MINUTES_ENV} must be between 5 and 43200")
        environment = os.getenv(AWS_OBSERVABILITY_ENVIRONMENT_ENV, DEFAULT_ENVIRONMENT).strip()
        if not environment:
            raise RuntimeError(f"{AWS_OBSERVABILITY_ENVIRONMENT_ENV} cannot be empty")
        return cls(
            region=os.getenv(AWS_OBSERVABILITY_REGION_ENV, DEFAULT_REGION).strip() or DEFAULT_REGION,
            log_group=os.getenv(AWS_TELEMETRY_LOG_GROUP_ENV, DEFAULT_LOG_GROUP).strip() or DEFAULT_LOG_GROUP,
            log_stream=os.getenv(AWS_TELEMETRY_LOG_STREAM_ENV, DEFAULT_LOG_STREAM).strip() or DEFAULT_LOG_STREAM,
            environment=environment,
            lookback_minutes=lookback,
        )


def aws_observability_enabled() -> bool:
    return os.getenv(AWS_OBSERVABILITY_ENABLED_ENV, "").strip().casefold() in {"1", "true", "yes", "on"}


def _read_trace_summary(store_path: str | Path, trace_id: str) -> dict[str, Any] | None:
    path = Path(store_path)
    if not path.exists():
        return None
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT
                t.trace_id,
                t.identity_id,
                t.actor_id,
                t.sdk_name,
                t.work_type,
                t.graph_id,
                t.graph_version,
                t.execution_fingerprint,
                t.node_id,
                t.ended_at,
                t.latency_ms AS run_latency_ms,
                t.span_count,
                t.generation_count,
                t.tool_span_count,
                COALESCE(SUM(CASE WHEN s.span_type = 'generation' THEN s.requests ELSE 0 END), 0) AS request_count,
                COALESCE(SUM(CASE WHEN s.span_type = 'generation' THEN s.input_tokens ELSE 0 END), 0) AS input_tokens,
                COALESCE(SUM(CASE WHEN s.span_type = 'generation' THEN s.output_tokens ELSE 0 END), 0) AS output_tokens,
                COALESCE(SUM(CASE WHEN s.span_type = 'generation' THEN s.total_tokens ELSE 0 END), 0) AS total_tokens,
                COALESCE(SUM(CASE WHEN s.span_type = 'generation' THEN s.cached_input_tokens ELSE 0 END), 0) AS cached_input_tokens,
                COALESCE(SUM(CASE WHEN s.span_type = 'generation' THEN s.reasoning_tokens ELSE 0 END), 0) AS reasoning_tokens,
                COALESCE(SUM(CASE WHEN s.error_present = 1 THEN 1 ELSE 0 END), 0) AS error_span_count,
                COALESCE(SUM(CASE WHEN s.span_type = 'generation' AND s.pricing_status = 'estimated' THEN 1 ELSE 0 END), 0) AS priced_generation_count,
                SUM(CASE WHEN s.span_type = 'generation' THEN s.estimated_cost_usd END) AS estimated_cost_usd,
                SUM(CASE WHEN s.span_type = 'generation' THEN s.latency_ms END) AS generation_latency_total_ms,
                AVG(CASE WHEN s.span_type = 'generation' THEN s.latency_ms END) AS generation_latency_ms,
                SUM(CASE WHEN s.span_type IN ('function', 'mcp_tools') THEN s.latency_ms END) AS local_tool_latency_total_ms,
                AVG(CASE WHEN s.span_type IN ('function', 'mcp_tools') THEN s.latency_ms END) AS local_tool_latency_ms
            FROM model_traces t
            LEFT JOIN model_spans s ON s.trace_id = t.trace_id
            WHERE t.trace_id = ?
            GROUP BY t.trace_id
            """,
            (trace_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def _epoch_ms(value: str | None) -> int:
    if value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return int(parsed.timestamp() * 1000)
        except ValueError:
            pass
    return int(time.time() * 1000)


def _metric(name: str, unit: str) -> dict[str, str]:
    return {"Name": name, "Unit": unit}


def build_cloudwatch_emf_event(summary: dict[str, Any], config: AwsObservabilityConfig) -> dict[str, Any]:
    """Build a strict allow-list CloudWatch EMF event from one local trace summary."""

    generation_count = int(summary.get("generation_count") or 0)
    priced_generation_count = int(summary.get("priced_generation_count") or 0)
    estimated_cost = summary.get("estimated_cost_usd")
    pricing_complete = generation_count > 0 and priced_generation_count == generation_count and estimated_cost is not None
    timestamp_ms = _epoch_ms(summary.get("ended_at"))

    metrics = [
        _metric("ModelRunCount", "Count"),
        _metric("RequestCount", "Count"),
        _metric("InputTokens", "Count"),
        _metric("OutputTokens", "Count"),
        _metric("TotalTokens", "Count"),
        _metric("CachedInputTokens", "Count"),
        _metric("ReasoningTokens", "Count"),
        _metric("ModelErrorCount", "Count"),
        _metric("RunLatencyMs", "Milliseconds"),
    ]
    if summary.get("generation_latency_ms") is not None:
        metrics.append(_metric("GenerationLatencyMs", "Milliseconds"))
    if summary.get("local_tool_latency_ms") is not None:
        metrics.append(_metric("LocalToolLatencyMs", "Milliseconds"))
    if pricing_complete:
        metrics.append(_metric("EstimatedModelCostUSD", "None"))

    event: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "telemetry_class": TELEMETRY_CLASS,
        "trace_id": str(summary["trace_id"]),
        "identity_id": str(summary["identity_id"]),
        "actor_id": str(summary["actor_id"]),
        "sdk_name": str(summary["sdk_name"]),
        "work_type": str(summary["work_type"]),
        "graph_id": summary.get("graph_id"),
        "graph_version": summary.get("graph_version"),
        "execution_fingerprint": summary.get("execution_fingerprint"),
        "node_id": summary.get("node_id"),
        "pricing_status": "estimated" if pricing_complete else "unavailable",
        "span_count": int(summary.get("span_count") or 0),
        "generation_count": generation_count,
        "tool_span_count": int(summary.get("tool_span_count") or 0),
        "priced_generation_count": priced_generation_count,
        "generation_latency_total_ms": round(float(summary.get("generation_latency_total_ms") or 0.0), 3),
        "local_tool_latency_total_ms": round(float(summary.get("local_tool_latency_total_ms") or 0.0), 3),
        "Environment": config.environment,
        "ModelRunCount": 1,
        "RequestCount": int(summary.get("request_count") or 0),
        "InputTokens": int(summary.get("input_tokens") or 0),
        "OutputTokens": int(summary.get("output_tokens") or 0),
        "TotalTokens": int(summary.get("total_tokens") or 0),
        "CachedInputTokens": int(summary.get("cached_input_tokens") or 0),
        "ReasoningTokens": int(summary.get("reasoning_tokens") or 0),
        "ModelErrorCount": 1 if int(summary.get("error_span_count") or 0) > 0 else 0,
        "RunLatencyMs": round(float(summary.get("run_latency_ms") or 0.0), 3),
        "_aws": {
            "Timestamp": timestamp_ms,
            "CloudWatchMetrics": [
                {
                    "Namespace": METRIC_NAMESPACE,
                    "Dimensions": [["Environment"]],
                    "Metrics": metrics,
                }
            ],
        },
    }
    if summary.get("generation_latency_ms") is not None:
        event["GenerationLatencyMs"] = round(float(summary["generation_latency_ms"]), 3)
    if summary.get("local_tool_latency_ms") is not None:
        event["LocalToolLatencyMs"] = round(float(summary["local_tool_latency_ms"]), 3)
    if pricing_complete:
        event["EstimatedModelCostUSD"] = round(float(estimated_cost), 8)

    validate_cloudwatch_event(event)
    return event


_ALLOWED_EVENT_KEYS = {
    "schema_version", "telemetry_class", "trace_id", "identity_id", "actor_id", "sdk_name",
    "work_type", "graph_id", "graph_version", "execution_fingerprint", "node_id", "pricing_status",
    "span_count", "generation_count", "tool_span_count", "priced_generation_count",
    "generation_latency_total_ms", "local_tool_latency_total_ms", "Environment", "ModelRunCount",
    "RequestCount", "InputTokens", "OutputTokens", "TotalTokens", "CachedInputTokens",
    "ReasoningTokens", "ModelErrorCount", "RunLatencyMs", "GenerationLatencyMs",
    "LocalToolLatencyMs", "EstimatedModelCostUSD", "_aws",
}


def validate_cloudwatch_event(event: dict[str, Any]) -> None:
    unexpected = set(event) - _ALLOWED_EVENT_KEYS
    if unexpected:
        raise ValueError(f"CloudWatch telemetry contains unapproved fields: {', '.join(sorted(unexpected))}")
    encoded_keys = " ".join(str(key).casefold() for key in event)
    for token in ("prompt", "model_output", "tool_argument", "tool_output", "learner", "credential", "secret"):
        if token in encoded_keys:
            raise ValueError(f"CloudWatch telemetry field violates privacy boundary: {token}")


class CloudWatchTelemetryPublisher:
    def __init__(
        self,
        *,
        store_path: str | Path,
        config: AwsObservabilityConfig | None = None,
        client: Any | None = None,
    ) -> None:
        self.store_path = Path(store_path)
        self.config = config or AwsObservabilityConfig.from_environment()
        if client is None:
            import boto3

            client = boto3.client("logs", region_name=self.config.region)
        self.client = client

    @classmethod
    def from_environment(cls, *, store_path: str | Path) -> "CloudWatchTelemetryPublisher | None":
        if not aws_observability_enabled():
            return None
        return cls(store_path=store_path)

    def publish_trace(self, trace_id: str) -> dict[str, Any] | None:
        summary = _read_trace_summary(self.store_path, trace_id)
        if summary is None:
            return None
        event = build_cloudwatch_emf_event(summary, self.config)
        timestamp_ms = int(event["_aws"]["Timestamp"])
        self.client.put_log_events(
            logGroupName=self.config.log_group,
            logStreamName=self.config.log_stream,
            logEvents=[{"timestamp": timestamp_ms, "message": json.dumps(event, separators=(",", ":"), sort_keys=True)}],
        )
        return event


_QUERY = """
fields trace_id, work_type, span_count, generation_count, tool_span_count, priced_generation_count,
       generation_latency_total_ms, local_tool_latency_total_ms, ModelRunCount, RequestCount,
       InputTokens, OutputTokens, TotalTokens, CachedInputTokens, ReasoningTokens, ModelErrorCount,
       RunLatencyMs, GenerationLatencyMs, LocalToolLatencyMs, EstimatedModelCostUSD, pricing_status
| filter telemetry_class = \"privacy_safe_model_runtime\"
| sort @timestamp desc
| dedup trace_id
| limit 10000
""".strip()


class CloudWatchRuntimeTelemetrySource:
    """Read privacy-safe trace summaries back through CloudWatch Logs Insights."""

    def __init__(
        self,
        config: AwsObservabilityConfig | None = None,
        *,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config or AwsObservabilityConfig.from_environment()
        if client is None:
            import boto3

            client = boto3.client("logs", region_name=self.config.region)
        self.client = client
        self.sleep = sleep

    def read(self, *, now_epoch: int | None = None, max_poll_attempts: int = 40) -> dict[str, Any]:
        end_time = int(now_epoch if now_epoch is not None else time.time())
        start_time = end_time - (self.config.lookback_minutes * 60)
        response = self.client.start_query(
            logGroupName=self.config.log_group,
            startTime=start_time,
            endTime=end_time,
            queryString=_QUERY,
            limit=10000,
        )
        query_id = response.get("queryId")
        if not query_id:
            raise RuntimeError("CloudWatch Logs Insights did not return a query ID")

        for _ in range(max_poll_attempts):
            result = self.client.get_query_results(queryId=query_id)
            status = result.get("status")
            if status == "Complete":
                rows = [_query_row(item) for item in result.get("results", [])]
                return aggregate_cloudwatch_runtime(rows, lookback_minutes=self.config.lookback_minutes)
            if status in {"Failed", "Cancelled", "Timeout", "Unknown"}:
                raise RuntimeError(f"CloudWatch Logs Insights query ended with status {status}")
            self.sleep(0.25)
        try:
            self.client.stop_query(queryId=query_id)
        except Exception:
            pass
        raise TimeoutError("CloudWatch Logs Insights query did not complete within the poll budget")


def _query_row(items: list[dict[str, str]]) -> dict[str, str]:
    return {str(item.get("field")): str(item.get("value", "")) for item in items if item.get("field") and item.get("field") != "@ptr"}


def _number(row: dict[str, str], key: str, *, integer: bool = False) -> int | float:
    value = row.get(key, "").strip()
    if not value:
        return 0 if integer else 0.0
    try:
        return int(float(value)) if integer else float(value)
    except ValueError:
        return 0 if integer else 0.0


def aggregate_cloudwatch_runtime(rows: list[dict[str, str]], *, lookback_minutes: int) -> dict[str, Any]:
    deduped: dict[str, dict[str, str]] = {}
    for row in rows:
        trace_id = row.get("trace_id", "").strip()
        if trace_id:
            deduped.setdefault(trace_id, row)

    totals = {
        "trace_count": len(deduped),
        "span_count": 0,
        "generation_count": 0,
        "tool_span_count": 0,
        "priced_generation_count": 0,
        "request_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cached_input_tokens": 0,
        "reasoning_tokens": 0,
        "model_error_count": 0,
        "estimated_cost_usd": 0.0,
        "run_latency_total_ms": 0.0,
        "run_latency_count": 0,
        "generation_latency_total_ms": 0.0,
        "local_tool_latency_total_ms": 0.0,
    }
    work: dict[str, dict[str, Any]] = {}

    for row in deduped.values():
        work_type = row.get("work_type", "unknown") or "unknown"
        bucket = work.setdefault(
            work_type,
            {
                "work_type": work_type,
                "model_run_count": 0,
                "generation_count": 0,
                "request_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cached_input_tokens": 0,
                "reasoning_tokens": 0,
                "model_error_count": 0,
                "estimated_cost_usd": 0.0,
                "run_latency_total_ms": 0.0,
                "run_latency_count": 0,
                "generation_latency_total_ms": 0.0,
            },
        )
        generation_count = int(_number(row, "generation_count", integer=True))
        tool_span_count = int(_number(row, "tool_span_count", integer=True))
        priced_count = int(_number(row, "priced_generation_count", integer=True))
        run_latency = float(_number(row, "RunLatencyMs"))
        generation_latency_total = float(_number(row, "generation_latency_total_ms"))
        local_tool_latency_total = float(_number(row, "local_tool_latency_total_ms"))
        cost = float(_number(row, "EstimatedModelCostUSD"))

        numeric_ints = {
            "span_count": int(_number(row, "span_count", integer=True)),
            "generation_count": generation_count,
            "tool_span_count": tool_span_count,
            "priced_generation_count": priced_count,
            "request_count": int(_number(row, "RequestCount", integer=True)),
            "input_tokens": int(_number(row, "InputTokens", integer=True)),
            "output_tokens": int(_number(row, "OutputTokens", integer=True)),
            "total_tokens": int(_number(row, "TotalTokens", integer=True)),
            "cached_input_tokens": int(_number(row, "CachedInputTokens", integer=True)),
            "reasoning_tokens": int(_number(row, "ReasoningTokens", integer=True)),
            "model_error_count": int(_number(row, "ModelErrorCount", integer=True)),
        }
        for key, value in numeric_ints.items():
            totals[key] += value
        totals["estimated_cost_usd"] += cost
        totals["generation_latency_total_ms"] += generation_latency_total
        totals["local_tool_latency_total_ms"] += local_tool_latency_total
        if run_latency > 0:
            totals["run_latency_total_ms"] += run_latency
            totals["run_latency_count"] += 1

        bucket["model_run_count"] += 1
        for key in (
            "generation_count", "request_count", "input_tokens", "output_tokens", "total_tokens",
            "cached_input_tokens", "reasoning_tokens", "model_error_count",
        ):
            bucket[key] += numeric_ints[key]
        bucket["estimated_cost_usd"] += cost
        bucket["generation_latency_total_ms"] += generation_latency_total
        if run_latency > 0:
            bucket["run_latency_total_ms"] += run_latency
            bucket["run_latency_count"] += 1

    workflows: list[dict[str, Any]] = []
    for work_type in sorted(work):
        item = work[work_type]
        run_count = item.pop("run_latency_count")
        run_total = item.pop("run_latency_total_ms")
        generation_total = item.pop("generation_latency_total_ms")
        generations = item["generation_count"]
        item["estimated_cost_usd"] = round(float(item["estimated_cost_usd"]), 8)
        item["average_run_latency_ms"] = round(run_total / run_count, 3) if run_count else None
        item["average_generation_latency_ms"] = round(generation_total / generations, 3) if generations else None
        workflows.append(item)

    trace_count = int(totals["trace_count"])
    generation_count = int(totals["generation_count"])
    tool_span_count = int(totals["tool_span_count"])
    run_count = int(totals.pop("run_latency_count"))
    run_total = float(totals.pop("run_latency_total_ms"))
    generation_total = float(totals.pop("generation_latency_total_ms"))
    local_tool_total = float(totals.pop("local_tool_latency_total_ms"))
    totals["estimated_cost_usd"] = round(float(totals["estimated_cost_usd"]), 8)

    return {
        "path_present": True,
        "source": "aws_cloudwatch_logs_insights",
        "lookback_minutes": lookback_minutes,
        **totals,
        "average_run_latency_ms": round(run_total / run_count, 3) if run_count else None,
        "average_generation_latency_ms": round(generation_total / generation_count, 3) if generation_count else None,
        "average_tool_latency_ms": round(local_tool_total / tool_span_count, 3) if tool_span_count else None,
        "workflows": workflows,
        "trace_linkage": "trace_id retained in encrypted CloudWatch Logs; direct execution IDs excluded",
        "pricing": "estimated cost exists only for traces whose local pricing inputs were reviewed and complete",
    }


def apply_cloudwatch_runtime_to_snapshot(snapshot: dict[str, Any], model_runtime: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(snapshot))
    result["model_runtime"] = model_runtime
    trace_count = int(model_runtime.get("trace_count") or 0)
    generation_count = int(model_runtime.get("generation_count") or 0)
    priced_generation_count = int(model_runtime.get("priced_generation_count") or 0)
    tool_span_count = int(model_runtime.get("tool_span_count") or 0)
    coverage = result.setdefault("telemetry_coverage", {})
    coverage["model_token_usage"] = trace_count > 0 and generation_count > 0
    coverage["model_monetary_cost"] = generation_count > 0 and priced_generation_count == generation_count
    coverage["provider_latency"] = trace_count > 0
    coverage["tool_call_latency"] = tool_span_count > 0
    coverage["trace_sampling"] = trace_count > 0
    coverage["hosted_tool_latency"] = False
    result.setdefault("source_coverage", []).append(
        {
            "store_kind": "aws_cloudwatch_model_telemetry",
            "path_present": True,
            "trace_count": trace_count,
            "lookback_minutes": model_runtime.get("lookback_minutes"),
        }
    )
    return result
