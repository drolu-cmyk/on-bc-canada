# Runtime Assurance

Runtime Assurance turns durable execution records and privacy-bounded model telemetry into evidence about whether the autonomous platform is operating reliably and inside its control model.

It is an assurance workflow, not a self-healing superuser. The graph can identify concerns and recommend accountable investigation. It cannot disable an agent, change authority or tools, change runtime policy, deploy code, mutate infrastructure, or alter production.

## Evidence boundary

The workflow reads aggregate fields from the durable execution stores plus one bounded model-runtime source.

Execution evidence can include:

- generic GraphExecutionStore records
- ResearchStore execution records

Model-runtime evidence can come from either:

- local privacy-safe telemetry SQLite
- centralized KMS-encrypted CloudWatch trace summaries

The deterministic snapshot contains operational evidence such as:

- graph ID and observed versions
- execution count
- completed, failed, and waiting-for-approval counts
- completed-node counts
- event counts
- coarse failure categories
- current emergency-disable configuration counts
- model trace and generation counts
- model request count
- input, output, total, cached-input, and reasoning token counts
- aggregate model-run and generation latency
- local function or MCP tool-span latency when those spans exist
- optional estimated model cost when reviewed pricing is configured

It does not pass raw graph state, checkpoints, prompts, model outputs, tool arguments, tool outputs, credentials, learner identity, or raw approval records to the Runtime Assurance agents.

## Model runtime telemetry

`runtime/model_runtime_telemetry.py` installs a secondary OpenAI Agents SDK tracing processor before governed live model work.

GraphKernel supplies execution context through a context variable so telemetry can be correlated to:

```text
graph
execution
node
actor
non-human identity
SDK trace
```

Learning Graph Design and the Platform Orchestrator sit outside GraphKernel, so their SDK calls set the same bounded context directly.

The telemetry processor records operational facts only. It does not copy SDK trace bodies into the local store. The runtime also sets:

```text
OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA=0
OPENAI_AGENTS_DONT_LOG_MODEL_DATA=1
OPENAI_AGENTS_DONT_LOG_TOOL_DATA=1
```

before governed live model work.

The default local reference database is:

```text
local-data/model-telemetry.sqlite3
```

## AWS production source

`runtime/aws_runtime_observability.py` supplies the centralized production path.

One strict trace summary is written to the KMS-encrypted CloudWatch log group after a governed model trace completes. The direct execution ID remains local; the centralized record contains only its one-way fingerprint.

Runtime Assurance reads CloudWatch through Logs Insights, requests only approved trace-summary fields, sorts newest first, deduplicates by trace ID, and performs final aggregation in deterministic Python code.

Select centralized telemetry with:

```bash
python -m runtime.run_runtime_assurance \
  --telemetry-source aws \
  start
```

The default query window is 1,440 minutes and can be changed with:

```text
SOZOROCK_AWS_ASSURANCE_LOOKBACK_MINUTES
```

AWS source details, IAM controls, retention and deployment authority are documented in [AWS Runtime Observability](aws-runtime-observability.md).

## Telemetry coverage

When model telemetry exists, Runtime Assurance can measure:

```text
trace linkage
model run count
model generation count
model request count
input tokens
output tokens
total tokens
cached input tokens
reasoning tokens
model-run latency
generation latency
local function/MCP tool-span latency
```

Coverage remains explicit. A missing local database, missing centralized log group, empty result window, or unavailable query does not become evidence of healthy operation.

Provider-hosted tool latency is still reported as unavailable separately. The current Research workers use OpenAI-hosted web search, and this implementation does not infer a standalone web-search duration when the SDK does not expose one as a local tool span.

## Cost boundary

No model price is hardcoded into runtime logic.

Estimated model cost is enabled only when `SOZOROCK_MODEL_PRICING_JSON` contains a reviewed rate table. The expected shape is:

```json
{
  "model-name": {
    "input_per_million": 0,
    "cached_input_per_million": 0,
    "output_per_million": 0
  }
}
```

The zeros above describe the configuration shape only. They are not model prices.

If pricing is absent, malformed, or does not cover a model, Runtime Assurance reports monetary-cost coverage as unavailable rather than guessing. Estimated runtime cost is an operational estimate and should be reconciled with authorized OpenAI Platform billing and usage records for financial reporting.

## Failure categories

Raw failure strings stay outside model context. Deterministic code maps failures to coarse categories such as:

- evaluation failure
- runtime-policy block
- configuration failure
- workflow-loop guard
- node failure
- other failure

This provides diagnostic signal without exposing arbitrary graph state or model content.

## Graph

`runtime/runtime_assurance_graph.py` runs:

```text
load aggregate runtime snapshot
        ↓
Runtime Reliability Agent
        ↓
Runtime Control Agent
        ↓
deterministic assurance boundary
        ↓
final runtime assurance packet
```

Both model workers are A1, tool-free, limited to six turns, one call each per graph execution, and zero automatic retries.

The Reliability Agent interprets completion, failure, approval-wait, graph-version, model-runtime, and telemetry-coverage patterns.

The Runtime Control Agent considers identity, authority, tool scope, human gates, failure handling, telemetry, budgets, and configuration. Any change to agent enablement, authority, tools, or runtime limits remains a human-controlled action outside this graph.

## Remediation boundary

The only registered handoff is:

```text
Runtime Assurance
        ↓
Product Development
```

The handoff may create a remediation problem statement using a runtime-assurance signal and telemetry-coverage information.

Product Development retains its existing A3 release-authorization boundary. Runtime Assurance cannot use the handoff to deploy a fix or mutate production.

## Durable operation

Run assurance with local model telemetry:

```bash
python -m runtime.run_runtime_assurance \
  --telemetry-source local \
  start
```

A custom local telemetry store may be selected with:

```bash
python -m runtime.run_runtime_assurance \
  --telemetry-source local \
  --telemetry-db local-data/model-telemetry.sqlite3 \
  start
```

When `SOZOROCK_AWS_OBSERVABILITY_ENABLED=1`, the command defaults to the AWS telemetry source. The source can still be selected explicitly with `--telemetry-source`.

Live Runtime Assurance model work requires `OPENAI_API_KEY`.

Read a stored result without a model call:

```bash
python -m runtime.run_runtime_assurance status \
  --execution-id <execution-id>
```

The terminal record is `runtime_assurance_packet`.

## Relationship to the Platform Graph Harness

The Platform Graph Harness is preventive: it tests whether a graph is allowed to exist with its declared authority, data, effect, and handoff boundaries.

Runtime Assurance is observational: it asks what execution and model-runtime evidence says about how those graphs are actually behaving.

The two layers should not be collapsed. Static policy validation cannot prove runtime health, and runtime statistics must not be allowed to rewrite static authority controls.
