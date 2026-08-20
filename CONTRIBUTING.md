# Contributing and release rules

## Before changing files

1. Read `PROJECT_CONTEXT.md`.
2. Identify the bounded workstream and its write scope.
3. Check whether the change affects public claims, learner privacy, accessibility, safety, credentials, or jurisdiction.
4. Add or update the relevant schema, policy, test, and evidence record before adding implementation complexity.

## Branches

Create a feature branch from `main`. Use a single scope in the branch name. Keep `main` releasable.

## Commits

Commits are small, atomic, and reversible. A commit should represent one reviewable decision. Do not use blanket staging commands. Stage confirmed paths only.

Every commit message uses the format:

```text
<area>: <imperative change>
```

## Pull requests

Open one draft pull request for the public-readiness foundation. The pull request must contain:

- summary of the bounded change;
- files changed;
- validation run and result;
- privacy/security/accessibility impact;
- claims impact;
- rollback or correction path;
- follow-on work that is intentionally not included.

## Required checks

- YAML and JSON parse successfully.
- Schema validation passes.
- Public-claims scan passes.
- Module outcomes map to evidence and rubrics.
- Links and generated outputs are checked.
- Accessibility checks pass for learner-facing output.
- Safe-lab data and authorization rules pass.
- No secrets, credentials, personal learner records, or production data are committed.
- Provider substitution test passes for any provider adapter change.

## Release gates

Do not publish learner-facing material until the content-release gate is approved. Do not issue a credential until the credential gate has the required attendance evidence. Do not share a funder package until the external-claim gate has verified calculations, limitations, audience, and privacy class.

