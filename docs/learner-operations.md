# Learner operations

Applied AI Training for Canada uses one automated learner path across enrollment, onboarding, virtual delivery, evidence, support, attendance, and closeout. The path is Canada-wide and 100% virtual, with Ontario as the primary operating province.

## Learner path

1. A learner submits a data-minimized enrollment record.
2. The system records consent, validates capacity, and creates an invitation or waitlist outcome.
3. An accepted learner receives a workspace reference, orientation packet, and next action.
4. Each session produces a session packet, lab boundary, attendance record, and evidence route.
5. Submissions, support requests, accessibility routes, and corrections receive versioned status events.
6. Cohort closeout produces an attendance summary, quality packet, and evidence index.
7. A human credential authorizer reviews attendance evidence before a certificate-of-attendance record is issued.

Routine routing, reminders, artifact generation, status updates, retries, and evidence assembly use versioned automation contracts. Safety incidents, accessibility exceptions, assessment appeals, credential decisions, policy changes, and external claims retain human authorization.

## Data boundary

Applicable learner records use AWS Canada Central as the reference region. The controlled record classes are enrollment, attendance, support, and shared artifacts. Learner references are pseudonymous in event payloads. Google Drive is a sharing layer for approved generated artifacts; learner identity, attendance detail, support details, and submissions remain outside that sharing layer.

## Attendance evidence

Attendance uses a versioned rule and one of six statuses: present, partial, absent, alternate path, excused, or corrected. Each record identifies the learner reference, cohort, session, policy version, evidence references, privacy class, and retention class. Corrections use an operator-authorized route with a reason.

## Support and safety

Accessibility, technical, learning, safety, privacy, withdrawal, correction, and complaint requests receive a support case. Safety-critical cases route to the safety and security owner. The standard path records the event, owner, next action, evidence references, and status without placing unnecessary personal detail in the event ledger.

## Portable implementation

The repository contains JSON Schemas, YAML automation definitions, privacy controls, a deterministic compiler, and a local reference control plane. AWS services, Google Workspace, model providers, and credential services connect through replaceable adapters. The source contracts preserve event names, data boundaries, evidence identifiers, and export behavior across provider changes.
