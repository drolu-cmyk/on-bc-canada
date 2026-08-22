# Applied AI Training for Canada

Applied AI Training for Canada is a free, 100% virtual training initiative operated by SozoRock Tech Inc Canada. The program serves learners across Canada, with Ontario as the primary operating province and British Columbia, including Abbotsford, as a regional context.

Public site: https://canada.sozorock.com

Legacy addresses `https://sozorock.ca` and `https://www.sozorock.ca` are retained as permanent redirects to the Canada site.

## Program

- Domains: Applied AI, Cybersecurity GRC, AI Governance, and Cloud.
- Delivery: Canada wide virtual instruction with accessible synchronous and asynchronous pathways.
- Price: CAD $0.
- Launch record: certificate of attendance and participation record.
- Curriculum: fundamentals first, problem led, evidence based, tool neutral, and designed for transfer across changing technologies.
- Public site privacy: The public site collects no learner data.
- Collaboration: Google Drive provides program resource sharing and collaboration.

## Learning design

The curriculum develops durable technical judgment through:

- computing, data, networks, security, and AI foundations before specialization;
- real world problems, structured cases, studio practice, and safe labs;
- evidence, critique, revision, reflection, and technical communication;
- accessibility across text, captions, transcripts, alternate formats, mobile, and low bandwidth paths;
- provider substitution so reasoning and evidence remain valid when a tool or model changes;
- human review for safety, accessibility exceptions, assessment appeals, credential decisions, and public claims.

## Public commitments

The program publishes only claims supported by current records. Participation is not represented as accreditation, a degree, diploma, professional licence, employment guarantee, immigration pathway, study permit pathway, endorsement, affiliation, or competency credential.

## Repository

- [Program charter](PROGRAM_CHARTER.md)
- [Capability domains](CAPABILITY_DOMAINS.md)
- [Public information site](site/index.html)
- [Contribution and release rules](CONTRIBUTING.md)
- [Program architecture](docs/program-architecture.md)
- [Graph runtime](docs/graph-runtime.md)
- [Canadian technical-work research graph](docs/research-graph.md)
- [Work Intelligence Graph](docs/work-intelligence-graph.md)
- [Learner Capability Graph](docs/capability-graph.md)
- [Specialization curriculum](docs/specialization-curriculum.md)
- [Automation capabilities](docs/automation-capabilities.md)
- [Learner operations](docs/learner-operations.md)
- [Public launch](docs/public-launch.md)
- [Standards register](docs/standards-register.md)
- [Quality standard](docs/public-quality-standard.md)
- [Funding evidence system](docs/funding-evidence-system.md)

## Validation

Run from the repository root:

```bash
python scripts/validate_specs.py
python scripts/validate_public_copy.py
python scripts/validate_site.py
python scripts/validate_deployment.py
PYTHONPATH=compiler/src python -m unittest discover -s compiler/tests -v
python -m unittest discover -s runtime -p 'test_*.py' -v
```

The repository contains versioned specifications, schemas, policies, deterministic release generation, and provider neutral reference implementations. Production learner data and external service credentials do not belong in source control.
