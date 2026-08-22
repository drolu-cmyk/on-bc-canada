# Business Operations Graph

## Purpose

The Business Operations Graph routes bounded operating work to one specialist while deterministic policy controls authority.

The first workstreams are:

- Growth
- Marketing
- Partnerships
- Operations
- Finance

The workstream is selected explicitly in the request. A model does not decide which department owns the work.

```text
operating request
      ↓
validated workstream + action class
      ↓
selected specialist
      ↓
operating assurance
   ↙        ↓         ↘
direct     A3          A4
            ↓           ↓
      human review   human review
            ↓           ↓
     external action  financial action
       authorization   authorization
```

A blocking specialist result bypasses the authority gates and ends in a blocked record.

## Action classes

`analysis` performs bounded reasoning and can finish without an external side effect.

`prepare` creates a bounded work package that remains inside the platform.

`external_publish` covers material intended for public release. It requires A3 human authorization.

`external_contact` covers communication to an employer, sponsor, partner, vendor, learner, or other outside party. It requires A3 human authorization.

`financial_commitment` covers authorization that could create a monetary obligation. It is restricted to the Finance workstream and requires A4 human authorization.

Authorization is separate from execution. This graph does not publish, send a message, transfer money, create a payment, sign an agreement, or alter an external account.

## Growth Agent

The Growth Agent examines acquisition and conversion as an evidence problem. It can define funnel stages, hypotheses, experiments, measurements, and evidence gaps.

It should prefer meaningful signals such as pathway interest, diagnostic completion, qualified registration, referral, and return engagement over raw traffic. It cannot manufacture demand or outcome claims.

## Marketing Agent

The Marketing Agent prepares audience, message, proof points, channels, content assets, and a concrete conversion action.

Supported evidence is kept separate from claims that still need evidence. Employment outcomes, salary statements, placement rates, accreditation claims, school status, and partnership claims cannot be inferred from marketing language.

Public release requires A3 human authorization.

## Partnership Agent

The Partnership Agent examines employer, sponsor, workforce, community, and institutional opportunities. It identifies mutual value, qualification signals, evidence gaps, preparation steps, and an outreach outline.

It cannot represent that a relationship exists unless that relationship is already supported by supplied evidence. External outreach requires A3 human authorization.

## Operations Agent

The Operations Agent examines processes such as registration, learner support, approvals, evidence review, partner intake, and platform administration.

It separates deterministic automation from judgment, identifies human controls and service measures, and records data boundaries. The agent has no learner-record mutation tools in this graph.

## Finance Agent

The Finance Agent works only from supplied financial inputs. It identifies assumptions, cost drivers, scenarios, guardrails, missing data, and decision implications.

Relevant cost drivers can include cloud services, model use, learner support, delivery, sponsored access, and employer work when those inputs are supplied.

The agent cannot invent monetary values, approve spend, transfer money, create a payment, or present an unevidenced scenario as an audited forecast. A financial commitment requires A4 human authorization before any separate execution process can begin.

## Deterministic authority policy

Authority is not selected by the specialist agent.

- analysis and preparation finish directly when no blocker exists;
- external publication and external contact route to A3;
- financial commitment routes to A4;
- incompatible workstream and action combinations fail closed;
- any specialist blocker routes to a blocked terminal record.

This policy makes the same authority rule apply even when the underlying model changes.

## Durable state

Business Operations uses the generic graph execution store. The store preserves execution state, checkpoints, human-review state, event history, and terminal records.

A process can therefore stop at A3 or A4 and resume later without regenerating the specialist analysis.

## Current limit

The operating agents have no tools for publishing, email, payments, banking, accounting mutation, CRM mutation, or learner-record mutation in this graph. Those capabilities can be added later through separate execution graphs with narrower identities, tools, and authority controls.
