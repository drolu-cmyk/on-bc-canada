# Automation MVP backlog

This is the build order for the first operational release. Each epic produces a usable control-plane capability and evidence, not a disconnected feature.

## Epic 0 — Repository and release control

Acceptance:

- authorized repository access works;
- validation workflow passes on pull requests;
- public-claims and human-gate policies are required inputs;
- generated release manifests identify source commit, versions, owners, and review dates;
- no external publish or push occurs without an approved release decision.

## Epic 1 — Curriculum compiler

Acceptance:

- module YAML validates against the schema;
- outcomes map to evidence artifacts and rubrics;
- one module spec generates learner page, instructor run-of-show, lab brief, rubric, and feedback form;
- generated outputs carry module version and source commit;
- changing a provider name does not change the learning outcome.

## Epic 2 — Intake, consent, and learner workspace

Acceptance:

- learner submits one data-minimized form;
- consent and policy acknowledgements are versioned;
- capacity and readiness rules create invitation, waitlist, or support tasks;
- learner receives one workspace link and a clear next action;
- withdrawal and correction requests create routed tasks.

## Epic 3 — Cohort orchestration

Acceptance:

- cohort dates, time zones, session links, reminders, and deadlines are generated from configuration;
- late enrollment, absence, and rescheduling follow explicit workflows;
- all messages are idempotent and traceable to a template version;
- the instructor sees only the learner information permitted for the role.

## Epic 4 — Virtual delivery and safe labs

Acceptance:

- weekly session packet is generated automatically;
- lab provisioning uses synthetic/public/authorized data only;
- sandbox accounts are least-privilege and disposable;
- unexpected exposure, cost, or unsafe action creates an incident task;
- accessibility and alternative participation paths are shown before the activity.

## Epic 5 — Assessment and evidence

Acceptance:

- submissions are linked to outcomes, rubric version, learner, module, and cohort;
- model-assisted feedback is marked provisional until the configured review path is complete;
- exception, appeal, resubmission, and missing-evidence states are automated;
- learner receives a clear status and next action;
- quality reports can reproduce the calculation from event records.

## Epic 6 — Attendance and credentials

Acceptance:

- attendance rule is versioned before cohort start;
- attendance events can be corrected through a controlled workflow;
- certificate issuance is blocked until the credential gate has the required evidence;
- the certificate records participation only at launch;
- learner can receive a portable export and verification link without exposing unnecessary data.

## Epic 7 — Quality and funder evidence

Acceptance:

- cohort closeout generates the quality report, outcome dashboard, budget summary, and funder data-room index;
- every metric includes denominator, cohort, date range, version, and limitation;
- public and funder claims route through the external-claim gate;
- Google Drive links are generated with audience, expiry, and privacy metadata;
- the operator can export the complete evidence package without rebuilding it manually.

## Definition of done for the pilot

The pilot is ready only when:

1. a synthetic cohort can complete the full journey without a manual instruction manual;
2. the instructor’s normal work is a generated task view plus exception decisions;
3. all six Common Core modules validate and generate their required outputs;
4. model and storage providers can be substituted in a dry run;
5. accessibility, privacy, safe-lab, claims, and human-gate checks pass;
6. a complete evidence and funder package can be generated from the event ledger;
7. a human operator has approved the release record.

