# AWS Runtime Observability

AWS Runtime Observability centralizes privacy-safe model runtime telemetry in AWS Canada Central while preserving the same content boundary as the local telemetry store.

It is infrastructure for operational evidence. It is not permission to capture prompts, learner work, model output, tool payloads, credentials, or direct learner identity.

## Production boundary

The stack is defined in:

```text
infra/runtime-observability.template.json
```

The deployment region is:

```text
ca-central-1
```

The default pilot log group is:

```text
/sozorock/canada/runtime/model-telemetry
```

The default retention period is 30 days.

The log group uses a dedicated customer-managed KMS key with rotation enabled. The key and log group use retained CloudFormation deletion policies so an infrastructure-stack deletion cannot silently erase retained operational evidence. CloudWatch retention still removes log events when the configured retention period expires.

## Centralized record

The runtime publishes one summary for a completed governed model trace.

The centralized record may contain:

- SDK trace ID
- stable non-human identity ID
- actor and SDK worker name
- work type
- graph ID and version where applicable
- one-way execution fingerprint
- node ID where applicable
- request count
- input, output, total, cached-input, and reasoning tokens
- trace, generation, and local tool latency
- error indicator
- optional estimated model cost when reviewed pricing is configured

The direct execution ID remains local and is not exported.

The centralized schema contains no field for prompts, model output bodies, learner content, tool arguments, tool outputs, passwords, API keys, or cloud credentials.

## Embedded metrics

Each trace summary is written as CloudWatch Embedded Metric Format JSON.

The metric namespace is:

```text
SozoRock/CanadaPlatform
```

The only metric dimension is:

```text
Environment
```

Work type, graph, actor, node, trace ID, and execution fingerprint remain searchable log properties rather than CloudWatch metric dimensions. This avoids creating a new custom-metric series for every workflow, graph, node, or execution.

The current metric set includes:

- ModelRunCount
- RequestCount
- InputTokens
- OutputTokens
- TotalTokens
- CachedInputTokens
- ReasoningTokens
- ModelErrorCount
- RunLatencyMs
- GenerationLatencyMs when available
- LocalToolLatencyMs when available
- EstimatedModelCostUSD only when reviewed pricing is complete for that trace

## Least privilege

The CloudFormation stack creates two managed policies but does not attach them to a workload automatically.

The publisher policy permits only:

```text
logs:PutLogEvents
```

against the precreated telemetry stream.

It does not permit the runtime to create log groups, create streams, change retention, modify KMS policy, query logs, or administer CloudWatch.

The Runtime Assurance reader policy permits only:

```text
logs:StartQuery
logs:GetQueryResults
logs:StopQuery
```

for the centralized telemetry query path.

The deployment owner attaches each policy to the correct workload identity after the stack is created.

## Alarms

The pilot stack includes four bounded CloudWatch alarms.

### Model error

Triggers when at least one governed trace records an error span within five minutes.

### Daily token volume

The default threshold is 1,000,000 total tokens in one day.

The threshold is a pilot cost-control parameter, not a claim about expected daily usage.

### Daily estimated model cost

The default threshold is USD 5 in one day.

This alarm can receive data only when `SOZOROCK_MODEL_PRICING_JSON` contains reviewed rates for every generation represented by the trace. It is an operational estimate, not a substitute for provider billing records.

### Run latency

The default threshold is 30 seconds average model-run latency for two consecutive five-minute periods.

All four alarms treat missing metric data as non-breaching. Missing observability is handled separately by Runtime Assurance rather than being interpreted as either healthy or failed model execution.

## Runtime enablement

Centralized publishing is off unless explicitly enabled.

The runtime environment uses:

```text
SOZOROCK_AWS_OBSERVABILITY_ENABLED=1
SOZOROCK_AWS_OBSERVABILITY_REGION=ca-central-1
SOZOROCK_AWS_TELEMETRY_LOG_GROUP=/sozorock/canada/runtime/model-telemetry
SOZOROCK_AWS_TELEMETRY_LOG_STREAM=model-runtime
SOZOROCK_AWS_OBSERVABILITY_ENVIRONMENT=pilot
```

Runtime Assurance uses the same configuration plus an optional query window:

```text
SOZOROCK_AWS_ASSURANCE_LOOKBACK_MINUTES=1440
```

A failed CloudWatch export is secondary to the governed model run. The local privacy-safe telemetry record remains available and the model workflow does not gain or lose authority because observability is unavailable.

## Runtime Assurance read path

Runtime Assurance can select centralized telemetry with:

```bash
python -m runtime.run_runtime_assurance \
  --telemetry-source aws \
  start
```

The CloudWatch reader requests only privacy-safe trace-summary fields, sorts newest first, deduplicates by SDK trace ID, and performs final aggregation in deterministic Python code.

The resulting aggregate contains model-run count, requests, tokens, estimated cost coverage, error count, average latency, and work-type summaries. Runtime Assurance agents still receive aggregate operational evidence only.

## Deployment authority

Merging this source does not deploy the AWS stack.

Deployment requires an explicit operator action:

```bash
bash scripts/deploy_runtime_observability.sh
```

or the manual GitHub workflow:

```text
.github/workflows/runtime-observability-deploy.yml
```

The workflow deploy job runs only when both repository variables are configured:

```text
RUNTIME_OBSERVABILITY_DEPLOYMENT_ENABLED=true
RUNTIME_OBSERVABILITY_DEPLOY_ROLE_ARN=<dedicated GitHub OIDC deployment role ARN>
```

This preserves the platform's A3 production-change boundary.

## Validation

Before deployment, run:

```bash
python scripts/validate_runtime_observability.py
python -m unittest runtime.test_aws_runtime_observability -v
```

The repository CI runs the observability validator and the complete runtime suite before merge.
