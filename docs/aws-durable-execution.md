# AWS Durable Execution Plane

The durable execution plane moves generic governed graph state from local SQLite to AWS Canada without changing graph definitions, agent authority, human gates, or model-provider contracts.

It is an execution substrate. It is not a new agent and it does not decide which work should run.

## Scope

The current AWS-capable generic execution workflows are:

- Business Operations
- Learner Execution
- Career Mobility
- Employer Workforce
- Outcomes Intelligence
- Runtime Assurance

Research Intelligence and Product Development retain their specialized persistence stores. They remain explicit migration gaps until those stores are ported with their domain-specific records and invariants intact.

## Architecture

```text
bounded work request
        ↓
encrypted DynamoDB command record
        ↓
SQS FIFO pointer message
        ↓
worker obtains command and execution lease
        ↓
existing governed GraphKernel workflow
        ↓
optimistic execution-state update
        ↓
append-only event mirror
        ↓
bounded EventBridge execution signal
        ↓
Runtime Assurance operational read
```

The queue message is intentionally smaller than the work command. Learner-private or employer-private command data stays in encrypted DynamoDB. SQS receives the work ID, graph identity, action, work type, and one-way fingerprints only.

## DynamoDB execution model

The table uses a composite key:

```text
pk = EXEC#<execution-id>
sk = STATE
```

Additional immutable records use the same execution partition:

```text
EVENT#<event-id>
TERM#<record-kind>
```

Work commands use a separate partition:

```text
pk = WORK#<work-id>
sk = COMMAND
```

Execution state includes graph identity, graph version, current node, status, state JSON, history, checkpoints, human approval state where applicable, failure category source text, the hash-chained event ledger snapshot, store version, update time, and optimistic revision.

The state record has no TTL. Work commands have `expires_at_epoch` and use the table TTL policy because queue commands are temporary delivery records rather than programme evidence.

## Concurrency

Every execution state update carries a revision number.

A process that loads revision 7 may write revision 8 only when the database still contains revision 7. Competing writers therefore cannot silently overwrite each other.

The production store adds a stronger rule: a fresh process may not update an execution that already exists until it has first loaded that execution. This prevents a retried start request from replacing a waiting human decision or a completed record.

## Leases

Workers may acquire a bounded execution lease before processing queue work.

A lease records:

- worker owner ID
- acquisition epoch
- expiry epoch

Another owner is blocked until the lease expires. The default reference lease is 120 seconds and may be configured between 30 and 900 seconds.

Leases complement, rather than replace, optimistic revision checks.

## Event integrity

The GraphKernel event ledger remains hash chained.

DynamoDB stores the current ledger snapshot with execution state and mirrors every event as an immutable `EVENT#...` record. Reusing an event ID with different content fails closed.

Terminal records are also immutable after successful completion. Repeating the same terminal record is idempotent; attempting to rewrite it with different content fails.

## Work delivery

The AWS stack creates a FIFO work queue and FIFO dead-letter queue.

Delivery rules:

- explicit message deduplication ID
- one message group per execution fingerprint
- 20-second long polling
- 120-second default visibility timeout
- 14-day queue retention
- dead-letter redrive after the configured receive count
- KMS encryption at rest

SQS delivery is still treated as at least once. Workers must therefore preserve idempotency and must not interpret queue uniqueness as proof that work ran exactly once.

## Command boundary

A `WorkCommand` defines:

- work ID
- execution ID
- registered work type
- graph ID and version
- start or resume action
- data class
- idempotency key

The encrypted command record may contain the bounded payload needed by the graph runner.

The SQS pointer does not contain:

- the direct execution ID
- learner identifiers
- submission identifiers
- employer record content
- prompts
- model outputs
- credentials
- API keys

## EventBridge boundary

The custom platform event bus accepts only bounded execution signals such as:

- graph execution queued
- graph execution completed
- graph execution failed
- graph approval requested
- graph retry exhausted

The event detail contains an execution fingerprint, work type, graph ID, and status. Direct execution identifiers and graph state bodies are excluded.

## Runtime Assurance

The DynamoDB table exposes `ExecutionUpdatedIndex` using:

```text
partition key: sk
sort key: updated_at
```

Runtime Assurance queries only `sk = STATE` and projects operational fields required for aggregate reliability analysis.

The AWS assurance source does not read graph state JSON. It reads graph ID, version, status, failure text for deterministic categorization, history count source, approval state, event count source, and update time.

When the generic execution backend is AWS, Runtime Assurance removes the local generic SQLite source from its coverage set and replaces it with the DynamoDB execution source. Research coverage remains separate until Research persistence is migrated.

## Storage controls

The CloudFormation stack uses:

- AWS Canada Central (`ca-central-1`)
- DynamoDB on-demand billing
- customer-managed KMS encryption for state and queues
- 35-day DynamoDB point-in-time recovery
- DynamoDB deletion protection
- retained KMS key
- retained DynamoDB table
- retained dead-letter queue
- TTL only for work-command records

The platform event bus uses the normal EventBridge encryption service boundary and carries pointer-only operational signals.

## IAM separation

The stack creates three managed policies instead of one broad runtime policy.

### Execution state policy

Allows bounded DynamoDB read, conditional write, update, and query operations plus the required KMS use.

### Work producer policy

Allows command persistence and `sqs:SendMessage` to the work queue.

### Work consumer policy

Allows receive, delete, visibility extension, command read/update, DynamoDB query, bounded EventBridge publishing, and required KMS use.

The policies do not grant DynamoDB scan, SQS purge, IAM pass-role, or wildcard KMS administration.

## Backend selection

Local SQLite remains the default.

Use:

```text
SOZOROCK_EXECUTION_BACKEND=aws
```

or:

```text
SOZOROCK_AWS_EXECUTION_ENABLED=true
```

to select the AWS execution store.

The AWS runtime also uses:

```text
SOZOROCK_AWS_EXECUTION_REGION=ca-central-1
SOZOROCK_AWS_EXECUTION_TABLE=sozorock-ca-graph-executions
SOZOROCK_AWS_EXECUTION_QUEUE_URL=<stack output>
SOZOROCK_AWS_EXECUTION_EVENT_BUS=<stack output>
SOZOROCK_AWS_EXECUTION_COMMAND_TTL_DAYS=14
SOZOROCK_AWS_EXECUTION_LEASE_SECONDS=120
```

A non-Canada region fails closed.

## Deployment boundary

Source validation runs on ordinary repository CI.

AWS deployment does not run on push, pull request, or merge. The deployment workflow is `workflow_dispatch` only and requires both:

```text
DURABLE_EXECUTION_DEPLOYMENT_ENABLED=true
DURABLE_EXECUTION_DEPLOY_ROLE_ARN=<dedicated GitHub OIDC deployment role>
```

The deploy script verifies the AWS account and `ca-central-1` before CloudFormation is invoked.

The stack creates infrastructure and managed policies only. It does not create a Lambda, ECS service, Step Functions state machine, model worker, or production credential.

## Validation

Run:

```bash
python scripts/validate_durable_execution.py
bash -n scripts/deploy_durable_execution.sh
python -m unittest discover -s runtime -p 'test_*.py' -v
```

The durable execution tests cover state round trips, immutable event mirrors, terminal-record immutability, optimistic concurrency, execution leases, command idempotency, pointer-only SQS delivery, EventBridge redaction, backend selection, and DynamoDB Runtime Assurance aggregation.
