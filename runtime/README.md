# Runtime reference implementations

The runtime folder keeps provider-neutral contracts executable before cloud services or model providers are allowed to create side effects.

## Control plane

`control_plane.py` is the enrollment-to-onboarding reference slice. It preserves versioned events, idempotency, privacy boundaries, and human-review routes.

## Graph kernel

`graph_kernel.py` adds the common execution primitive for autonomous work. The graph controls sequencing and authority. A node may be deterministic code, an agent, or a human decision. The kernel provides:

- versioned graph definitions;
- conditional edges;
- mutable execution state with immutable checkpoints;
- node evidence;
- evaluator gates;
- human approval interrupts;
- reviewed denial routes when a graph explicitly defines them;
- execution traces through the existing hash-chained event ledger;
- idempotent execution creation.

The graph kernel does not call a model by itself. Agent providers are injected through handlers. That keeps the work definition stable when models or vendors change.

## Research graph

`research_graph.py` moves a Canadian technical-work research question through source discovery, evidence verification, labour-market analysis, technology analysis, capability extraction, contradiction review, deterministic evidence scoring, and curriculum-impact analysis. A recommended pathway change stops at a human curriculum gate.

`openai_research_provider.py` supplies typed reasoning workers using the OpenAI Agents SDK. Only source discovery, evidence verification, technology verification, and contradiction review receive hosted web-search access. Confidence scoring remains deterministic code.

## Research domains

`research_domain_packs.py` defines the three launch research domains:

- `applied-ai-systems`
- `cybersecurity-grc`
- `ai-governance-assurance`

Each pack supplies its own research goal, source priorities, evidence rules, capability focus, technology focus, and contradiction tests. Domain packs guide evidence gathering and interpretation; they do not bypass the graph's evaluators or human curriculum gate.

## Durable research state

`research_store.py` persists one graph execution to SQLite, including state, checkpoints, human-review state, failure state, and the hash-chained event ledger. This is workflow memory, not semantic learner memory.

The default local database is `local-data/research.sqlite3`. `local-data/` is ignored by Git and is not a production data store.

`research_runner.py` supplies testable start and resume helpers. `run_research.py` is the command interface.

## Work Intelligence

`work_intelligence.py` converts validated research into traceable relationships between pathways, roles, capabilities, technologies, and sources. Research recommendations that would change a pathway must carry the human curriculum authorization record before those relationships can enter Work Intelligence.

## Capability graph

`capability_graph.py` defines the learner capability layer beneath modules and delivery content. Work Intelligence must first support the capability. A candidate capability then carries an observable description, target proficiency, evidence standards, prerequisites, and exact Work Intelligence provenance.

A capability becomes active only after a named human decision. Deterministic checks require evidence standards, provenance, and active prerequisites.

`run_capability_graph.py` provides command operations for evidence-backed candidate creation, activation, retirement, inspection, and pathway listing.

## Learning graph

`learning_graph.py` maps active capabilities to sprints, labs, missions, prerequisite edges, and mission evidence requirements. It validates active capability status, pathway ownership, accepted evidence-standard identifiers, mission coverage, and acyclic learning-unit dependencies before a candidate path can be stored.

A mission is the only unit type that can carry final capability evidence requirements. Sprints teach focused concepts and methods. Labs provide bounded practice.

`openai_learning_provider.py` supplies a typed Learning Graph Design Agent. It receives reviewed capability records and optional summaries of existing modules. It has no web-search tool and cannot create new capability or evidence-standard identifiers. Its output remains a candidate until deterministic validation and named human activation.

## Product Development graph

`product_development_graph.py` coordinates Product, Experience, UI Design, Copy, Brand, Engineering, Cloud, Security, Accessibility, and Quality agents through one versioned graph. Every specialist agent is A1 and has no production tool in this graph.

Deterministic release assurance reads structured reviews. Any release blocker routes directly to a blocked terminal record. A packet with no blocker stops at an A3 human release gate. Approval creates an implementation-authorization record; it does not deploy, merge code, publish copy, or mutate infrastructure.

## Business Operations graph

`business_operations_graph.py` routes explicit requests to Growth, Marketing, Partnerships, Operations, or Finance. The workstream is selected by deterministic request validation rather than model classification.

