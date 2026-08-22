from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.model_runtime_telemetry import (
    MODEL_PRICING_ENV,
    ModelTelemetryStore,
    PrivacySafeTelemetryProcessor,
    model_runtime_context,
)
from runtime.runtime_assurance import RuntimeAssuranceSnapshotBuilder


class FakeTrace:
    def __init__(self, trace_id: str) -> None:
        self.trace_id = trace_id


class FakeSpanData:
    def __init__(self, span_type: str, *, name=None, model=None, usage=None) -> None:
        self.type = span_type
        self.name = name
        self.model = model
        self.usage = usage


class FakeSpan:
    def __init__(
        self,
        *,
        trace_id: str,
        span_id: str,
        data: FakeSpanData,
        started_at: str,
        ended_at: str,
        error=None,
    ) -> None:
        self.trace_id = trace_id
        self.span_id = span_id
        self.span_data = data
        self.started_at = started_at
        self.ended_at = ended_at
        self.error = error


class ModelRuntimeTelemetryTests(unittest.TestCase):
    def test_generation_usage_is_correlated_without_payload_storage(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ",
            {
                MODEL_PRICING_ENV: (
                    '{"gpt-5.6-sol":{"input_per_million":2.0,'
                    '"cached_input_per_million":0.5,"output_per_million":8.0}}'
                )
            },
            clear=False,
        ):
            path = Path(directory) / "telemetry.sqlite3"
            processor = PrivacySafeTelemetryProcessor(ModelTelemetryStore(path))
            trace = FakeTrace("trace_1234567890abcdef1234567890abcdef")
            with model_runtime_context(
                actor_id="product-agent",
                execution_id="product-execution-001",
                graph_id="product-development",
                graph_version="0.1.0",
                node_id="analyse_product",
            ):
                processor.on_trace_start(trace)
            processor.on_span_end(
                FakeSpan(
                    trace_id=trace.trace_id,
                    span_id="span_generation_001",
                    data=FakeSpanData(
                        "generation",
                        model="gpt-5.6-sol",
                        usage={
                            "requests": 1,
                            "input_tokens": 1000,
                            "output_tokens": 200,
                            "total_tokens": 1200,
                            "input_tokens_details": {"cached_tokens": 250},
                            "output_tokens_details": {"reasoning_tokens": 75},
                        },
                    ),
                    started_at="2026-08-22T19:00:00Z",
                    ended_at="2026-08-22T19:00:01Z",
                )
            )
            processor.on_trace_end(trace)

            with sqlite3.connect(path) as connection:
                connection.row_factory = sqlite3.Row
                trace_row = connection.execute("SELECT * FROM model_traces").fetchone()
                span_row = connection.execute("SELECT * FROM model_spans").fetchone()
                trace_columns = {row[1] for row in connection.execute("PRAGMA table_info(model_traces)")}
                span_columns = {row[1] for row in connection.execute("PRAGMA table_info(model_spans)")}

            self.assertEqual("nhi:canada-platform:product-agent", trace_row["identity_id"])
            self.assertEqual("product-execution-001", trace_row["execution_id"])
            self.assertEqual("analyse_product", trace_row["node_id"])
            self.assertEqual(1000, span_row["input_tokens"])
            self.assertEqual(250, span_row["cached_input_tokens"])
            self.assertEqual(75, span_row["reasoning_tokens"])
            self.assertEqual(1000.0, span_row["latency_ms"])
            self.assertEqual("estimated", span_row["pricing_status"])
            self.assertAlmostEqual(0.003225, span_row["estimated_cost_usd"], places=8)
            forbidden_tokens = ("prompt", "output_body", "input_body", "tool_argument", "tool_output", "credential")
            for column in trace_columns | span_columns:
                self.assertFalse(any(token in column for token in forbidden_tokens), column)

    def test_runtime_assurance_uses_generation_usage_once_and_reads_local_tool_latency(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.sqlite3"
            processor = PrivacySafeTelemetryProcessor(ModelTelemetryStore(path))
            trace = FakeTrace("trace_abcdef1234567890abcdef1234567890")
            with model_runtime_context(actor_id="runtime-reliability-agent", execution_id="assurance-001"):
                processor.on_trace_start(trace)
            processor.on_span_end(
                FakeSpan(
                    trace_id=trace.trace_id,
                    span_id="span_generation_002",
                    data=FakeSpanData(
                        "generation",
                        model="gpt-5.6-sol",
                        usage={"input_tokens": 300, "output_tokens": 50, "total_tokens": 350},
                    ),
                    started_at="2026-08-22T19:00:00Z",
                    ended_at="2026-08-22T19:00:00.500000Z",
                )
            )
            # Task spans may contain aggregate usage for the same run. It must not
            # be counted again by the telemetry accounting layer.
            processor.on_span_end(
                FakeSpan(
                    trace_id=trace.trace_id,
                    span_id="span_task_001",
                    data=FakeSpanData(
                        "task",
                        name="Agent workflow",
                        usage={"requests": 1, "input_tokens": 300, "output_tokens": 50, "total_tokens": 350},
                    ),
                    started_at="2026-08-22T19:00:00Z",
                    ended_at="2026-08-22T19:00:00.800000Z",
                )
            )
            processor.on_span_end(
                FakeSpan(
                    trace_id=trace.trace_id,
                    span_id="span_function_001",
                    data=FakeSpanData("function", name="bounded_lookup"),
                    started_at="2026-08-22T19:00:00.500000Z",
                    ended_at="2026-08-22T19:00:00.700000Z",
                )
            )
            processor.on_trace_end(trace)

            snapshot = RuntimeAssuranceSnapshotBuilder((), model_telemetry_path=path).build()
            runtime = snapshot["model_runtime"]
            self.assertEqual(1, runtime["trace_count"])
            self.assertEqual(3, runtime["span_count"])
            self.assertEqual(1, runtime["generation_count"])
            self.assertEqual(1, runtime["tool_span_count"])
            self.assertEqual(1, runtime["request_count"])
            self.assertEqual(350, runtime["total_tokens"])
            self.assertEqual(500.0, runtime["average_generation_latency_ms"])
            self.assertEqual(200.0, runtime["average_tool_latency_ms"])
            self.assertTrue(snapshot["telemetry_coverage"]["model_token_usage"])
            self.assertTrue(snapshot["telemetry_coverage"]["provider_latency"])
            self.assertTrue(snapshot["telemetry_coverage"]["tool_call_latency"])
            self.assertTrue(snapshot["telemetry_coverage"]["trace_sampling"])
            self.assertFalse(snapshot["telemetry_coverage"]["model_monetary_cost"])
            self.assertFalse(snapshot["telemetry_coverage"]["hosted_tool_latency"])

    def test_average_run_latency_is_per_trace_not_weighted_by_span_count(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.sqlite3"
            store = ModelTelemetryStore(path)
            with sqlite3.connect(path) as connection:
                connection.executemany(
                    """
                    INSERT INTO model_traces (
                        trace_id, identity_id, actor_id, sdk_name, work_type,
                        graph_id, graph_version, execution_id, execution_fingerprint,
                        node_id, started_at, ended_at, latency_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        ("trace-one", "nhi:one", "one", "One", "fixture", None, None, "one", "f1", None, "s", "e", 100.0),
                        ("trace-two", "nhi:two", "two", "Two", "fixture", None, None, "two", "f2", None, "s", "e", 300.0),
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO model_spans (
                        span_id, trace_id, span_type, pricing_status
                    ) VALUES (?, ?, ?, ?)
                    """,
                    [
                        ("one-generation", "trace-one", "generation", "unconfigured"),
                        ("two-generation", "trace-two", "generation", "unconfigured"),
                        ("two-task", "trace-two", "task", "not_applicable"),
                        ("two-agent", "trace-two", "agent", "not_applicable"),
                    ],
                )
            snapshot = RuntimeAssuranceSnapshotBuilder((), model_telemetry_path=path).build()
            self.assertEqual(200.0, snapshot["model_runtime"]["average_run_latency_ms"])
            self.assertEqual(200.0, snapshot["model_runtime"]["workflows"][0]["average_run_latency_ms"])


if __name__ == "__main__":
    unittest.main()
