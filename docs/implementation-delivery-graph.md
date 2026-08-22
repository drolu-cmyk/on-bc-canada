# Implementation and Delivery Graph

## Purpose

The Implementation and Delivery Graph turns a human-authorized Product Development release packet into reversible staging changes and verification evidence without giving a model unrestricted repository, shell, cloud, or deployment authority.

```text
authorized product packet
        ↓
repository context snapshot
        ↓
implementation plan
        ↓
typed file change generation
        ↓
deterministic change assurance
        ↓
A2 staging write
        ↓
registered verification commands
        ↓
code review
        ↓
security review
        ↓
quality review
        ↓
deterministic delivery assurance
   ↙                       ↘
blocked                A3 human review
                              ↓
                 authorized for merge or deploy
```

Authorization is not execution. The graph does not merge a pull request, push a branch, mutate production infrastructure, or deploy a production service.

## Staging workspace

The model has no filesystem tool. It receives an operator-selected snapshot of repository files containing:

- relative path
- existence state
- SHA-256 hash
- UTF-8 text content

The generated change set is typed and then validated by deterministic code.

The staging executor enforces:

- explicit allowed repository roots
- no absolute paths or `..` traversal
- protected path exclusions for `.git`, `.env`, `secrets`, `local-data`, virtual environments, and dependency directories
- text-file extension allowlist
- file-count and file-size limits
- full-file content for create and update operations
- exact SHA-256 preconditions for updates and deletes
- no overwrite through a create operation
- obvious secret-material scanning
- duplicate-path rejection

All changes are validated before the first write. The reference adapter keeps backups for affected files and restores them if the staging write itself fails.

## A2 side effects

Model workers remain A1.

Only deterministic services receive A2 in this graph:

- staging file application
- registered verification execution

This keeps reversible side effects separate from model reasoning.

## Verification registry

The model cannot invent or run arbitrary shell commands.

Verification uses operator-registered command identifiers. The reference command runner executes fixed argv lists with `shell=False`, a bounded timeout, and bounded captured output.

The repository command interface currently exposes identifiers for:

- specification validation
- public-copy validation
- public-site validation
- deployment-contract validation
- runtime tests
- curriculum compiler tests

An operator can require specific verification identifiers. The planning agent is not allowed to omit an operator-required verification.

## Review agents

### Implementation Planning Agent

Converts the authorized product packet into small reversible implementation slices and verification requirements.

### Code Generation Agent

Produces complete text for create and update operations and carries forward exact file hashes for update and delete preconditions.

### Code Review Agent

Reviews correctness, maintainability, contract drift, error handling, hidden coupling, and rollback risk.

### Implementation Security Review Agent

Reviews privilege expansion, identity and authorization changes, agent tool boundaries, secret exposure, injection paths, destructive operations, and audit controls.

### Implementation Quality Review Agent

Reviews the registered verification results and whether critical behavior, regressions, failure paths, accessibility where relevant, and agent boundaries are adequately covered.

All five are A1 and have no direct side-effect tools.

## Deterministic delivery assurance

Delivery assurance blocks the release candidate when:

- any registered verification failed;
- code review returns a blocking finding;
- security review returns a blocking finding;
- quality review returns a blocking finding.

Only a passing staging packet reaches A3.

## Pre-approval integrity

A staging tree can change after tests finish but before a human reviews the result. The delivery runner therefore compares the current hash of every affected file with the exact post-change hash stored in the graph execution before recording A3 approval.

If any file has drifted, authorization is refused and the graph remains at the human gate.

## Durable state

The generic graph execution store preserves the implementation plan, generated change set, applied hashes, verification results, specialist reviews, checkpoints, event ledger, and A3 state.

The graph can stop at A3 and resume later without rerunning model workers. The staging-integrity check still runs at resume.

## Current boundary

This graph ends at `authorized_for_merge_or_deploy`.

A later execution graph may receive narrowly scoped GitHub or AWS tools, but merge and production deployment should remain separate from staging generation so tool identity, branch protection, environment controls, and production authorization can be enforced independently.
