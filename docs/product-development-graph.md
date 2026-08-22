# Product Development Graph

## Purpose

The Product Development Graph coordinates specialist agents around one platform change while keeping release authority outside the model layer.

The graph begins with a defined product problem and ends in one of two states:

```text
product request
    ↓
product analysis
    ↓
experience analysis
    ↓
interface design
    ↓
copy review
    ↓
brand review
    ↓
engineering plan
    ↓
cloud review
    ↓
security review
    ↓
accessibility review
    ↓
quality plan
    ↓
release assurance
   ↙             ↘
blocked      human release review
                  ↓
        authorized for implementation
```

Authorization for implementation is not deployment. Repository changes, infrastructure mutation, spending, and production release remain separate controlled actions.

## Specialist workers

The first operating set includes:

- Product Agent
- Experience Agent
- UI Design Agent
- Copy Agent
- Brand Agent
- Engineering Agent
- Cloud Agent
- Security Agent
- Accessibility Agent
- Quality Agent

All specialist workers operate at A1 authority. They analyze, design, review, and recommend. They have no production tools in this graph.

## Product and experience boundary

The Product Agent defines the problem, primary users, work to be done, scope, non-scope, success signals, and assumptions that still need evidence.

The Experience Agent works from those decisions and defines key tasks, journey steps, information architecture, friction risks, and research gaps. It is instructed to design around work rather than conventional learning-management navigation.

The UI Design Agent converts the product and experience logic into an interface contract covering surfaces, hierarchy, components, states, responsive behavior, and design-system needs. This stage defines the interface before implementation begins.

## Copy and brand boundary

The Copy Agent blocks unsupported claims, school-like terminology, generic AI language, unclear calls to action, and copy that exceeds current evidence.

The Brand Agent reviews whether the interface and language feel credible, restrained, distinct, accessible, and appropriate for a Canadian applied-technology workforce platform rather than a generic learning portal or template technology product.

## Engineering and assurance boundary

The Engineering Agent identifies components, data and API changes, agent-runtime changes, implementation slices, migration risks, and rollback strategy.

The Cloud Agent reviews AWS-first operational concerns including least privilege, secrets, queues, persistence, cost exposure, observability, rollback, and failure modes.

The Security Agent reviews identity, authorization, tool permissions, prompt injection, data boundaries, dependency risk, destructive actions, and audit evidence.

The Accessibility Agent reviews core-task access across keyboard use, semantic structure, focus, labels, status communication, contrast, zoom, responsive behavior, reduced motion, screen readers, captions, transcripts, and low-bandwidth conditions.

The Quality Agent creates the release-focused test contract, including functional acceptance, regression, browser behavior, agent evaluations, permission tests, failure recovery, negative cases, and observability.

## Deterministic release assurance

Release assurance is software, not another model opinion. It reads the structured review status from copy, brand, cloud, security, accessibility, and quality. Any blocking status or release blocker routes the graph directly to a blocked release record.

Only a packet with no blocking review reaches the A3 human release-review node.

## Durable state

Product executions persist state, checkpoints, human-review state, release packets, and the hash-chained event ledger in a local SQLite reference store. A process can stop at the release gate and resume later without rerunning the specialist agents.

## Current limit

This graph stops at authorization for implementation. It does not yet write application code, alter Figma, mutate AWS, merge a pull request, spend money, publish copy, or deploy production services. Those actions require separate execution graphs with narrower tools and authority controls.
