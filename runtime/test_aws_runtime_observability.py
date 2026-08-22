from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from runtime.aws_runtime_observability import (
    AWS_ASSURANCE_LOOKBACK_MINUTES_ENV,
    AWS_OBSERVABILITY_ENABLED_ENV,
    AwsObservabilityConfig,
    CloudWatchRuntimeTelemetrySource,
    CloudWatchTelemetryPublisher,
    aggregate_cloudwatch_runtime,
    apply_cloudwatch_runtime_to_snapshot,
    aws_observability_enabled,
)
from runtime.model_runtime_telemetry import ModelTelemetryStore, PrivacySafeTelemetryProcessor, model_runtime_context


class FakeLogsPublisherClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def put_log_events(self, **kwargs):
        self.calls.append(kwargs)
        return {"rejectedLogEventsInfo": {}}


class FakeLogsQueryClient:
    def __init__(self, results) -> None:
        self.results = results
        self.start_calls: list[dict[str, object]] = []
        self.poll_count = 0
        self.stopped: list[str] = []

    def start_query(self, **kwargs):
        self.start_calls.append(kwargs)
        return {"queryId": "query-001"}

    def get_query_results(self, *, queryId):
        self.poll_count += 1
        if self.poll_count == 1:
            return {"status": "Running", "results": []}
        return {"status": "Complete", "results": self.results}

    def stop_query(self, *, queryId):
        self.stopped.append(queryId)
        return {"success": True}


def query_result(**values):
    return [{"field": key, "value": str(value)} for key, value in values.items()]


