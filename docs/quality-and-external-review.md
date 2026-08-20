# Quality and external-review alignment

The program uses a documented quality system from its first cohort. The system records real instructional, learner-support, safety, privacy, accessibility, operational, and financial evidence.

## Evidence domains

| Domain | Required evidence | Automated capture |
| --- | --- | --- |
| Mission and governance | purpose, scope, operator, roles, decision rights, conflicts, change log | release manifest, approvals, policy versions |
| Curriculum | program outcomes, module outcomes, workload, prerequisites, sequence, standards map | schema validation, outcome alignment, content build |
| Learning delivery | session plan, learner access, labs, alternate paths, support route | generated run-of-show, link checks, accessibility checks |
| Assessment | rubric, evidence criteria, feedback, moderation, appeals, resubmission rule | rubric version, submission events, review queue |
| Learner support | intake, orientation, accessibility, communication, complaints, withdrawal | timestamped support and workflow events |
| Faculty and operations | instructor role, qualifications, onboarding, substitution, continuity | roster, role record, generated briefing, incident log |
| Security and privacy | data map, provider inventory, permissions, retention, deletion, incident response | configuration checks, access logs, control evidence |
| Credentials and records | attendance rule, verification, record number, correction/withdrawal path | event-derived status, signed record, verification endpoint |
| Effectiveness | learner feedback, outcomes, completion, artifact quality, improvements | de-identified dashboard, decision log, corrective actions |
| Financial stewardship | budget, cost per learner, in-kind support, vendor costs, continuity reserve | ledger imports, approved assumptions, report snapshots |

## Quality cycle

```text
define -> build -> deliver -> collect evidence -> review -> improve -> release
```

The release process blocks publication when a module lacks measurable outcomes, an evidence artifact, an accessibility path, a safe-lab rule, or a provider-substitution test. Claims without an evidence record also remain blocked.

## External references

- [ISO 21001:2025](https://www.iso.org/standard/21001) — educational organization management systems, learner focus, inclusive delivery, distance learning, and continual improvement.
- [DEAC Accreditation Handbook](https://www.deac.org/seeking-accreditation/the-deac-accreditation-handbook/) — distance-education review reference for institutional responsibility, student experience, faculty/administration, evidence, and reporting.
- [WCAG 2.2](https://www.w3.org/WAI/standards-guidelines/wcag/) — digital accessibility requirements for learning content and services.
- [ISO/IEC 27001:2022](https://www.iso.org/standard/27001) — information-security management system reference.
- [ISO/IEC 42001:2023](https://www.iso.org/standard/42001) — AI-management system reference for responsible AI operations.
- [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework) and [NIST CSF 2.0](https://www.nist.gov/cyberframework) — practical AI-risk and cybersecurity outcome references.

These references inform design and evidence. They do not confer certification, accreditation, endorsement, or authorization.

## Ontario and British Columbia

The operator records a jurisdiction decision for each offer change and reviews current official materials covering:

- Ontario career-college registration and program-approval triggers;
- Ontario exemptions and conditions;
- British Columbia program-approval and private-training thresholds;
- advertising and credential language;
- tuition, refunds, learner protections, complaints, and records;
- international-student and financial-aid implications.

Official anchors include [Ontario career-college compliance notices](https://www.ontario.ca/page/career-college-compliance-notices), [Ontario’s third-party-funded vocational-program directive](https://www.ontario.ca/page/policy-directive-exemption-vocational-programs-funded-third-party), [BC PTIRU regulatory standards](https://www.privatetraininginstitutions.gov.bc.ca/quality-standards), and [BC informed-student guidance](https://www.privatetraininginstitutions.gov.bc.ca/index.php/students/be-an-informed-student). These references do not replace Canadian legal or regulatory advice.

## Evidence room

Google Drive provides a read-only sharing layer generated from a release manifest:

```text
00_release_manifest/
01_legal_and_operator/
02_mission_governance/
03_program_and_curriculum/
04_learning_delivery/
05_assessment_and_moderation/
06_learner_support_and_accessibility/
07_faculty_and_operations/
08_privacy_security_and_ai_governance/
09_credentials_and_records/
10_effectiveness_and_improvement/
11_financial_and_funder_evidence/
```

Every file carries document ID, version, owner, approval state, effective date, review date, source commit, and privacy class.
