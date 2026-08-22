# Work Intelligence Graph

## Purpose

The Work Intelligence Graph converts validated research into reusable relationships about technical work. Research answers a question. Work Intelligence preserves what that evidence means for roles, capabilities, pathways, and technology signals over time.

The first implementation uses SQLite tables shaped as entities and relationships. A dedicated graph database is not required until real traversal or scale requirements justify one.

## Initial entity types

| Entity | Meaning |
| --- | --- |
| Pathway | One public capability pathway such as Applied AI Systems |
| Role | A job or work role observed in evidence |
| Capability | Work a person can demonstrate |
| Technology | A technology signal that may affect how work is performed |

Research sources remain separate records so relationships can be traced back to evidence.

## Initial relationship types

| Relationship | Meaning |
| --- | --- |
| `develops_capability` | A pathway develops an evidence-backed capability |
| `requires_capability` | A role is directly associated with a capability in validated evidence |
| `signals_capability` | Labour-market evidence indicates a role-capability relationship |
| `has_technology_signal` | Research identifies a technology change relevant to a pathway |

Each relationship records the research execution, research graph version, confidence, supporting source IDs, status, and relationship metadata.

## Admission rule

Only a completed Research Graph execution with a validated finding can enter Work Intelligence.

If the research finding recommends a pathway change, the execution must contain the A3 human authorization record from the curriculum review node. A model recommendation without that record is rejected by deterministic code.

A `no_change` finding can be recorded without the curriculum review node because it does not alter learner requirements.

## Confidence

The relationship inherits the deterministic confidence score produced by the Research Graph. Model prose is not used as an independent confidence value.

## Idempotency

One research execution can be ingested once. Repeating the same execution returns the existing ingest result instead of duplicating relationships.

## Boundary

This graph does not decide curriculum, assign learner competency, rank applicants, or make employment decisions. It is an evidence-backed representation of work that other graphs may read under their own authority rules.
