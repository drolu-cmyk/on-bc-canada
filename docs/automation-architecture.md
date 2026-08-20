# Portable automation architecture

## Operating promise

The standard path is automated for learners, instructors, and operators. A learner submits one form and receives the correct next step. An instructor opens one workspace with the cohort, generated session plan, lab state, questions, risk notices, and exceptions. The operator receives a live evidence view rather than a manual report-assembly task.

The automation boundary is clear: routine routing and evidence collection are automated; safety, accessibility exceptions, assessment appeals, credential decisions, policy changes, and external claims retain human authorization.

## System of record

The canonical source is a versioned repository of Markdown, YAML, and JSON. Google Drive is a distribution and collaboration surface, not the only source of truth. Generated Google Drive documents carry the source version, generation timestamp, policy version, and evidence references.

Canonical objects:

- program identity and jurisdiction position;
- module specifications and learning outcomes;
- assessment rubrics and evidence requirements;
- learner and cohort policies;
- provider adapter contracts;
- public claims and release gates;
- event schemas and retention classes;
- outcomes, budget, and funder-report definitions.

## Control-plane components

| Component | Reference service | Portable contract |
| --- | --- | --- |
| Source control | GitHub | Versioned files, pull-request checks, release tags |
| Workflow orchestration | AWS Step Functions | State-machine definitions and event contracts |
| Event routing | AWS EventBridge | Event envelope and event schema |
| Queues and retries | AWS SQS | Idempotency key, retry policy, dead-letter event |
| Compute | AWS Lambda | Stateless handlers behind adapter interfaces |
| Operational data | DynamoDB | Learner, cohort, task, status, and approval records |
| Evidence archive | S3 | Immutable/versioned objects with hash and retention metadata |
| Public and learner pages | S3/CloudFront or equivalent | Static build artifacts and accessibility checks |
| Collaboration | Google Drive | Generated links, shared folders, permissions, and export package |
| Models | Codex, Grok, Google models | Structured-input/structured-output model adapter |
| Credentials | Program verifier plus portable credential format | Issuer, achievement, evidence, status, verification |

Provider-specific services remain behind adapter interfaces. Curriculum and learner records remain exportable when a service changes.

## Standard learner journey

```text
interest form
  -> consent and data-minimization check
  -> capacity rules
  -> invitation or waitlist message
  -> learner workspace provisioning
  -> orientation checklist
  -> weekly session packet generated from module specification
  -> reminders, lab links, attendance, and submission capture
  -> structured feedback and exception routing
  -> attendance calculation
  -> credential authorization gate
  -> certificate and learner record export
  -> de-identified quality and funder metrics
```

Every transition emits a versioned event. Every generated artifact has a source version. Every failed automation creates a retryable task or a human exception with an owner, due time, and evidence packet.

## Model gateway

The model gateway accepts a task contract rather than a free-form prompt. A task contract contains:

- task type;
- permitted data class;
- source documents;
- expected JSON schema;
- model risk tier;
- maximum cost and latency;
- verification method;
- fallback provider;
- required disclosure.

Example tasks:

- generate a learner reminder from an approved template;
- summarize a support issue for an authorized operator;
- produce a first-pass rubric comment tied to evidence;
- prepare an instructor run-of-show from a module specification;
- identify missing evidence in a funder report;
- translate content into an approved accessible format.

No model changes a learning outcome, public claim, policy, assessment decision, credential status, or safety disposition without the configured human gate.

## Instructor experience

Before each session, the system generates one task view containing cohort status, attendance exceptions, authorized support flags, the session sequence, expected evidence, lab links, questions, explicit instructor decisions, and a closeout action.

The system generates the next session packet, notifies learners, and updates the evidence ledger.

## Learner experience

The learner receives one consistent workspace containing the weekly activity, concept material, problem set, case, lab link, submission checklist, AI-assistance disclosure, feedback status, support route, accessibility route, attendance status, certificate status, and exportable evidence record.

## Reliability and failure design

Every automation has:

- an idempotency key;
- a timeout;
- a retry policy;
- a dead-letter route;
- a human owner for unresolved errors;
- a privacy classification;
- an audit event;
- a rollback or compensating action;
- a learner-safe fallback message.

Provider failure produces a stable service message and replacement path. Google Drive failure leaves the canonical source and evidence ledger available. Instructor unavailability produces a continuity message and an escalation task.

## Portability

Portability is defined by stable domain objects, JSON schemas, event types, content and assessment specifications, evidence identifiers, credential payloads, export formats, provider capability tests, and deployment configuration.
