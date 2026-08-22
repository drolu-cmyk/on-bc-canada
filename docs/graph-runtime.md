# Graph runtime

## Rule

Model the work as a graph. Use agents where judgment is required, deterministic services where the rule is known, and people where accountability cannot be delegated.

The graph is the stable contract. Models are replaceable workers inside selected nodes.

## Primitives

| Primitive | Meaning |
| --- | --- |
| Node | One bounded piece of work |
| Edge | An allowed transition |
| Route | A named decision outcome that selects an edge |
| State | Facts carried through one execution |
| Actor | Service, agent, or human responsible for a node |
| Evidence | Record that supports node completion |
| Evaluator | Check that decides whether output may continue |
| Approval | Human authorization required before continuation |
| Checkpoint | Recoverable state after a completed node |
| Trace | Ordered event record of what happened |
| Version | Exact graph contract used for the run |

## Authority

The first implementation uses these authority classes for autonomous work:

- A0 read;
- A1 analyse and recommend;
- A2 perform bounded, reversible actions;
- A3 consequential action requiring explicit authorization at launch;
- A4 high-consequence commitment that remains human-controlled.

Authority is attached to the actor occupying a node. It is not inferred from the model name.

## Failure boundary

A failed handler or failed evaluator stops the execution and emits a failure event. The runtime does not invent a recovery path. Retry, compensation, or escalation must be explicit in the graph definition so that failure behaviour remains reviewable.

## Provider boundary

The kernel has no OpenAI-specific types. OpenAI Agents SDK workers will implement graph handlers behind a narrow adapter. This lets the programme use agents, tools, sessions, guardrails, tracing, and human intervention without making the learning or operating graph dependent on one SDK.