Analysis and preparation can finish directly when no blocker exists. External publication and external contact stop at A3. Financial commitment is restricted to Finance and stops at A4. Authorization is separate from execution.

`openai_business_operations_provider.py` supplies typed, tool-free workers.

`graph_execution_store.py` is the generic durable graph-state store used by multiple workflows.

## Learner Execution graph

`learner_progress_store.py` freezes an active learning-path version for a pseudonymous learner reference, tracks sprint and lab progress, records mission submission references, and stores human-accepted capability evidence.

`learner_execution_graph.py` uses deterministic evidence-readiness checks before model work. The model context excludes learner reference, cohort ID, submission ID, raw artifact references, attendance, support records, credentials, and learner submission content.

`openai_learner_provider.py` supplies three typed, tool-free A1 workers. They cannot grade, certify, remove a learner, or accept capability evidence.

A metadata-complete mission stops at an A3 human evidence-review gate. Acceptance records capability evidence through the learner progress store.

## Outcomes Intelligence graph

`outcomes_intelligence.py` creates a privacy-released programme snapshot from the learner progress store before model work begins. The launch policy aggregates by pathway and learning-path version, requires at least 20 learners in a released group, and suppresses binary cells where either side contains fewer than five records.

Secondary submission, unit-status, and capability metrics are also suppression-aware. The snapshot does not release learner references, instance IDs, cohort IDs, submission IDs, artifact references, assessor identities, or free-text assessment notes.

`outcomes_intelligence_graph.py` runs two tool-free A1 workers: Outcomes Analysis Agent and Outcomes Challenge Agent. A material signal can become a research question only after the challenge step preserves it. The graph cannot change curriculum or Work Intelligence.

The only registered handoff is to Research Intelligence for independent validation.

`outcomes_intelligence_runner.py` and `run_outcomes_intelligence.py` provide durable start/status operations through `graph_execution_store.py`.

## Runtime Assurance graph

`runtime_assurance.py` creates aggregate operational telemetry from the durable generic graph store and ResearchStore. It reports execution status, graph versions, node completion, human-review state, coarse failure categories, event counts, and source coverage.

The first release explicitly marks model token usage, monetary model cost, provider latency, tool-call latency, and trace sampling as unavailable rather than inferring them.

`runtime_assurance_graph.py` runs Runtime Reliability Agent and Runtime Control Agent. Both are tool-free A1 workers. They may recommend human investigation or prepare a Product Development remediation problem. They cannot disable agents, change authority or tools, change runtime limits, deploy code, mutate infrastructure, or alter production.

`runtime_assurance_runner.py` and `run_runtime_assurance.py` provide durable start/status operations.

## Agent identity and runtime policy

Every current model worker has a stable logical non-human identity in `agent_identity_registry.py`. The registry defines authority, model-data scope, exact tool scope, provider turn limit, per-execution call budget, zero automatic retries, and emergency disable controls. The SDK construction audit verifies all current workers without making model calls.

Install the agent runtime dependencies before live agent use:

```bash
python -m pip install -r runtime/requirements-agentic.txt
```

A live agent run additionally requires `OPENAI_API_KEY`. Secrets do not belong in the repository.

Start research inside one launch domain:

```bash
python -m runtime.run_research start \
  --domain applied-ai-systems \
  --question "What capabilities are Canadian employers asking Applied AI practitioners to demonstrate?"
```

Run privacy-preserving programme outcomes analysis:

```bash
python -m runtime.run_outcomes_intelligence start \
  --pathway-id applied-ai-systems
```

Run aggregate autonomous-platform assurance:

```bash
python -m runtime.run_runtime_assurance start
```

Read stored workflow status without a model call using the corresponding `status --execution-id` command.

Run the tests from the repository root:

```bash
python -m unittest discover -s runtime -p 'test_*.py' -v
```

The test suite does not make live model calls. It checks graph execution, persistence, stop-and-resume behavior, research specialization, Work Intelligence, Capability and Learning Graph authority, Product Development release authority, Business Operations A3/A4 routing, Learner Execution privacy, outcomes cell suppression, Runtime Assurance telemetry boundaries, cross-graph handoffs, agent identity/tool contracts, runtime budgets, command boundaries, and installed SDK construction.