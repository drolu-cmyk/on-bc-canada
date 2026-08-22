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

Install the optional agent runtime dependencies before live use:

```bash
python -m pip install -r runtime/requirements-agentic.txt
```

A live run additionally requires `OPENAI_API_KEY`. Secrets do not belong in the repository.

Run the tests from the repository root:

```bash
python -m unittest discover -s runtime -p 'test_*.py' -v
```

The test suite does not make live model calls. It checks the provider contracts with deterministic fixtures and constructs the installed SDK agents to catch integration drift.
