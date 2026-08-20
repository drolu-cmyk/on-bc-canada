# Portable automation architecture

## 1. The operating promise

The system should feel manual to nobody on the normal path. A learner submits one form and receives the right next step. An instructor opens one workspace and sees the cohort, generated session plan, lab state, questions, risk notices, and exceptions. The operator receives a live evidence view rather than a request to assemble a report from scattered files.

The automation objective is therefore:

> **No manual runbook for standard delivery; explicit human review only where the consequence, uncertainty, or accountability requires it.**

This is stronger and safer than claiming that a model can make every decision without review.

## 2. System of record

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

## 3. Control-plane components

| Component | First implementation | Portable contract |
| --- | --- | --- |
| Source control | GitHub | Versioned files, pull-request checks, release tags |
| Workflow orchestration | AWS Step Functions | State-machine definitions and event contracts |
| Event routing | AWS EventBridge | Event envelope and event schema |
| Queues and retries | AWS SQS | Idempotency key, retry policy, dead-letter event |
| Compute | AWS Lambda | Small stateless handlers behind adapter interfaces |
| Operational data | DynamoDB | Learner, cohort, task, status, and approval records |
| Evidence archive | S3 | Immutable/versioned objects with hash and retention metadata |
| Public and learner pages | S3/CloudFront or equivalent | Static build artifacts and accessibility checks |
| Collaboration | Google Drive | Generated links, shared folders, permissions, and export package |
| Models | Codex, Grok, Google models | Structured-input/structured-output model adapter |
| Credentials | Internal verifier plus portable credential format | Issuer, achievement, evidence, status, verification |

The first implementation may be AWS-heavy, but no curriculum or learner record should be written in a provider-specific format that prevents export.

## 4. Standard learner journey

```text
interest form
  -> consent and data-minimization check
  -> readiness and capacity rules
  -> automated invitation or waitlist message
  -> learner workspace provisioning
  -> orientation checklist
  -> weekly session packet generated from module spec
  -> reminders, lab links, attendance, and submission capture
  -> structured feedback and exception routing
  -> completion/attendance calculation
  -> credential approval gate
  -> certificate and learner record export
  -> de-identified quality and funder metrics
```

Every transition emits a versioned event. Every generated artifact has a source version. Every failed automation creates a retryable task or a human exception with an owner, due time, and evidence packet.

## 5. Model gateway

The model gateway accepts a task contract, not a free-form prompt. A task contract contains:

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
- draft an instructor run-of-show from a module specification;
- identify missing evidence in a funder report;
- translate content into an approved accessible format.

No model may silently change a learning outcome, public claim, policy, assessment decision, credential status, or safety disposition.

## 6. Generated instructor experience

The instructor does not need a long manual. Before each session, the system generates a single task view containing:

1. cohort status and attendance exceptions;
2. learner support flags that the instructor is authorized to see;
3. the 90-minute or 120-minute run-of-show;
4. the concept, problem, case, lab, and debrief sequence;
5. expected learner evidence and common failure patterns;
6. current lab links and safe-data reminder;
7. questions waiting for response;
8. decisions that require the instructor’s explicit action;
9. a closeout button that records attendance, risks, feedback, and next steps.

The system then generates the next session packet, notifies learners, and updates the evidence ledger.

## 7. Generated learner experience

The learner receives one consistent workspace:

- what to do this week;
- why it matters;
- short concept material;
- problem set and case;
- lab link with safe-data boundaries;
- submission checklist;
- AI-assistance disclosure field;
- feedback and resubmission status;
- support and accessibility route;
- attendance and certificate status;
- exportable evidence record.

## 8. Reliability and failure design

Every automation must have:

- an idempotency key;
- a timeout;
- a retry policy;
- a dead-letter route;
- a human owner for unresolved errors;
- a privacy classification;
- an audit event;
- a rollback or compensating action;
- a learner-safe fallback message.

If a model provider fails, the learner should see a stable service message and a replacement path. If Google Drive fails, the canonical source and evidence ledger remain available. If an instructor is unavailable, the cohort receives a generated continuity message and the operator receives an escalation task.

## 9. What “portable” means in practice

Portability is not achieved by listing several vendors. It is achieved by keeping the following stable:

- domain objects;
- JSON schemas;
- event types;
- content and assessment specifications;
- evidence identifiers;
- credential payloads;
- export formats;
- provider capability tests;
- deployment configuration.

The first provider is an implementation choice. The contracts and evidence remain the institution’s assets.

