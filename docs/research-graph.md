# Canadian technical-work research graph

## Purpose

The research graph turns outside signals into structured evidence before they can influence a pathway. It is designed to answer questions such as which capabilities Canadian employers are asking Applied AI practitioners to demonstrate and whether those requirements are broad, current, and material enough to justify a pathway review.

## Workflow

```text
research question
  -> normalize scope
  -> Research Director source discovery
  -> Evidence Agent verification
  -> Labour Market Agent analysis
  -> Technology Agent analysis
  -> Capability Agent extraction
  -> Contradiction Agent challenge
  -> deterministic confidence score
  -> Curriculum Impact Agent recommendation
  -> human review when change is proposed
  -> record validated finding
```

The graph owns the sequence. Agents do not call each other freely or determine their own authority. Each worker receives only the state required for its node and must return a typed result.

## Agent boundaries

| Worker | Responsibility | Authority |
| --- | --- | --- |
| Research Director | Find a compact, high-quality source set | A1 research only |
| Evidence Agent | Verify sources and extract attributable claims | A1 research only |
| Labour Market Agent | Identify repeated role, geography, and work signals | A1 analysis only |
| Technology Agent | Separate durable capability changes from vendor noise | A1 analysis only |
| Capability Agent | Convert evidence into observable, tool-neutral capabilities | A1 analysis only |
| Contradiction Agent | Search for counterevidence and reasons to reduce confidence | A1 challenge only |
| Curriculum Impact Agent | Recommend whether a pathway review is warranted | A1 recommendation only |
| Programme accountable person | Decide whether a proposed pathway change may proceed | A3 human decision |

No research agent may authorize curriculum changes, publish claims, spend money, contact an employer, or modify a production system.

## Evidence record

A production research source should carry at least:

- source identifier;
- publisher;
- publication or observation date;
- retrieval date;
- geography;
- source type;
- claim supported;
- extracted capability or technology relationship;
- confidence and limitations;
- contradiction status;
- review state.

## Confidence

Confidence is computed by deterministic code from evidence count, source diversity, and the contradiction adjustment. The Contradiction Agent may reduce confidence but cannot increase it. This keeps a persuasive model response from becoming its own evidence score.

## Provider boundary

`runtime/openai_research_provider.py` implements the first live provider using the OpenAI Agents SDK. Hosted web search is limited to the workers that need external evidence. Outputs use Pydantic contracts. A free-form or malformed result fails closed before it can enter the next graph node.

The provider remains replaceable. The Research Graph contract, human gate, evidence model, and scoring rules do not depend on one model vendor.

## Curriculum boundary

The graph may recommend `increase`, `add`, `reduce`, `retire`, or `no_change`. Any recommendation that would alter a pathway stops at the curriculum review node. Approval permits the finding to proceed to the programme record; implementation remains a separate product or curriculum graph.

This separation prevents a transient hiring signal from silently rewriting learner requirements.
