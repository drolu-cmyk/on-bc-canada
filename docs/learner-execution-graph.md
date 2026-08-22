# Learner Execution Graph

The Learner Execution Graph connects an active Learning Graph to learner progress, mission evidence, coaching, and accountable human review.

It does not give a model access to raw learner work.

## Operating chain

```text
Active Learning Graph
        ↓
Pseudonymous learner path instance
        ↓
Sprint and lab progress
        ↓
Mission submission references
        ↓
Deterministic evidence-readiness check
        ↓
Deidentified model context
        ↓
Learning Coach Agent
        ↓
Learner Progress Agent
        ↓
Human Review Preparation Agent
        ↓
Ready? ── no ──→ learner action required
  │
 yes
  ↓
A3 human evidence review
  ├─ accepted → capability evidence recorded
  └─ needs revision → another learner iteration
```

## Data boundary

`learner_progress_store.py` keeps pseudonymous path and submission records in the local reference implementation. The model layer does not receive:

- learner reference or learner ID
- cohort ID
- submission ID
- raw artifact references
- learner submission content
- attendance records
- support records
- credential records
- revision, defense, or changed-scenario references

The model receives only deidentified program and progress metadata such as pathway ID, reviewed learning-unit text, attempt number, unit-status counts, artifact types, evidence-standard descriptions, and deterministic readiness flags.

This matches `config/data-controls.yaml`, where model adapters may use public program material, synthetic lab data, and deidentified metrics but may not receive enrollment, attendance, support, learner submissions, or credentials.

## Agent roles

### Learning Coach Agent

Uses deidentified readiness information to suggest concrete preparation steps. It does not claim to have read the learner's work and cannot grade or certify.

### Learner Progress Agent

Interprets path progress and attempt metadata. It can recommend another iteration, ordinary learning support, or readiness for human review. It cannot remove a learner, change enrollment, issue a credential, or make an employment or eligibility decision.

### Human Review Preparation Agent

Turns reviewed capability evidence standards into a concise checklist for the accountable human assessor. It does not judge whether the raw evidence passes.

## Deterministic controls

Before any learner-support agent runs, the graph builds a deidentified model context and checks it against prohibited fields and known private values from the learner and submission records.

Evidence readiness is calculated without a model. For every mission evidence standard, the graph checks:

- whether an accepted artifact type is represented
- whether a revision is present when required
- whether a defense response is present when required
- whether a changed-scenario response is present when required

If any required element is absent, the submission is routed to learner action required. A human acceptance decision is not available on that path.

## Human evidence review

A metadata-complete mission stops at an A3 human evidence-review node. The human assessor can inspect the raw evidence through the approved learner-data workflow and use the generated checklist against the reviewed evidence standards.

Acceptance records the capability evidence through `LearnerProgressStore.accept_mission_evidence` and can complete the mission and path when all requirements are met.

A non-acceptance routes to revision. It is treated as a normal learning outcome rather than a graph failure.

## Persistence

`graph_execution_store.py` preserves graph state and the event ledger. A learner assessment can stop at human review and resume later without rerunning the three learner-support agents.

Graph events for this workflow use `learner_private` and `quality_record`, with the pseudonymous learner reference and cohort ID attached to the event ledger. The model context remains deidentified.

## Command interface

Start a learner assessment after a mission submission exists:

```bash
python -m runtime.run_learner_execution start \
  --submission-id <submission-id>
```

Starting the learner-support agents requires `OPENAI_API_KEY`.

Read status without a model call:

```bash
python -m runtime.run_learner_execution status \
  --execution-id <execution-id>
```

Record the human evidence decision:

```bash
python -m runtime.run_learner_execution review \
  --execution-id <execution-id> \
  --accept \
  --reviewer-id <reviewer-id> \
  --note "Reviewed raw evidence against the capability standards."
```

Use `--revise` when another learner iteration is required.

## Authority

Agents are A1. They may analyze deidentified learning metadata, coach, and prepare a review checklist.

Capability-evidence acceptance is A3 and remains human.

This graph does not issue credentials, change enrollment, make employment decisions, contact external parties, or expose learner submissions to model adapters.
