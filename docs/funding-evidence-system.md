# Fundable-by-design evidence system

Fundability rests on a documented public problem, credible instructional method, safe operations, measurable outputs, meaningful learner outcomes, a cost model, and an improvement loop. Free delivery is an access feature. Evidence of access, quality, transfer, and stewardship forms the funding case.

## Evidence streams

| Stream | Example measures | Source events |
| --- | --- | --- |
| Reach | applications, provinces/territories, rural/urban mix where voluntarily collected, access barriers | enrollment and access events |
| Participation | orientation activation, attendance, session engagement, support requests | attendance, session, support events |
| Learning | artifact completion, rubric dimensions, revision rate, learner reflection | submission, review, resubmission events |
| Quality | accessibility coverage, response time, incident rate, unresolved exceptions | release, support, incident, QA events |
| Outcomes | confidence change, demonstrated capability, portfolio use, further study, work signal | pre/post surveys and follow-up events |
| Equity and inclusion | access support delivered, alternate-path use, barrier reduction | support and accessibility events |
| Stewardship | cost per learner, in-kind support, cloud cost, instructor time, cost avoided | finance and operations events |
| Sustainability | partner interest, repeatability, instructor pipeline, cohort capacity | partner, roster, cohort events |

## Metric definitions

```yaml
metrics:
  enrollment_rate:
    formula: confirmed_learners / eligible_applicants
  activation_rate:
    formula: learners_completing_orientation / confirmed_learners
  attendance_rate:
    formula: attended_required_sessions / required_session_seats
  artifact_completion_rate:
    formula: learners_submitting_required_artifacts / activated_learners
  completion_rate:
    formula: learners_meeting_published_completion_rule / activated_learners
  quality_pass_rate:
    formula: artifacts_meeting_published_rubric_threshold / reviewed_artifacts
  cost_per_learner:
    formula: approved_cohort_cost / activated_learners
  support_response_time:
    formula: median(first_response_at - request_received_at)
```

Metrics preserve denominator, date range, cohort, version, exclusions, and limitations. Demographic or sensitive data enters the system only with a defined purpose, voluntary choice, secure handling, and approved reporting logic.

## Cohort evidence package

Cohort closeout generates:

1. one-page impact brief;
2. theory of change and logic model;
3. program and curriculum summary;
4. learner access and inclusion summary;
5. outcome dashboard with definitions and limitations;
6. anonymized learner artifacts or sample evidence;
7. quality, safety, privacy, and incident summary;
8. budget, cost-per-learner, and in-kind contribution table;
9. continuity and scale model;
10. versioned data dictionary and methodology note;
11. operator, governance, and contact sheet;
12. evidence index for a read-only Google Drive data room.

## Funding pathways

- philanthropic grants for access, equity, digital skills, and workforce readiness;
- corporate sponsorship for responsible AI, cybersecurity, cloud literacy, and talent development;
- employer or association-sponsored cohorts;
- public or quasi-public workforce and skills programs, subject to eligibility;
- research, evaluation, or demonstration partnerships;
- in-kind credits, cloud support, subject-matter experts, and accessibility services.

Educational claims remain stable across funder audiences. The evidence system produces audience-specific views of verified records.

## Funder data-room controls

Every shared item carries:

- approved audience;
- privacy class;
- source cohort and date range;
- calculation method;
- version and owner;
- expiration/review date;
- link health check;
- redaction/de-identification status;
- claim limitations.

Google Drive provides the sharing layer. S3/versioned evidence objects and the repository remain the durable archive. A revoked or expired link becomes an event in the evidence ledger.
