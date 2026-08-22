# Platform Graph Harness

The Platform Graph Harness is the common control layer for GraphKernel workflows.

It answers five questions before a graph is trusted:

1. Is this the graph the registry says it is?
2. Are model agents still bounded to their declared authority?
3. Are deterministic services within their declared authority?
4. Do the actual human gates exactly match the registered human gates?
5. Does every path to a protected state change pass the required human authority first?

## Registered graphs

The first registry contains six GraphKernel workflows:

| Work type | Graph | Human authority |
| --- | --- | --- |
| Research Intelligence | `canadian-work-research` | A3 for curriculum review |
| Product Development | `product-development` | A3 for release authorization |
| Business Operations | `business-operations` | A3 for external-action authorization, A4 for financial commitment |
| Learner Execution | `learner-execution` | A3 for capability-evidence acceptance |
| Career Mobility | `career-mobility` | none; learner guidance only |
| Employer Workforce | `employer-workforce` | none; organization analysis only |

The Capability Graph and Learning Graph remain reviewed state layers rather than GraphKernel execution workflows. They are not represented as execution graphs merely to make the registry look larger.

## Registry contract

`platform_graph_registry.py` records for every execution graph:

- work type
- graph ID
- purpose
- model data classes
- maximum agent authority
- maximum deterministic service authority
- exact human gate nodes and authorities
- protected state-changing nodes
- required human authority for each protected state change
- terminal record
- whether the graph executes an external effect
- whether live model execution requires an OpenAI API key

The registry is executable. It loads the actual graph definition from the graph class rather than copying node topology into a second configuration file.

## Agent and service authority

Model agents are A1 in every registered graph.

Some deterministic services are allowed to be A2 when they record an outcome that has already passed the required human decision. Product release records and Business Operations authorization records use this pattern.

The harness rejects an agent whose authority exceeds the graph contract and rejects a deterministic service whose authority exceeds its declared graph limit.

## Exact human gates

A graph cannot silently gain or lose a human gate.

The harness compares all human nodes in the actual `GraphDefinition` with the graph contract. Node ID and authority must match exactly.

Examples:

```text
product-development
release_review = A3

business-operations
external_action_review = A3
financial_commitment_review = A4

learner-execution
human_assessment = A3
```

## Protected state changes

Some deterministic nodes change consequential platform state after a human decision. Those nodes are explicitly registered.

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

The harness walks every structural path from the graph start to each protected node. A graph fails if even one route reaches that node without first passing the required human authority or higher.

This is stronger than checking that a human node exists somewhere in the graph.

## External effects

The current registered graphs do not execute external effects.

Some graphs can create authorization records after human review, but authorization remains separate from execution. The harness also rejects handler names that appear to perform deployment, publication, sending, transfers, payments, messaging, or email when a graph declares that it executes no external effects.

## Deterministic routing

`PlatformGraphHarness.route()` resolves an explicit work type to its registered graph contract.

It does not ask a model to guess which graph should run.

Supported work types are:

```text
research_intelligence
product_development
business_operations
learner_execution
career_mobility
employer_workforce
```

An unknown work type fails closed.

## CI gate

The repository validation workflow now includes:

```bash
python -m runtime.run_platform_graph_harness validate
```

This runs before the wider runtime and graph test suite.

The command prints a machine-readable report for every registered graph and exits non-zero if any contract fails.

Inspect the registry:

```bash
python -m runtime.run_platform_graph_harness manifest
```

Resolve one explicit work type:

```bash
python -m runtime.run_platform_graph_harness route \
  --work-type learner_execution
```

## Why this layer matters

The graph registry is the point where autonomy becomes governable across the whole platform.

A model can change, a specialist can be replaced, and a graph can gain new nodes. The authority contract remains independently testable. If a future change gives an agent too much authority or creates a new path around a human gate, CI stops the change before it reaches `main`.
