# Applied AI Training for Canada

Public-readiness foundation for a free, 100% virtual, Canada-wide training initiative operated by SozoRock Tech Inc Canada.

## Launch position

- Ontario-primary operating posture; Canada-wide virtual delivery.
- Durable learning across Applied AI, Cybersecurity GRC, AI Governance, and Cloud.
- Certificate of attendance only at launch.
- Tool-neutral curriculum with replaceable model and infrastructure providers.
- AWS Canada Central as the planned reference region for applicable program data.
- Google Drive as a sharing layer, not the only source of truth.

## Start here

1. Read [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md).
2. Read [`CONTRIBUTING.md`](CONTRIBUTING.md).
3. Review the [19 workstreams](WORKSTREAMS.md).
4. Run `python scripts/validate_specs.py` after installing `pyyaml` and `jsonschema`.
5. Run `PYTHONPATH=compiler/src python -m unittest discover -s compiler/tests -v`.
6. Run `python -m unittest discover -s runtime -p 'test_*.py' -v`.
7. Review `docs/mvp-backlog.md` before adding platform features.

This repository is a training and automation foundation. It does not claim accreditation, certification, endorsement, licensing, immigration eligibility, employment outcomes, or affiliation without an approved evidence record.
