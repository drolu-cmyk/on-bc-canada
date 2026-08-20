# Quality and future-review readiness

## Position

The pilot should be built as a small, evidence-producing educational organization from the first cohort. That does not make it accredited. It means that later review is supported by real records rather than reconstructed claims.

The quality system should be mapped to current educational-organization management expectations, distance-learning review expectations, accessibility standards, information-security controls, AI-management controls, and the actual provincial questions triggered by the offer. The register in `docs/standards-register.md` is the source for review anchors and revision dates.

## Evidence domains

| Domain | Required evidence | Automated capture |
| --- | --- | --- |
| Mission and governance | purpose, scope, operator, roles, decision rights, conflicts, change log | release manifest, approvals, policy versions |
| Curriculum | program outcomes, module outcomes, workload, prerequisites, sequence, standards map | schema validation, outcome alignment, content build |
| Learning delivery | session plan, learner access, labs, alternative paths, support route | generated run-of-show, link checks, accessibility checks |
| Assessment | rubric, evidence criteria, feedback, moderation, appeals, resubmission rule | rubric version, submission events, review queue |
| Learner support | intake, orientation, accessibility, communication, complaints, withdrawal | timestamped support and workflow events |
| Faculty and operations | instructor role, qualifications, onboarding, substitution, continuity | roster, role record, generated briefing, incident log |
| Security and privacy | data map, provider inventory, permissions, retention, deletion, incident response | configuration checks, access logs, control evidence |
| Credentials and records | attendance rule, verification, record number, correction/withdrawal path | event-derived status, signed record, verification endpoint |
| Effectiveness | learner feedback, outcomes, completion, artifact quality, improvements | de-identified dashboard, decision log, corrective actions |
| Financial stewardship | budget, cost per learner, in-kind support, vendor costs, continuity reserve | ledger imports, approved assumptions, report snapshots |

## Quality cycle

```text
plan -> build -> run -> collect evidence -> review -> improve -> release
```

The release process should block publication when a module has no measurable outcomes, no evidence artifact, no accessibility path, no safe-lab rule, or no substitution test. It should also block claims that cannot be tied to evidence.

## External reference points

- [ISO 21001:2025](https://www.iso.org/standard/21001) — educational organizations management systems, including learner-centred, inclusive, distance, and lifelong learning contexts.
- [DEAC Accreditation Handbook](https://www.deac.org/seeking-accreditation/the-deac-accreditation-handbook/) — a distance-education review reference emphasizing institutional responsibility, evidence, multi-source review, documentation, and continuous reporting.
- [WCAG 2.2 Recommendation](https://www.w3.org/WAI/standards-guidelines/wcag/) — accessibility requirements for digital learning content and services.
- [ISO/IEC 27001:2022](https://www.iso.org/standard/27001) — information-security management system reference.
- [ISO/IEC 42001:2023](https://www.iso.org/standard/42001) — AI-management system reference for responsible AI operations.
- [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework) and [NIST CSF 2.0](https://www.nist.gov/cyberframework) — practical risk and cybersecurity outcome references.

These are design anchors. The program must not state that it is certified, accredited, endorsed, or authorized merely because its internal controls are mapped to a reference.

## Ontario and BC review triggers

The operator should maintain a jurisdiction decision record before changing the offer. At minimum, review the current official materials for:

- Ontario career-college registration and program-approval triggers;
- Ontario exemptions and their conditions, if any are relevant;
- BC program-approval and private-training thresholds;
- advertising and credential language;
- tuition, refunds, student protections, complaints, and records;
- whether a future designation, international-student pathway, or financial-aid pathway changes the analysis.

Current official anchors include [Ontario’s career-college compliance notices](https://www.ontario.ca/page/career-college-compliance-notices), [Ontario’s third-party-funded vocational-program directive](https://www.ontario.ca/page/policy-directive-exemption-vocational-programs-funded-third-party), [BC PTIRU regulatory standards](https://www.privatetraininginstitutions.gov.bc.ca/quality-standards), and [BC’s informed-student guidance](https://www.privatetraininginstitutions.gov.bc.ca/index.php/students/be-an-informed-student). These pages are not a substitute for Canadian legal or regulatory advice.

## Accreditation-ready document room

Google Drive may expose a read-only sharing layer, but every folder should be generated from a release manifest:

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

Every file should carry: document ID, version, owner, approval state, effective date, review date, source commit, and privacy class.

