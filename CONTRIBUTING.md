# Contribution and release rules

## Before changing files

1. Read `PROGRAM_CHARTER.md`.
2. Identify the capability domain and file scope.
3. Check whether the change affects public claims, learner privacy, accessibility, safety, credentials, or jurisdiction.
4. Add or update the relevant schema, policy, test, and evidence record with the implementation change.

## Branches

Create a feature branch from `main`. Use a single scope in the branch name. Keep `main` releasable.

## Commits

Commits are small, atomic, and reversible. Each commit represents one reviewable decision. Do not use blanket staging commands. Stage confirmed paths only.

Every commit message uses the format:

```text
<area>: <imperative change>
```

## Pull requests

Each pull request contains:

- summary of the bounded change;
- files changed;
- validation run and result;
- privacy/security/accessibility impact;
- claims impact;
- rollback or correction path;
- scope boundaries and excluded changes.

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
