# Runtime Assurance

Runtime Assurance turns durable execution records into bounded evidence about whether the autonomous platform is operating reliably and inside its control model.

It is an assurance workflow, not a self-healing superuser. The graph can identify concerns and recommend human investigation. It cannot disable an agent, change authority or tools, change runtime policy, deploy code, mutate infrastructure, or alter production.

## Evidence boundary

The first release reads aggregate fields from the durable stores that already exist:

- generic GraphExecutionStore records
- ResearchStore execution records

The deterministic snapshot builder extracts only aggregate operational evidence such as:

- graph ID and observed versions
- execution count
- completed, failed, and waiting-for-approval counts
- completed-node counts
- event counts
- coarse failure categories
- current emergency-disable configuration counts

It does not pass raw graph state, checkpoints, prompts, model outputs, credentials, learner identity, or raw approval records to the Runtime Assurance agents.

## Telemetry honesty

`runtime/runtime_assurance.py` explicitly records which telemetry is available.

The initial release can prove:

```text
execution status
graph version
node completion
human approval state
failure reason category
event count
```

It does not yet claim to have:

```text
model token usage
model monetary cost
provider latency
tool-call latency
trace sampling
```

Those fields are marked unavailable. Missing telemetry is a coverage gap, not evidence that the system is healthy.

A missing runtime store is also reported as a coverage gap rather than silently ignored.

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

The Reliability Agent interprets completion, failure, approval-wait, graph-version and telemetry-coverage patterns.

The Runtime Control Agent considers identity, authority, tool scope, human gates, failure handling, telemetry, budgets and configuration. Any change to agent enablement, authority, tools or runtime limits remains a human-controlled action outside this graph.

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

Run assurance over the current generic graph and research execution stores:

```bash
python -m runtime.run_runtime_assurance start
```

Live model work requires `OPENAI_API_KEY`.

Read a stored result without a model call:

```bash
python -m runtime.run_runtime_assurance status \
  --execution-id <execution-id>
```

The terminal record is `runtime_assurance_packet`.

## Relationship to the Platform Graph Harness

The Platform Graph Harness is preventive: it tests whether a graph is allowed to exist with its declared authority, data, effect and handoff boundaries.

Runtime Assurance is observational: it asks what the durable execution evidence says about how those graphs are actually behaving.

The two layers should not be collapsed. Static policy validation cannot prove runtime health, and runtime statistics must not be allowed to rewrite static authority controls.