def nested_keys(value) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key).casefold())
            keys.update(nested_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(nested_keys(item))
    return keys


class RaisingPublisher:
    def publish_trace(self, trace_id: str):
        raise RuntimeError("simulated CloudWatch outage")


class AwsRuntimeObservabilityTests(unittest.TestCase):
    def _telemetry_db(self, directory: str) -> Path:
        path = Path(directory) / "model-telemetry.sqlite3"
        ModelTelemetryStore(path)
        with sqlite3.connect(path) as connection:
            connection.execute(
                """
                INSERT INTO model_traces (
                    trace_id, identity_id, actor_id, sdk_name, work_type, graph_id,
                    graph_version, execution_id, execution_fingerprint, node_id,
                    started_at, ended_at, latency_ms, span_count, generation_count, tool_span_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "trace-001",
                    "nhi:canada-platform:product-agent",
                    "product-agent",
                    "Product Agent",
                    "product_development",
                    "product-development",
                    "0.1.0",
                    "direct-execution-id-must-not-leave-local-store",
                    "execution-fingerprint-001",
                    "analyse_product",
                    "2026-08-22T20:00:00Z",
                    "2026-08-22T20:00:02Z",
                    2000.0,
                    2,
                    1,
                    1,
                ),
            )
            connection.executemany(
                """
                INSERT INTO model_spans (
                    span_id, trace_id, span_type, span_name, model, started_at, ended_at,
                    latency_ms, requests, input_tokens, output_tokens, total_tokens,
                    cached_input_tokens, reasoning_tokens, input_rate_per_million,
                    cached_input_rate_per_million, output_rate_per_million,
                    estimated_cost_usd, pricing_status, error_present
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "span-generation-001", "trace-001", "generation", "model_generation", "gpt-5.6-sol",
                        "2026-08-22T20:00:00Z", "2026-08-22T20:00:01.500000Z", 1500.0,
                        1, 1000, 200, 1200, 250, 75, 2.0, 0.5, 8.0, 0.003475, "estimated", 0,
                    ),
                    (
                        "span-function-001", "trace-001", "function", "bounded_lookup", None,
                        "2026-08-22T20:00:01.500000Z", "2026-08-22T20:00:01.700000Z", 200.0,
                        0, 0, 0, 0, 0, 0, None, None, None, None, "not_applicable", 0,
                    ),
                ],
            )
        return path

    def test_publisher_exports_strict_emf_summary_without_direct_execution_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._telemetry_db(directory)
            client = FakeLogsPublisherClient()
            config = AwsObservabilityConfig(
                region="ca-central-1",
                log_group="/sozorock/canada/runtime/model-telemetry",
                log_stream="model-runtime",
                environment="pilot",
                lookback_minutes=1440,
            )
            event = CloudWatchTelemetryPublisher(store_path=path, config=config, client=client).publish_trace("trace-001")

        self.assertIsNotNone(event)
        self.assertEqual(1, len(client.calls))
        call = client.calls[0]
        self.assertEqual(config.log_group, call["logGroupName"])
        self.assertEqual(config.log_stream, call["logStreamName"])
        message = call["logEvents"][0]["message"]
        self.assertNotIn("direct-execution-id-must-not-leave-local-store", message)
        self.assertNotIn("prompt", message.casefold())
        self.assertNotIn("tool_output", message.casefold())
        payload = json.loads(message)
        self.assertEqual("execution-fingerprint-001", payload["execution_fingerprint"])
        self.assertEqual(1200, payload["TotalTokens"])
        self.assertEqual(1, payload["ModelRunCount"])
        self.assertEqual(200.0, payload["LocalToolLatencyMs"])
        self.assertEqual([["Environment"]], payload["_aws"]["CloudWatchMetrics"][0]["Dimensions"])
        metric_names = {item["Name"] for item in payload["_aws"]["CloudWatchMetrics"][0]["Metrics"]}
        self.assertIn("EstimatedModelCostUSD", metric_names)
        self.assertNotIn("work_type", payload["_aws"]["CloudWatchMetrics"][0]["Dimensions"][0])

    def test_cloudwatch_query_deduplicates_trace_id_and_aggregates_workflows(self):
        row_a = query_result(
            trace_id="trace-a", work_type="research_intelligence", span_count=2, generation_count=1,
            tool_span_count=0, priced_generation_count=1, generation_latency_total_ms=100,
            local_tool_latency_total_ms=0, ModelRunCount=1, RequestCount=1, InputTokens=100,
            OutputTokens=20, TotalTokens=120, CachedInputTokens=10, ReasoningTokens=5,
            ModelErrorCount=0, RunLatencyMs=150, EstimatedModelCostUSD=0.001,
        )
        row_a_duplicate = list(row_a)
        row_b = query_result(
            trace_id="trace-b", work_type="product_development", span_count=3, generation_count=2,
            tool_span_count=1, priced_generation_count=2, generation_latency_total_ms=500,
            local_tool_latency_total_ms=200, ModelRunCount=1, RequestCount=2, InputTokens=400,
            OutputTokens=100, TotalTokens=500, CachedInputTokens=50, ReasoningTokens=25,
            ModelErrorCount=1, RunLatencyMs=800, EstimatedModelCostUSD=0.005,
        )
        client = FakeLogsQueryClient([row_a, row_a_duplicate, row_b])
        source = CloudWatchRuntimeTelemetrySource(
            AwsObservabilityConfig(lookback_minutes=60),
            client=client,
            sleep=lambda seconds: None,
        )
        runtime = source.read(now_epoch=2_000_000_000)

        self.assertEqual(2, runtime["trace_count"])
        self.assertEqual(3, runtime["generation_count"])
        self.assertEqual(620, runtime["total_tokens"])
        self.assertEqual(1, runtime["model_error_count"])
        self.assertEqual(475.0, runtime["average_run_latency_ms"])
        self.assertEqual(round(600 / 3, 3), runtime["average_generation_latency_ms"])
        self.assertEqual(200.0, runtime["average_tool_latency_ms"])
        self.assertEqual(2, len(runtime["workflows"]))
        self.assertEqual(1, len(client.start_calls))
        query = client.start_calls[0]["queryString"]
        self.assertIn("dedup trace_id", query)
        self.assertEqual(60 * 60, client.start_calls[0]["endTime"] - client.start_calls[0]["startTime"])

    def test_apply_cloudwatch_runtime_updates_assurance_coverage_without_payload_fields(self):
        base = {
            "model_runtime": {"path_present": False},
            "source_coverage": [],
            "telemetry_coverage": {
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
        model_runtime = aggregate_cloudwatch_runtime(
            [
                {
                    "trace_id": "trace-x",
                    "work_type": "runtime_assurance",
                    "span_count": "1",
                    "generation_count": "1",
                    "tool_span_count": "0",
                    "priced_generation_count": "1",
                    "ModelRunCount": "1",
                    "RequestCount": "1",
                    "InputTokens": "100",
                    "OutputTokens": "20",
                    "TotalTokens": "120",
                    "CachedInputTokens": "10",
                    "ReasoningTokens": "5",
                    "ModelErrorCount": "0",
                    "RunLatencyMs": "250",
                    "generation_latency_total_ms": "200",
                    "local_tool_latency_total_ms": "0",
                    "EstimatedModelCostUSD": "0.001",
                }
            ],
            lookback_minutes=1440,
        )
        snapshot = apply_cloudwatch_runtime_to_snapshot(base, model_runtime)
        self.assertTrue(snapshot["telemetry_coverage"]["model_token_usage"])
        self.assertTrue(snapshot["telemetry_coverage"]["model_monetary_cost"])
        self.assertTrue(snapshot["telemetry_coverage"]["provider_latency"])
        self.assertFalse(snapshot["telemetry_coverage"]["hosted_tool_latency"])
        self.assertEqual("aws_cloudwatch_logs_insights", snapshot["model_runtime"]["source"])
        keys = nested_keys(snapshot)
        forbidden = {
            "prompt",
            "prompt_body",
            "model_output",
            "tool_argument",
            "tool_output",
            "learner_id",
            "submission_id",
            "credential",
            "secret",
        }
        self.assertTrue(forbidden.isdisjoint(keys), sorted(forbidden & keys))
        self.assertFalse(snapshot["model_boundary"]["contains_prompts_or_model_outputs"])
        self.assertFalse(snapshot["model_boundary"]["contains_tool_arguments_or_outputs"])

    def test_cloudwatch_failure_never_propagates_from_trace_processor(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ModelTelemetryStore(Path(directory) / "telemetry.sqlite3")
            processor = PrivacySafeTelemetryProcessor(store=store, aws_publisher=RaisingPublisher())
            trace = SimpleNamespace(trace_id="trace-failure-safe")
            with model_runtime_context(actor_id="product-agent", execution_id="product-001"):
                processor.on_trace_start(trace)
            processor.on_trace_end(trace)
            with sqlite3.connect(store.path) as connection:
                ended = connection.execute(
                    "SELECT ended_at FROM model_traces WHERE trace_id = ?", (trace.trace_id,)
                ).fetchone()[0]
        self.assertIsNotNone(ended)

    def test_configuration_is_explicit_and_bounded(self):
        with patch.dict(os.environ, {AWS_OBSERVABILITY_ENABLED_ENV: "true", AWS_ASSURANCE_LOOKBACK_MINUTES_ENV: "60"}, clear=True):
            self.assertTrue(aws_observability_enabled())
            config = AwsObservabilityConfig.from_environment()
            self.assertEqual("ca-central-1", config.region)
            self.assertEqual(60, config.lookback_minutes)
        with patch.dict(os.environ, {AWS_ASSURANCE_LOOKBACK_MINUTES_ENV: "1"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "between 5 and 43200"):
                AwsObservabilityConfig.from_environment()


if __name__ == "__main__":
    unittest.main()
