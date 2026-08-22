# Career Mobility Graph

The Career Mobility Graph turns human-accepted capability evidence into learner-facing career guidance without exposing raw learner submissions or turning career support into an employer decision system.

## Operating chain

```text
Human-accepted capability evidence
        ↓
Reviewed capability definitions
        ↓
Work Intelligence role relationships
        ↓
Deterministic evidence alignment
        ↓
Deidentified career context
        ↓
Career Profile Agent
        ↓
Role Transition Agent
        ↓
Career Evidence Packaging Agent
        ↓
Interview Practice Agent
        ↓
Career Action Agent
        ↓
Deterministic boundary assurance
        ↓
Learner-facing career guidance packet
```

## What evidence alignment means

Evidence alignment measures overlap between capabilities with human-accepted evidence and capability relationships already stored in Work Intelligence for a role.

It is not:

- a probability of being hired
- an employer ranking
- a job guarantee
- a substitute for experience requirements
- a licensing conclusion
- an immigration or work-authorisation conclusion

A role enters the career context only when Work Intelligence already connects that role to at least one accepted capability.

## Data boundary

`career_intelligence.py` joins three reviewed sources:

1. human-accepted capability evidence from `LearnerProgressStore`
2. capability definitions and evidence standards from `CapabilityGraphStore`
3. role-to-capability relationships from `WorkIntelligenceStore`

The model context does not receive:

- learner reference or learner ID
- cohort ID
- learner path instance ID
- mission submission ID
- raw artifact references
- raw learner submission content
- reviewer identity
- attendance or support records
- credential records
- immigration information

The context contains capability IDs, capability names, reviewed target levels, accepted evidence-standard IDs and descriptions, role names, Work Intelligence capability relationships, evidence-alignment ratios, and research provenance identifiers.

## Deterministic role alignment

`CareerIntelligenceBuilder` discovers role relationships from Work Intelligence. It calculates matched and missing capability relationships before any model call.

For each role it records:

- required capabilities
- additional capability signals
- capabilities already supported by accepted learner evidence
- capabilities still missing from the accepted evidence set
- a deterministic evidence-alignment ratio
- Work Intelligence relation IDs
- source research execution IDs

The model may interpret those records for the learner but cannot invent another role and pass validation.

## Agent roles

### Career Profile Agent

Creates restrained positioning language from capabilities with human-accepted evidence. Every capability statement must map to an accepted capability ID. The agent is told explicitly that it has not inspected raw learner artifacts.

### Role Transition Agent

Explains the supplied role relationships and capability gaps. It cannot turn evidence alignment into a hiring score or introduce a role absent from Work Intelligence.

### Career Evidence Packaging Agent

Creates an evidence-card structure for each accepted capability-standard pair. The learner supplies the real artifact, context, outcomes, and claims.

### Interview Practice Agent

Creates practice questions for supplied role names and accepted capabilities. The questions emphasize reasoning, evidence, tradeoffs, failure handling, and technical judgment.

### Career Action Agent

Can recommend only learner-controlled action types:

- practice
- learning
- portfolio preparation
- interview practice
- employer research

Employer research means learning about organizations or roles. This graph does not apply, message, publish, submit, or contact anyone.

## Authority

All Career Mobility agents are A1.

No human gate is required for the guidance packet because the graph performs no external action and makes no employer-side decision.

A later workflow that publishes a profile, sends an application, contacts an employer, or shares learner evidence externally must use a separate authority-controlled graph.

## Persistence

`career_mobility_runner.py` stores the completed graph and career guidance packet in `GraphExecutionStore`. Graph events use the pseudonymous learner reference and cohort ID with the `learner_private` privacy class. Those identifiers are not supplied to the model workers.

## Command interface

Create career guidance after at least one capability evidence record has been accepted by a human:

```bash
python -m runtime.run_career_mobility start \
  --instance-id <learner-path-instance-id>
```

Starting the agents requires `OPENAI_API_KEY`.

Read a stored packet without a model call:

```bash
python -m runtime.run_career_mobility status \
  --execution-id <execution-id>
```

The graph does not contact an employer, submit a job application, publish a learner profile, or make a hiring, licensing, or immigration decision.
