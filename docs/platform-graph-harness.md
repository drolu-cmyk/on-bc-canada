# Platform Graph Harness

The Platform Graph Harness is the common control layer above GraphKernel workflows.

It keeps platform autonomy governable as more specialist agents and graphs are added. A model may propose which workflow should handle an objective, but deterministic code decides whether that graph, data boundary, requested effect, and handoff are allowed.

## Registered graphs

The registry contains six GraphKernel workflows:

| Work type | Graph | Human authority |
| --- | --- | --- |
| Research Intelligence | `canadian-work-research` | A3 for curriculum review |
| Product Development | `product-development` | A3 for release authorization |
| Business Operations | `business-operations` | A3 for external-action authorization, A4 for financial commitment |
| Learner Execution | `learner-execution` | A3 for capability-evidence acceptance |
| Career Mobility | `career-mobility` | none; learner guidance only |
| Employer Workforce | `employer-workforce` | none; organization analysis only |

The Capability Graph and Learning Graph remain reviewed state layers rather than GraphKernel execution workflows. They are not represented as execution graphs merely to make the registry larger.

## One authoritative registry

`platform_graph_registry.py` is the single registry for execution-graph contracts. It records:

- work type
- graph ID and expected graph version
- purpose
- runtime data classes
- model data classes
- forbidden data classes
- autonomous effects
- effects that may reach a human authorization gate
- effects a graph may execute after the registered authority boundary
- maximum agent and deterministic-service authority
- exact human gate nodes and authorities
- protected state-changing nodes
- required human authority for protected changes
- registered handoffs
- terminal record
- whether the graph executes an external effect
- whether live model execution requires an OpenAI API key

The registry loads each actual `GraphDefinition`. It does not copy graph topology into a second configuration system.

## Structural authority checks

`platform_graph_harness.py` checks the registry against the real graph definitions.

It verifies:

1. graph identity and registered version
2. model agents remain at or below their authority ceiling
3. deterministic services remain within their declared authority
4. actual human gates exactly match the registry
5. every structural path to a protected state change passes the required human authority or higher
6. handler names do not imply an undeclared external effect
7. model data is a subset of the graph runtime data boundary
8. forbidden data never appears in a model data contract
9. every authorization or consequential execution effect has the required human authority available
10. every handoff target is registered

A human node merely existing somewhere in a graph is not enough. The harness walks every path from the graph start to each protected state change.

## Protected state changes

Current protected changes include:

```text
product-development
finalize_release requires A3

business-operations
finalize_external requires A3
finalize_financial requires A4

learner-execution
accept_evidence requires A3
```

The current Product Development and Business Operations graphs create authorization records. They do not deploy, publish, contact an external party, or move money.

Learner Execution is different in one important respect: after the A3 evidence-review decision, deterministic code may write the accepted capability-evidence record to the learner progress store. The model never performs that write.

## Data boundaries

Every graph now declares two data boundaries:

`runtime_data_classes`
: Data the local graph runtime may need to operate.

`model_data_classes`
: The narrower subset that may be sent to model workers.

Examples:

- Learner Execution may use pseudonymous learner and evidence references locally, while its model workers receive only deidentified learning metadata and capability standards.
- Career Mobility may use a pseudonymous learner instance locally, while model workers receive deidentified accepted-capability metadata and Work Intelligence.
- Employer Workforce may hold a local organization reference, while model workers receive organization workflow and aggregate metric data only.

The common forbidden model boundary includes raw learner submissions, direct learner identifiers, individual employee records, payment credentials, and production secrets.

## Effects and dispatch modes

A dispatch request declares:

- work type
- mode
- requested effect
- data classes

Modes are:

`analyze`
: The graph may perform a registered autonomous analysis or preparation effect at A1.

`authorize`
: The graph may prepare a consequential decision but must stop at the registered human authority.

`execute`
: Allowed only for effects that the registry explicitly marks executable after the required graph authority boundary.

No current graph may execute external publication, external contact, a financial transaction, production mutation, an employment decision, or credential issuance.

This distinction prevents an authorization record from being mistaken for permission to perform the external action itself.

## Cross-graph handoffs

Handoffs are explicit rather than implicit.

Current registered handoffs include:

```text
Research Intelligence
  -> Work Intelligence
  completed validated finding only

Employer Workforce
  -> Research Intelligence
  organization-level capability signal only
  Research Intelligence must independently validate it

Learner Execution
  -> Career Mobility
  pseudonymous learner instance only after A3-accepted capability evidence exists
```

Two boundaries are intentional:

- Employer Workforce cannot write a capability signal directly into Work Intelligence.
- Learner Execution cannot pass raw learner submissions into Career Mobility.

An unregistered direct handoff fails closed.

## Routing

The safest route remains explicit deterministic routing:

```bash
python -m runtime.run_platform_graph_harness route \
  --work-type learner_execution
```

A richer dispatch check validates the data and effect boundary:

```bash
python -m runtime.run_platform_graph_harness dispatch \
  --work-type employer_workforce \
  --mode analyze \
  --effect analysis \
  --data-class organization_workflow \
  --data-class aggregate_metrics
```

Validate model context separately:

```bash
python -m runtime.run_platform_graph_harness model-context \
  --work-type career_mobility \
  --data-class deidentified_accepted_capability_metadata \
  --data-class work_intelligence
```

Validate a handoff:

```bash
python -m runtime.run_platform_graph_harness handoff \
  --source-work-type employer_workforce \
  --target-kind graph \
  --target-id canadian-work-research \
  --data-class organization_aggregate \
  --data-class capability_signal
```

## Optional Platform Orchestrator Agent

`openai_platform_orchestrator.py` adds a typed, tool-free manager that may propose the first registered work type for a metadata-only objective.

It is deliberately not the routing authority.

The manager:

- can return only one of the six registered work types
- receives objective metadata, declared data-class labels, mode, and requested effect
- has no graph-execution tools
- has no external-action tools
- cannot create a new work type, authority level, data class, or side effect
- cannot make a blocked route permissible

After the manager proposes a work type, `PlatformGraphHarness.validate_dispatch()` still makes the deterministic decision.

Live proposal requires `OPENAI_API_KEY`:

```bash
python -m runtime.run_platform_graph_harness propose \
  --objective "Assess whether this organization workflow has a justified AI opportunity." \
  --mode analyze \
  --effect analysis \
  --data-class organization_workflow \
  --data-class aggregate_metrics
```

## Deterministic evaluation cases

The harness includes a standing case matrix covering boundaries such as:

- public research analysis is allowed
- production mutation is blocked
- financial commitment authorization requires A4
- financial transaction execution is blocked
- raw learner submissions are blocked from model workflows
- learner capability-evidence write requires A3
- accepted capability metadata may support Career Mobility
- organization-level Employer Workforce analysis is allowed
- individual employee data is blocked

These cases run as part of the harness validation rather than depending on exact model prose.

## CI gate

The repository validation workflow runs:

```bash
python -m runtime.run_platform_graph_harness validate
```

The command validates structural graph contracts and the dispatch case matrix. It exits non-zero when a graph changes authority, bypasses a protected human gate, expands a model data boundary without registry review, introduces an undeclared handoff, or violates a standing dispatch case.

Inspect the full registry:

```bash
python -m runtime.run_platform_graph_harness manifest
```

## Why this layer matters

The registry is the point where platform autonomy becomes independently testable.

Models can change. Specialist agents can be replaced. Graphs can gain new nodes. None of those changes should silently expand authority, data access, or side effects. The harness makes those changes explicit and reviewable before they reach `main`.
