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

Install the agent runtime dependencies before live use:

```bash
python -m pip install -r runtime/requirements-agentic.txt
```

A live run additionally requires `OPENAI_API_KEY`. Secrets do not belong in the repository.

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

The test suite does not make live model calls. It checks graph execution, persistence, stop-and-resume behavior, domain specialization, provider contracts, command boundaries, and installed SDK construction.
