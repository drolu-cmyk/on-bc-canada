# Shared project context

## Mission

Build a public-ready, Canada-wide, 100% virtual training operating system for Applied AI Training for Canada, operated by SozoRock Tech Inc Canada, with Ontario as the primary Canadian operating posture.

The system must make serious learning accessible while preserving evidence, safety, accessibility, privacy, portability, and future external-review readiness.

## Locked launch decisions

- Operator: **SozoRock Tech Inc Canada**.
- Program: **Applied AI Training for Canada**.
- Delivery: 100% virtual and Canada-wide.
- Primary operating province: Ontario.
- Regional context: British Columbia, including Abbotsford.
- Launch price: free.
- Launch credential: certificate of attendance only.
- Program status: training initiative, not a degree, diploma, licence, or accredited provider.
- Curriculum domains: Applied AI, Cybersecurity GRC, AI Governance, and Cloud.
- Pedagogy: fundamentals-first, problem-led, studio/lab, critique, evidence, and defense.
- Infrastructure: AWS Canada Central is the planned reference region for applicable program data.
- Collaboration: Google Drive is a sharing layer; it is not the only source of truth.
- Models: Codex, Grok, and Google models are replaceable adapters.

## Public-claims rule

No public copy may imply accreditation, certification, endorsement, affiliation, licensing, immigration eligibility, study-permit eligibility, employment, promotion, or competency unless an approved evidence record and appropriate authorization exist.

## Automation rule

Automate the standard path completely: intake, consent, onboarding, reminders, session packets, labs, attendance, submissions, feedback routing, certificates, quality reports, and funder reports.

Keep explicit human gates for safety incidents, accessibility exceptions, assessment appeals, credential decisions, policy changes, and external claims. The system automates their routing, evidence packet, deadlines, notifications, and audit trail.

## Branch strategy

- `main`: releasable source only; protected when repository permissions allow.
- Feature branch: `feat/public-readiness-foundation`.
- Follow-on branches: `feat/<bounded-scope>`, `fix/<bounded-scope>`, or `docs/<bounded-scope>`.
- One coherent purpose per branch.
- Never mix curriculum, infrastructure, policy, and unrelated formatting in one commit.
- Push every approved atomic commit as soon as it passes its local validation.
- Use one draft pull request for the release branch once write access is available.
- Do not merge or publish a production release without the release gates passing.

## Atomic commit format

```text
<area>: <imperative change>
```

Examples:

```text
docs: add shared project context
schema: define learner event envelope
curriculum: add Common Core module specifications
automation: add cohort reminder workflow
security: add provider data-flow checks
quality: add release evidence manifest
```

Each commit must leave the repository understandable and its validation state explicit.

## Provider rule

Provider-specific code belongs behind an adapter. The curriculum, learner record, evidence identifiers, event types, and export formats must remain usable if any model, cloud, collaboration, or credential provider changes.

