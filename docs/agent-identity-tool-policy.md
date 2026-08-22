# Agent Identity, Tool, and Runtime Policy

Every model worker in the Canada platform has a stable logical non-human identity before it is allowed to participate in platform execution.

This layer does not create cloud credentials and does not store secrets. It defines the identity, authority, tool scope, model-data scope, and runtime budget that a future workload-identity implementation must preserve.

## Why this exists

A graph authority model is incomplete if a model worker can silently gain a new tool, receive broader data, consume unbounded turns, or continue operating after an incident.

The agent identity policy adds four controls above the SDK workers:

1. stable non-human identity
2. least-privilege tool scope
3. bounded model execution
4. emergency disable state

The Platform Graph Harness still owns graph routing, data/effect boundaries, human gates, and cross-graph handoffs. The identity registry governs the model workers inside those boundaries.

## Stable identities

`runtime/agent_identity_registry.py` contains one record for every current model worker.

There are 38 identities at launch:

- 7 Research Intelligence agents
- 10 Product Development agents
- 5 Business Operations agents
- 3 Learner Execution agents
- 5 Career Mobility agents
- 7 Employer Workforce agents
- 1 Platform Orchestrator agent

An identity uses the form:

```text
nhi:canada-platform:<actor-id>
```

Examples:

```text
nhi:canada-platform:research-director-agent
nhi:canada-platform:security-agent
nhi:canada-platform:finance-agent
nhi:canada-platform:learning-coach-agent
nhi:canada-platform:platform-orchestrator-agent
```

The NHI is stable even when the underlying model version changes.

Every current identity is A1. Model workers do not receive A3/A4 authority merely because their output later reaches a human approval node.

## Credential boundary

Identity records contain no API key, cloud credential, token, password, or secret reference.

The current credential boundary is `application_runtime_only`. The application runtime obtains provider credentials outside the identity record. `secret_access` is false for every model worker.

This is a logical workload identity layer, not yet an AWS IAM/OIDC workload-identity implementation. Production cloud identity can be added later without changing the stable NHI or graph actor IDs.

## Tool scope

Most platform agents are intentionally tool-free.

Only four current Research Intelligence workers may receive hosted web search:

```text
research-director-agent
evidence-agent
technology-agent
contradiction-agent
```

Their registered tool label is:

```text
hosted_web_search
```

All Product, Business, Learner, Career, Employer, and Platform Orchestrator workers are tool-free in the current release.

The policy does not grant repository write, cloud mutation, messaging, payment, credential issuance, production deployment, or employee-decision tools to any model worker.

## Runtime turn budgets

The registry records the provider turn limit for each worker and a maximum number of model calls for each workflow execution.

| Work type | Specialist identities | Max turns per worker | Max model calls on one execution path |
| --- | ---: | ---: | ---: |
| Research Intelligence | 7 | 8 | 7 |
| Product Development | 10 | 8 | 10 |
| Business Operations | 5 | 8 | 1 |
| Learner Execution | 3 | 6 | 3 |
| Career Mobility | 5 | 6 | 5 |
| Employer Workforce | 7 | 7 | 7 |
| Platform Orchestration | 1 | 6 | 1 |

Business Operations has five specialists but deterministic routing selects only one workstream agent in an execution.

Automatic model retries are disabled in the launch policy. `retry_limit` and `retry_limit_per_agent` are zero.

The model-call budgets are tested against actual GraphDefinition paths rather than the total number of agents in a file.

## Emergency disable boundary

The runtime supports two environment-controlled stop mechanisms:

```text
SOZOROCK_DISABLED_AGENT_IDS
SOZOROCK_DISABLED_WORK_TYPES
```

`SOZOROCK_DISABLED_AGENT_IDS` accepts a comma-separated stable NHI ID, graph actor ID, or SDK agent name.

Example:

```text
SOZOROCK_DISABLED_AGENT_IDS=security-agent,finance-agent
```

A whole work type can be stopped:

```text
SOZOROCK_DISABLED_WORK_TYPES=business_operations
```

A third control can contract the global turn ceiling:

```text
SOZOROCK_MAX_AGENT_TURNS=6
```

If the effective ceiling is lower than a registered provider contract, GraphKernel fails the affected agent node before entering the model handler. The platform does not silently widen the cap or let a model re-enable itself.

These are runtime configuration controls. The repository CLI intentionally does not provide an agent self-service enable/disable command.

## Runtime enforcement

`runtime/agent_runtime_guard.py` is called by GraphKernel before a registered graph agent handler runs.

It verifies:

- a registered actor uses its registered NHI
- authority remains A1
- secret access remains false
- the identity or work type is not disabled
- the effective turn ceiling has not fallen below the provider contract

Generic unregistered GraphKernel fixtures and extension graphs remain usable. CI separately requires every agent in the six registered platform graphs to have an NHI record before merge.

The Platform Orchestrator sits outside GraphKernel, so `openai_platform_orchestrator.py` calls the SDK-level guard directly before `Runner.run_sync`.

## SDK construction audit

`runtime/agent_identity_audit.py` reconstructs every current SDK agent without making a model call.

It reconciles:

```text
GraphDefinition actor
        ↕
non-human identity record
        ↕
constructed Agents SDK worker
```

The audit checks:

- every registered graph agent has exactly one identity
- no stale identity exists for a removed graph actor
- stable NHI IDs are unique
- SDK names are unique and match the registry
- all model workers remain A1
- all `secret_access` values remain false
- model-data classes stay inside the graph model-data contract
- actual SDK tools exactly match registered tools
- every SDK worker has typed output
- registered turn limits match provider defaults
- every registered identity has a constructed SDK worker
- no constructed SDK worker is missing an identity

This catches a source change such as adding a tool to Marketing or Security even if the graph topology itself does not change.

## Operator commands

Validate identities and actual SDK construction:

```bash
python -m runtime.run_agent_identity_policy validate
```

Inspect all identities and workflow budgets:

```bash
python -m runtime.run_agent_identity_policy manifest
```

Inspect effective runtime state for one identity:

```bash
python -m runtime.run_agent_identity_policy status \
  --agent-id security-agent
```

The status command is read-only.

## CI gate

The repository validation workflow runs the identity audit as a dedicated step:

```text
Validate agent identity and tool contracts
```

The graph authority harness runs separately. Both must pass before the general runtime test suite.

This separation is intentional:

- the Platform Graph Harness asks whether the workflow is allowed to do something
- the Agent Identity Policy asks whether the particular model worker is allowed to exist, see the declared model context, use its tools, and consume its registered runtime budget

Both controls must agree before an autonomous platform can be considered bounded.
