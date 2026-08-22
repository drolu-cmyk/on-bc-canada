# Learner Capability Graph

## Purpose

The Capability Graph defines what a learner must be able to demonstrate. It sits between Work Intelligence and delivery content.

Work Intelligence answers whether a capability matters in Canadian technical work. The Capability Graph answers what that capability means, what must come before it, and what evidence is strong enough to verify it. Modules, labs, and missions can then teach or test the capability without becoming the source of truth for the capability itself.

```text
validated work evidence
        ↓
Work Intelligence
        ↓
capability candidate
        ↓
evidence standard + prerequisite review
        ↓
human activation
        ↓
active capability
        ↓
modules, labs, missions, and assessment
```

## Capability record

Each capability has:

- a stable capability identifier;
- one launch pathway;
- an observable work description;
- a target proficiency level;
- one or more evidence standards;
- zero or more prerequisite capabilities;
- Work Intelligence provenance;
- an accountable activation or retirement record.

The proficiency levels use the same vocabulary as the existing module specification: `explain`, `apply`, `analyze`, `evaluate`, `design`, and `defend`.

## Evidence standard

A capability cannot become active without a concrete evidence standard. An evidence standard identifies acceptable artifact types and the minimum level of performance. It may also require revision, a defense, or performance under a changed scenario.

The accepted artifact types remain aligned with the current module contract, including briefs, diagrams, memos, risk registers, control matrices, lab notebooks, evaluation reports, presentations, oral defenses, and portfolios.

A submitted artifact alone is not automatically proof of capability. Higher-risk or higher-judgment capabilities can require defense, revision, or a changed scenario so the system tests understanding rather than document production.

## Authority boundary

Research agents may establish evidence that a capability matters. They may help formulate a candidate definition. They cannot activate a learner capability.

Activation requires an accountable human decision and deterministic checks that:

- Work Intelligence provenance exists;
- at least one evidence standard exists;
- every prerequisite capability exists and is already active.

An active capability cannot be replaced by an agent-authored candidate. Retirement also requires an accountable human decision and is blocked while another active capability depends on it.

## Relationship to existing modules

Existing modules remain delivery content. Their outcomes and artifacts can map to capabilities, but a module title does not become a capability by itself.

For example, `AAI-101` can contribute evidence toward workflow analysis, data evidence assessment, and evaluation-boundary capabilities. `AAI-102` can combine several active capabilities in a practicum. This keeps the learner capability model stable even when delivery sequence, tools, or module packaging changes.

`CAPABILITY_DOMAINS.md` describes broad platform functions. The learner Capability Graph described here is a separate layer for observable learner performance.

## Initial operating rule

The first three pathways use the same graph contract:

- Applied AI Systems
- Cybersecurity GRC
- AI Governance & Assurance

Capabilities enter the graph from validated Canadian work evidence and reviewed evidence standards. The graph does not issue employment claims, licences, degrees, or professional status.
