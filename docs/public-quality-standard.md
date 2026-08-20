# Public quality standard

This standard defines the evidence required for a public program release. It describes controls and publication boundaries; it does not represent accreditation, certification, licensing, endorsement, or authorization by an external body.

## Source and build

- YAML and JSON specifications pass schema validation.
- Every learning outcome maps to evidence and rubric criteria.
- The compiler produces identical hashes on clean repeated runs.
- The release manifest records source digest, compiler version, policy versions, and artifact hashes.
- Generated public artifacts contain no instructor-only notes or learner records.

## Learning and delivery

- The module sequence, workload, prerequisites, and participation rule are published.
- Every required session has live, asynchronous, text-first, and alternate-format pathways.
- UTC instants and learner-selected IANA time zones govern schedules.
- Captions, transcripts, visual descriptions, accessible documents, and low-bandwidth downloads pass checks.
- Provider outage has a tested continuity activity and learner-safe notice.
- Learner support, complaints, withdrawal, correction, and accessibility routes are visible.

## Safety, privacy, and portability

- The data-flow register covers storage, processing, backups, support, communications, media, models, and sharing.
- AWS Canada Central is the declared data reference region for applicable program data; provider and data-flow evidence governs publication language.
- Learner labs use synthetic, public, or expressly authorized data only.
- Labs use least privilege, expiry, reset, cost limits, deny-by-default egress, and incident handling.
- Provider adapters record versions, policy decisions, usage, and transfer metadata.
- A deterministic mock provider and a no-model fallback pass the substitution test.
- Google Drive links carry audience, privacy class, review/expiry, and revocation handling.

## Assessment and credential boundary

- Attendance is separate from artifact submission, assessment, and competency evidence.
- The launch certificate states participation and attendance only.
- Automation calculates and routes; a human authorizes credentials, appeals, exceptions, and public claims.
- Feedback remains provisional until human review when it affects a consequential learner decision.
- Correction, withdrawal, revocation, and verification paths are tested.

## Claims and governance

- Public copy uses approved operator, program, scope, price, delivery, and credential language.
- Public copy excludes accreditation, certification, degree, diploma, licensing, endorsement, affiliation, immigration, study-permit, and employment outcome claims.
- External claims carry an evidence record, calculation, date range, limitation, audience, and approver.
- Standards appear as design references, never as proof of conformance or accreditation.
- Ownership, backup coverage, incident escalation, and review dates are documented.

## Publication decision

Public enrollment opens when the configured checks pass, the synthetic cohort replay succeeds, data-flow and privacy decisions are approved, and the content-release gate has a named human owner. An unresolved high-severity safety, privacy, accessibility, claims, or credential issue blocks publication until resolution or documented human acceptance.
