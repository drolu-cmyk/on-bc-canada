# Model Runtime Telemetry

Model Runtime Telemetry records operational evidence about governed OpenAI Agents SDK work without storing the content the agents process.

Its purpose is to answer questions such as:

- Which governed worker made a model call?
- Which graph execution and node did the call belong to?
- How many model requests and tokens were used?
- How much input was served from cache?
- How much reasoning-token usage was reported?
- How long did the model run take?
- Which traces or local tool spans were involved?
- Is a reviewed cost estimate available?

It is not an application log for prompts or outputs.

## Architecture

```text
GraphKernel or governed non-graph worker
        ↓
model runtime context
        ↓
OpenAI Agents SDK trace
        ↓
privacy-bounded tracing processor
        ↓
local telemetry SQLite
        ↓
aggregate Runtime Assurance
```

GraphKernel attaches graph ID, graph version, execution ID, node ID, and actor ID around each registered agent handler. The tracing processor resolves that actor to its stable non-human identity.

Learning Graph Design and Platform Orchestration set the same runtime context directly because they call the SDK outside GraphKernel.

## Recorded trace facts

The local trace table can contain:

- SDK trace ID
- stable non-human identity ID
- graph actor ID
- SDK worker name
- work type
- graph ID and version where applicable
- execution ID and a one-way execution fingerprint
- node ID where applicable
- trace start and end timestamps
- trace latency
- count of recorded spans, generations, and local tool spans

The span table can contain:

- span ID and trace ID
- span type
- bounded span name
- model identifier for a generation span
- span start and end timestamps
- span latency
- request count
- input, output, and total tokens
- cached input tokens
- reasoning tokens
- optional reviewed pricing inputs
- optional estimated cost
- whether the span recorded an error

## Data that is not stored

The telemetry schema has no field for:

- prompts
- system instructions
- model output text
- structured model output bodies
- tool arguments
- tool outputs
- learner submissions
- learner artifacts
- learner direct identifiers
- employee individual records
- passwords
- API keys
- cloud credentials

The implementation also sets:

```text
OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA=0
```

before governed live model execution.

The local collector is a secondary processor. It does not replace graph authority, NHI controls, human gates, or the SDK's normal execution path.

## Local storage

The default reference store is:

```text
local-data/model-telemetry.sqlite3
```

A different location may be supplied with:

```text
SOZOROCK_MODEL_TELEMETRY_DB
```

`local-data/` is ignored by Git. This SQLite design is for local development and the current reference runtime, not the final AWS production telemetry store.

## Pricing inputs

Token usage is measured from SDK usage metadata. Monetary cost is different: it depends on a current reviewed pricing table.

Pricing is therefore configuration, not source-code knowledge. Optional rates are supplied with:

```text
SOZOROCK_MODEL_PRICING_JSON
```

Shape:

```json
{
  "model-name": {
    "input_per_million": 0,
    "cached_input_per_million": 0,
    "output_per_million": 0
  }
}
```

The numeric zeros show the expected fields only. They are not prices.

If a reviewed rate is unavailable, the telemetry record keeps token usage and marks pricing as unavailable. Runtime Assurance does not guess a cost.

## Latency coverage

The collector measures:

- full SDK trace duration for a governed model run
- generation-span duration
- local function or MCP tool-span duration when the SDK emits those spans

It does not currently claim a separate latency measurement for OpenAI-hosted tools such as hosted web search when that duration is not exposed as an independently attributable local tool span.

That distinction is deliberate. Total model-run latency may include hosted-tool work, but the platform does not subtract or infer an unsupported standalone hosted-tool duration.

## Trace linkage

SDK trace IDs are retained for operational correlation. Prompts and outputs are not required for that correlation.

The normal linkage is:

```text
work type
↓
non-human identity
↓
graph and execution where applicable
↓
node
↓
SDK trace
↓
generation/tool span
↓
usage and timing facts
```

Runtime Assurance consumes only aggregated telemetry. Model workers do not receive the telemetry database or raw span rows.

## Failure behavior

Telemetry is observational. A telemetry write failure cannot widen an agent's authority, bypass a graph evaluator, satisfy a human gate, or make an external action executable.

If telemetry cannot be collected, governed model work may continue under the existing identity and graph controls, while Runtime Assurance reports the telemetry gap. Authority remains fail-closed even when observability is incomplete.

## Production direction

The production AWS design should preserve the same contract while moving storage and aggregation away from local SQLite. The likely target is centralized encrypted operational telemetry with CloudWatch/OpenTelemetry-compatible export, explicit retention, access controls, cost controls, and separate aggregate views for Runtime Assurance.

That production step must preserve the current content boundary. More durable telemetry storage is not permission to capture prompts, learner submissions, model outputs, tool payloads, or credentials.
