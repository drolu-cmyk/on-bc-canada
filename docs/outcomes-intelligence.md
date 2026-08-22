# Outcomes Intelligence

Outcomes Intelligence turns programme evidence into questions the platform can investigate without exposing learner-level records or allowing outcomes data to rewrite curriculum.

The launch design is intentionally conservative. It measures what the learner progress store can support, applies deterministic privacy suppression before any model call, and treats the surviving aggregate evidence as programme intelligence rather than proof of causation.

## Boundary

Outcomes Intelligence is not learner scoring, cohort ranking, demographic profiling, employment prediction, or credential assessment.

The first release aggregates by:

```text
pathway + learning-path version
```

It does not release cohort IDs to model workers and does not create individual-level output.

The model boundary excludes:

- learner references and instance IDs
- cohort IDs
- submission IDs
- artifact references
- assessor identities
- free-text assessment notes
- direct learner identifiers
- raw learner submissions

## Privacy release rules

`runtime/outcomes_intelligence.py` applies deterministic suppression before the graph starts.

The default launch thresholds are:

```text
minimum aggregate population = 20
minimum binary cell = 5
```

A pathway/version group with fewer than 20 learners is not released to the Outcomes Intelligence agents.

For a binary rate, both the positive cell and its complement must contain at least five records. A 1/20, 19/20, 0/20, or 20/20 rate is therefore suppressed rather than reported as a percentage.

The same principle is applied to secondary behaviour. Submission participation must clear the binary-cell rule before submission aggregates are exposed. Unit-status distributions are released only when the status cell and its complement within the unit kind clear the rule. Rare capability-evidence rates remain suppressed.

Suppression means unavailable evidence. Agents are explicitly instructed not to estimate suppressed values or treat them as zero.

## Released programme evidence

When privacy rules are satisfied, the snapshot may include:

- learner population for the pathway/version aggregate
- completion rate
- rate of learners with human-accepted capability evidence
- privacy-safe submission participation and attempt information
- privacy-safe unit-status rates
- privacy-safe capability-evidence rates

The snapshot contains a machine-readable `model_boundary` declaration that the graph verifies before either outcomes agent runs.

## Graph

`runtime/outcomes_intelligence_graph.py` is a GraphKernel workflow:

```text
load aggregate snapshot
        ↓
Outcomes Analysis Agent
        ↓
Outcomes Challenge Agent
        ↓
deterministic signal policy
        ↓
prepare research question when justified
        ↓
outcomes assurance
        ↓
final outcomes packet
```

Both model workers are A1 and tool-free.

The Outcomes Analysis Agent may identify a material programme-level signal. The Outcomes Challenge Agent then attempts to narrow or reject that interpretation by considering denominator problems, suppression, selection effects, path-version differences, observation windows, measurement mismatch, and alternative explanations.

A research signal is created only when the analysis reports a material signal and the challenge supports or narrows it.

## No direct curriculum loop

An outcomes signal is not a curriculum change request.

The only registered cross-graph handoff is:

```text
Outcomes Intelligence
        ↓
Research Intelligence
```

The payload is restricted to privacy-released aggregate outcomes and the resulting outcome signal. Research Intelligence must independently validate the question against current attributable evidence before Work Intelligence or curriculum can change.

Outcomes Intelligence cannot write Work Intelligence directly.

## Durable operation

Start a live outcomes analysis from the local learner progress store:

```bash
python -m runtime.run_outcomes_intelligence start \
  --pathway-id applied-ai-systems
```

The command first builds the deterministic privacy snapshot. Live agent work then requires `OPENAI_API_KEY`.

Read a stored execution without a model call:

```bash
python -m runtime.run_outcomes_intelligence status \
  --execution-id <execution-id>
```

The terminal record is `outcomes_packet`.

## What this does not yet measure

The initial implementation does not claim to measure causal learning gain, wages, placement, employer performance, long-term retention, or demographic equity. Those require separately governed measurement designs and appropriate evidence.

The purpose of this layer is narrower: make programme evidence usable without making the feedback loop unsafe.