# Lead workstream synthesis

This document records the design decisions returned by the 19 specialized
workstreams. It is an internal architecture and release-planning record. It
does not establish accreditation, certification, licensing, regulatory
approval, endorsement, employment outcomes, or immigration outcomes.

## Decisions by workstream

| # | Workstream | Decision that governs integration |
|---:|---|---|
| 1 | Control plane | Use an event-driven modular monolith first; events are immutable facts, commands are retryable, consumers are idempotent, and human gates remain explicit. |
| 2 | Curriculum compiler | Compile reviewed YAML/JSON source offline and deterministically; models may assist authors but are not required to produce a release. |
| 3 | Common Core | Keep the six-module sequence `CC-101` through `CC-106`; transfer evidence between modules and keep the workload, alternatives, and provider-substitution rules explicit. |
| 4 | Applied AI | Teach problem framing, data/evidence, architecture, evaluation, oversight, and operations through provider-neutral artifacts and a cumulative practicum. |
| 5 | Cybersecurity GRC | Build an eight-module risk-to-control-to-evidence pathway; prohibit live targets and keep risk acceptance, incidents, and public claims human-owned. |
| 6 | AI Governance | Use the lifecycle `inventory → assess → design → procure/build → operate → monitor → change → retire` and require an AI governance dossier for each system. |
| 7 | Cloud | Separate production, non-production, lab, and security boundaries; use least privilege, budgets, TTLs, backup/restore tests, and provider-neutral exports. |
| 8 | Assessment | Use two lanes: attendance produces the launch record; assessment evidence supports learning and quality but does not silently become a public competency credential. |
| 9 | Learner operations | Use separate lifecycle, attendance, submission, support, credential, and alumni status axes with pseudonymous IDs and granular consent. |
| 10 | Instructor experience | Generate one immutable release packet and one human task queue; automate preparation, routing, drafts, reminders, and evidence assembly while retaining approval authority. |
| 11 | Virtual delivery | Treat each session as a versioned product with live, asynchronous, text-first, and alternate-format paths; store UTC and render learner-selected IANA time zones. |
| 12 | Safe labs | Use a profile-driven lab factory with disposable, least-privilege, time-limited, cost-bounded environments, synthetic/public data, deny-by-default egress, and teardown evidence. |
| 13 | Provider adapters | Keep model, cloud, storage, collaboration, communications, video, and credential providers behind ports with structured task contracts, redaction, fallback, and deterministic mocks. |
| 14 | Data and privacy | Use an Ontario-primary Canada-wide control baseline with P0–P4 data classes, minimal collection, restricted sensitive-support handling, provider inventories, retention, deletion, and correction events. |
| 15 | Credentials | Launch with an attendance/participation record only; freeze the attendance policy per cohort, require human authorization, and make corrections append-only. |
| 16 | Accessibility and UX | Target accessible end-to-end learning and require equivalent outcomes across text, structured tables, audio/transcript, captions, live, asynchronous, mobile, and low-bandwidth paths. |
| 17 | Quality review | Maintain four evidence layers—Git, event ledger, evidence archive, and release/cohort manifest—with document control, complaints, internal audit, corrective actions, and hard release blockers. |
| 18 | Funding | Report at cohort/grant level using observed, bounded outcomes; track cash, in-kind, resource cost, access support, suppression, claim limitations, and sponsor boundaries. |
| 19 | Public launch | Ship a claims-safe public shell with a request-enrollment CTA first; enable live intake only after privacy, support, cohort, accessibility, and province-readiness gates pass. |

## Integration status

The foundation branch currently contains the first shared slice:

- project context, branch rules, 19-workstream contract, claims policy, and release gates;
- program, learner-event, module, provider-adapter, and release-manifest schemas;
- six Common Core module specifications;
- deterministic offline curriculum compiler and manifest validator;
- idempotent local enrollment-to-onboarding event-ledger reference slice;
- CI workflow for contract validation, compiler tests, generated release checks, and public-claims checks;
- quality, standards-reference, funding-evidence, and public-release documentation.

The following remain intentionally outside this foundation branch until their
contracts and approvals are ready:

- production learner portal and enrollment form;
- real AWS accounts, queues, databases, lab provisioning, and backups;
- live model, email, video, Google Drive, and credential adapters;
- real learner data, support contacts, retention approvals, and data-flow sign-off;
- public website deployment, analytics, domain, and monitored support;
- specialized Applied AI, Cybersecurity GRC, AI Governance, and Cloud module packs;
- live credential issuance or any stronger credential claim.

## First end-to-end pilot slice

Use a synthetic adult cohort and one Common Core module, preferably `CC-101`,
to prove:

1. deterministic release compilation;
2. enrollment idempotency and human review routing;
3. one virtual session with equivalent access paths;
4. a safe lab and offline alternative;
5. one provider-substitution test;
6. attendance-only credential eligibility with human approval;
7. one support or complaint route;
8. de-identified cohort and funding evidence;
9. release-manifest, accessibility, privacy, claims, and rollback evidence.

No real learner information or external production side effects belong in this
pilot replay.
