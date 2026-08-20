# Automation capabilities

This document defines the automation contract for the training operating system. Each capability produces a learner-safe action, a versioned event, and an evidence record.

## Repository and release control

- GitHub stores versioned source and validation history.
- YAML and JSON specifications validate against their schemas.
- Public claims and human-gate policies remain release inputs.
- Generated manifests identify source commit, versions, owners, review dates, and artifact hashes.
- External publication occurs only after the configured release decision.

## Curriculum generation

- Module specifications validate against the module schema.
- Learning outcomes map to evidence artifacts and rubric criteria.
- A module specification generates a learner page, instructor run-of-show, lab brief, rubric, feedback form, evidence index, and release manifest.
- Generated outputs carry module version and source commit.
- Provider substitutions leave learning outcomes unchanged.

## Intake and learner workspace

- A data-minimized form captures enrollment information.
- Consent and policy acknowledgements carry version identifiers.
- Capacity rules route invitation, waitlist, and support tasks.
- The learner receives one workspace link and one next action.
- Withdrawal and correction requests create routed tasks.

## Cohort orchestration

- Cohort dates, time zones, session links, reminders, and deadlines derive from configuration.
- Late enrollment, absence, and rescheduling use explicit workflows.
- Messages are idempotent and traceable to a template version.
- Role-based views expose only permitted learner information.

## Virtual delivery and safe labs

- Weekly session packets generate automatically.
- Lab provisioning uses synthetic, public, or expressly authorized data.
- Sandbox accounts use least privilege and automatic expiry.
- Unexpected exposure, cost, or unsafe action creates an incident task.
- Accessibility and alternate participation paths appear before the activity.

## Assessment and evidence

- Submissions link to outcomes, rubric version, learner, module, and cohort.
- Model-assisted feedback carries a provisional status until its review path completes.
- Exception, appeal, resubmission, and missing-evidence states route automatically.
- Learners receive a clear status and next action.
- Quality reports reproduce calculations from event records.

## Attendance and credentials

- The attendance rule is versioned before cohort start.
- Attendance corrections use a controlled workflow.
- Credential issuance stops until the credential gate contains the required evidence.
- The launch record represents participation only.
- Learners receive portable exports and verification links without unnecessary data exposure.

## Quality and funding evidence

- Cohort closeout produces a quality report, outcome dashboard, budget summary, and funder data-room index.
- Every metric carries denominator, cohort, date range, version, and limitation.
- Public and funder claims route through the external-claim gate.
- Google Drive links carry audience, expiry, and privacy metadata.
- The operator exports the evidence package from the event ledger.

## Repository status

The repository contains the contracts, schemas, policies, deterministic compiler, validators, and local reference slices for these capabilities. Production services require approved deployment records, data-flow controls, and human authorization before learner data or external side effects enter the system.
