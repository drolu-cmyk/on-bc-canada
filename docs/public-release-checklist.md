# Public-release checklist

This checklist defines a controlled public release of the training initiative.
It is an internal release standard, not a claim that the program is accredited,
certified, licensed, endorsed, or authorized by any external body.

## Source and build

- [ ] The release branch is based on the intended `main` revision.
- [ ] YAML and JSON source specifications pass schema validation.
- [ ] Every learning outcome maps to evidence and a rubric reference.
- [ ] The compiler produces the same hashes on two clean runs.
- [ ] The release manifest records source digest, compiler version, policy versions, and artifact hashes.
- [ ] Generated public artifacts contain no instructor-only notes or learner records.

## Learning and delivery

- [ ] The module sequence, workload, prerequisites, and participation rule are published.
- [ ] Every required session has live, asynchronous, text-first, and alternate-format paths.
- [ ] UTC instants and learner-selected IANA time zones are used for schedules.
- [ ] Captions, transcripts, visual descriptions, accessible documents, and low-bandwidth downloads are checked.
- [ ] A provider outage has a tested continuity activity and learner-safe notice.
- [ ] Learner support, complaints, withdrawal, correction, and accessibility routes are visible.

## Safety, privacy, and portability

- [ ] The data-flow register covers storage, processing, backups, support, communications, media, models, and sharing.
- [ ] AWS Canada Central language is limited to a planned reference region until the data-flow decision is approved.
- [ ] Learner labs use synthetic, public, or expressly authorized data only.
- [ ] Labs have least privilege, expiry, reset, cost limits, deny-by-default egress, and incident handling.
- [ ] Provider adapters record versions, policy decisions, usage, and transfer metadata.
- [ ] A deterministic mock provider and a no-model fallback pass the substitution test.
- [ ] Google Drive links have audience, privacy class, review/expiry, and revocation handling.

## Assessment and credential boundary

- [ ] Attendance is separate from artifact submission, assessment, and competency evidence.
- [ ] The launch certificate states participation/attendance only.
- [ ] Automation calculates and routes; a human authorizes credentials, appeals, exceptions, and public claims.
- [ ] Feedback is provisional until human review where it could affect a consequential learner decision.
- [ ] Corrections, withdrawal, revocation, and verification paths are tested.

## Claims and governance

- [ ] Public copy uses only approved operator, program, scope, price, delivery, and credential language.
- [ ] No public copy claims accreditation, certification, degree, diploma, licensing, endorsement, affiliation, immigration, study-permit, or employment outcomes.
- [ ] External claims have an evidence record, calculation, date range, limitation, audience, and approver.
- [ ] Standards are recorded as design references, never as proof of conformance or accreditation.
- [ ] Ownership, backup coverage, incident escalation, and review dates are documented.

## Pilot exit decision

The pilot may move from design to public enrollment only when all required
checks pass, the synthetic cohort replay succeeds, the data-flow and privacy
decisions are approved, and the content-release gate has a named human owner.
Any unresolved high-severity safety, privacy, accessibility, claims, or
credential issue blocks publication until it is resolved or explicitly accepted
through the appropriate human gate.
