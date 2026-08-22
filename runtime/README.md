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
- execution traces through the existing hash-chained event ledger;
- idempotent execution creation.

The graph kernel does not call a model by itself. Agent providers are injected through handlers. That keeps the work definition stable when models or vendors change.

## Research graph

`research_graph.py` is the first production-shaped workflow. It moves a Canadian technical-work research question through Research Director discovery, Evidence verification, labour-market analysis, technology analysis, capability extraction, contradiction review, deterministic evidence scoring, and curriculum-impact analysis. A recommended pathway change stops at a human curriculum gate.

`openai_research_provider.py` supplies the first live reasoning workers using the OpenAI Agents SDK. Workers use typed Pydantic outputs. Only source discovery, evidence verification, technology verification, and contradiction review receive hosted web-search access. Confidence scoring remains deterministic code.

## Research domains

`research_domain_packs.py` defines the three launch research domains:

- `applied-ai-systems`
- `cybersecurity-grc`
- `ai-governance-assurance`

Each pack supplies its own research goal, source priorities, evidence rules, capability focus, technology focus, and contradiction tests. These values travel inside the research state so every specialist worker receives the same domain boundary. Domain packs guide evidence gathering and interpretation; they do not bypass the graph's evaluators or human curriculum gate.

## Durable research state

`research_store.py` persists one graph execution to SQLite, including state, checkpoints, human-review state, failure state, and the hash-chained event ledger. This is workflow memory, not semantic learner memory. It allows a process to stop at a human gate and resume later without rerunning completed research nodes.

The default local database is `local-data/research.sqlite3`. `local-data/` is ignored by Git and is not a production data store.

`research_runner.py` supplies testable start and resume helpers. `run_research.py` is the command interface.

## Work Intelligence

`work_intelligence.py` converts validated research into traceable relationships between pathways, roles, capabilities, technologies, and sources. Research recommendations that would change a pathway must carry the human curriculum authorization record before those relationships can enter Work Intelligence.

## Capability graph

`capability_graph.py` defines the learner capability layer beneath modules and delivery content. Work Intelligence must first support the capability. A candidate capability then carries an observable description, target proficiency, evidence standards, prerequisites, and exact Work Intelligence provenance.

A capability becomes active only after a named human decision. Deterministic checks require evidence standards, provenance, and active prerequisites. Active or retired capability definitions cannot be replaced by an agent-authored candidate, and retirement is blocked while another active capability depends on the capability.

`run_capability_graph.py` provides command operations for evidence-backed candidate creation, activation, retirement, inspection, and pathway listing. Local reference data defaults under `local-data/` and does not belong in source control.

## Learning graph

`learning_graph.py` maps active capabilities to sprints, labs, missions, prerequisite edges, and mission evidence requirements. It validates active capability status, pathway ownership, accepted evidence-standard identifiers, mission coverage, and acyclic learning-unit dependencies before a candidate path can be stored.

A mission is the only unit type that can carry final capability evidence requirements. Sprints teach focused concepts and methods. Labs provide bounded practice. Every target capability must have mission evidence coverage before a path can reach human review.

`openai_learning_provider.py` supplies a typed Learning Graph Design Agent. It receives reviewed capability records and optional summaries of existing modules. It has no web-search tool and cannot create new capability or evidence-standard identifiers. Its output remains a candidate until `learning_graph.py` validates it and a named human activates the path.

`run_learning_graph.py` provides command operations for agent-assisted design, activation, retirement, inspection, and active-path lookup. Only one learning-path version may be active for a pathway at a time.

## Product Development graph

`product_development_graph.py` coordinates Product, Experience, UI Design, Copy, Brand, Engineering, Cloud, Security, Accessibility, and Quality agents through one versioned graph. Every specialist agent is A1 and has no production tool in this graph.

Deterministic release assurance reads the structured copy, brand, cloud, security, accessibility, and quality reviews. Any release blocker routes directly to a blocked terminal record. A packet with no blocker stops at an A3 human release gate. Approval creates an `authorized_for_implementation` record; it does not deploy, merge code, publish copy, or mutate infrastructure.

`product_development_store.py`, `product_development_runner.py`, and `run_product_development.py` provide durable stop-and-resume state and command operations.

## Business Operations graph

`business_operations_graph.py` routes explicit requests to Growth, Marketing, Partnerships, Operations, or Finance. The workstream is selected by deterministic request validation rather than model classification.

Analysis and preparation can finish directly when no blocker exists. External publication and external contact stop at A3. Financial commitment is restricted to Finance and stops at A4. Authorization is separate from execution.

`openai_business_operations_provider.py` supplies typed, tool-free workers. Growth focuses on funnel evidence and experiments. Marketing separates supported proof from claims that still need evidence. Partnerships evaluates mutual value and qualification. Operations separates deterministic automation from judgment and records data boundaries. Finance uses supplied numeric inputs, surfaces assumptions, and cannot move money or approve spend.

`graph_execution_store.py` is the first generic durable graph-state store. `business_operations_runner.py` and `run_business_operations.py` use it so A3/A4 work can survive a restart without regenerating specialist analysis.

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

Use `cybersecurity-grc` or `ai-governance-assurance` for the other launch pathways.

If the graph reaches the curriculum gate, the command returns the execution ID and approval state. Review the stored evidence, then resume with an accountable human decision:

```bash
python -m runtime.run_research resume \
  --execution-id <execution-id> \
  --approve \
  --approver-id <approved-operator-id> \
  --note "Approved for programme review."
```

Use `--deny` instead of `--approve` when the evidence should not proceed. Read stored status without a model call:

```bash
python -m runtime.run_research status --execution-id <execution-id>
```

Run the tests from the repository root:

```bash
python -m unittest discover -s runtime -p 'test_*.py' -v
```

The test suite does not make live model calls. It checks graph execution, persistence, stop-and-resume behavior, domain specialization, provider contracts, Work Intelligence, Capability Graph authority, Learning Graph sequence and evidence rules, Product Development release authority, Business Operations A3/A4 routing, command boundaries, and installed SDK construction.
