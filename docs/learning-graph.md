# Learning Graph

## Purpose

The Learning Graph turns active learner capabilities into a reviewed sequence of instruction, practice, work-like performance, and evidence.

It does not decide whether a capability matters. Work Intelligence supplies that evidence. It does not decide what proof is acceptable. The Capability Graph owns the evidence standard. The Learning Graph decides how a learner reaches and demonstrates the active capability.

```text
Work Intelligence
      ↓
active Capability Graph
      ↓
Learning Graph
      ↓
sprint → lab → mission
                  ↓
          accepted evidence standard
```

## Learning units

The first contract has three unit types.

### Sprint

Focused instruction required to understand or apply a capability. A sprint should be small enough to change without rewriting the whole pathway.

### Lab

Bounded practice where learners can make mistakes safely, inspect results, revise work, and build judgment before a work-like mission.

### Mission

A realistic technical problem that can produce evidence against an active capability standard. Final capability evidence is attached to missions rather than quizzes or content completion.

## Validation rules

A learning path cannot enter active use unless deterministic checks confirm that:

- every referenced capability is active;
- target capabilities belong to the pathway or shared common core;
- every evidence-standard identifier exists on the referenced capability;
- every target capability has mission evidence coverage;
- a mission only assesses capabilities it develops;
- unit prerequisites reference real units;
- prerequisite edges contain no cycles;
- the same path version is not already active or retired.

Input order does not control execution order. Units are stored first and prerequisite edges are stored afterwards, so graph structure determines the sequence.

## Agent role

The Learning Graph Design Agent receives only reviewed capability records, their evidence standards, and optional summaries of existing modules. It may compose a candidate sequence of sprints, labs, and missions.

The agent has no web-search tool because labour-market evidence has already been handled by the Research Graph. It cannot add new capability identifiers, create evidence standards, or activate a learning path. Typed output is converted into the deterministic Learning Graph contract and validated before human review.

## Human authority

Activation requires a named accountable human and a review note. Only one learning-path version may be active for a pathway at a time. A newer version waits until the active version is retired through a separate human decision.

This keeps learner-facing sequence changes reviewable while allowing agents to do much of the composition work.

## Relationship to existing modules

Current modules remain reusable delivery assets. A learning unit may retain source module identifiers such as `AAI-101` or `AAI-102`, but those module identifiers do not control capability meaning.

This allows the same active capability to be developed through a different sprint, lab, or mission as technology and delivery methods change, while the evidence standard stays stable until it is separately reviewed.

## Initial pathway use

The same Learning Graph contract will support:

- Applied AI Systems
- Cybersecurity GRC
- AI Governance & Assurance

The first live path should be generated only after the relevant research evidence has entered Work Intelligence and the target capabilities have been activated through the Capability Graph.
