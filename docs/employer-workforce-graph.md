# Employer Workforce Graph

The Employer Workforce Graph analyzes an organization-level workflow to identify where AI may help, how work may change, what capabilities may become important, what can go wrong, and how to test adoption without turning the platform into an employee-scoring or automated HR system.

## Operating chain

```text
Organization-level workflow request
        ↓
Employer Workflow Agent
        ↓
AI Opportunity Agent
        ↓
Justified AI opportunity?
   ├─ no → no-change analysis
   └─ yes
        ↓
Workforce Impact Agent
        ↓
Employer Capability Demand Agent
        ↓
AI Adoption Risk Agent
        ↓
AI Adoption Pilot Agent
        ↓
AI Adoption Measurement Agent
        ↓
Deterministic boundary assurance
        ↓
Employer Workforce analysis packet
```

## Input boundary

`employer_workforce_context.py` accepts:

- a pseudonymous organization reference
- sector
- workflow name and purpose
- organization-level tasks
- role labels
- current tools
- process pain points
- constraints
- aggregate baseline metrics
- desired outcomes

The organization reference remains local and is removed before model calls.

The contract does not contain fields for employee identity, candidate identity, individual performance, compensation, promotion, discipline, termination, or protected characteristics. Obvious personal email addresses and phone numbers are rejected from input text.

Organizations should supply only workflow information they are authorized to process through the model layer.

## No forced AI use case

The AI Opportunity Agent may return no opportunities. If it does, it must explain why.

The graph then ends with `no_justified_ai_opportunity` instead of forcing an AI pilot. This allows the system to distinguish an AI problem from a process-definition, ownership, data-quality, or governance problem.

## Agent roles

### Employer Workflow Agent

Maps task friction, decision points, and human accountability. Findings must reference supplied task IDs.

### AI Opportunity Agent

Identifies bounded patterns such as assistance, retrieval, classification, generation, monitoring, bounded automation, or agentic coordination. Every opportunity must state the automation boundary and the evidence needed before adoption.

### Workforce Impact Agent

Describes task change for supplied role labels. It focuses on assistance, task shifts, new tasks, control requirements, and preserved human decisions. It cannot recommend individual hiring, termination, promotion, discipline, or performance scores.

### Employer Capability Demand Agent

Translates work changes into observable capability signals. These are organization-specific signals, not approved learner capabilities.

Every capability signal must carry `research_validation_required=true`.

### AI Adoption Risk Agent

Challenges the opportunities across privacy, security, reliability, human oversight, compliance, change management, cost, and data quality. Opportunity-specific risks must include a mitigation and stop condition.

### AI Adoption Pilot Agent

Designs one bounded and reversible pilot using supplied opportunity and task IDs. It must include success measures, stop conditions, and any required human approvals.

### AI Adoption Measurement Agent

Defines organization-level measures and decision rules. It may reference only aggregate baseline metric IDs supplied in the request. It cannot create individual worker productivity rankings.

## Capability signal handoff

Employer capability demand does not write to Work Intelligence.

The terminal assurance record explicitly sets:

```text
work_intelligence_write_authorized = false
capability_signals_require_research_validation = true
```

A capability signal that may affect the platform must return to Research Intelligence for broader Canadian evidence, contradiction review, confidence scoring, and human curriculum authorization before it can affect Work Intelligence or learner pathways.

## Authority

All Employer Workforce agents are A1.

The graph does not:

- deploy an AI system
- change a production workflow
- contact an employer or employee
- make an employee decision
- rank workers or candidates
- change curriculum
- write to Work Intelligence
- spend money

A later external or production action must use the appropriate authority-controlled graph.

## Persistence

`employer_workforce_runner.py` stores the graph and terminal analysis packet in `GraphExecutionStore`. Events use the `operational` privacy class. The pseudonymous organization reference is included only in the local packet, not model context.

## Command interface

Prepare a JSON file using organization-level fields, then run:

```bash
python -m runtime.run_employer_workforce start \
  --request-file employer-request.json
```

Starting the agents requires `OPENAI_API_KEY`.

Read a stored result without a model call:

```bash
python -m runtime.run_employer_workforce status \
  --execution-id <execution-id>
```

The output is analysis for accountable human use. It is not an automated employment or production decision.
