# Workflow Agent Prompt

> Use this prompt when building or modifying the LangGraph workflow and its nodes.

---

## Your Role

You are implementing the multi-agent LangGraph workflow for Aditi IT Assist.
This is the core AI orchestration layer — it classifies issues, retrieves
knowledge, generates resolutions, and escalates to humans.

## Context Files (MUST READ)

- `AGENTS.md` — Complete agent system specification
- `agents/01-orchestrator.md` through `agents/06-ticketing.md` — Individual agent specs
- `skills/backend/langgraph-workflows.md` — Implementation patterns
- `skills/backend/llm-integration.md` — LLM abstraction
- `backend/app/workflows/state.py` — WorkflowState definition

## Critical Safety Rules

1. **Resolution Agent must NEVER fabricate steps** — Only use knowledge base content
2. **Escalation Agent must NEVER dismiss human requests** — Always escalate when asked
3. **Orchestrator routing must be deterministic** — No LLM calls in routing
4. **All nodes must log to audit_trail** — Every decision is traceable
5. **Confidence scores must be formula-based** — Not arbitrary values
6. **Maximum 10 turns per session** — Enforced in Orchestrator

## Node Implementation Checklist

When implementing a new node:
- [ ] Node function is `async def node_name(state: WorkflowState) -> dict`
- [ ] Returns ONLY modified state fields
- [ ] Includes `current_node` in return
- [ ] Appends to `audit_trail`
- [ ] Handles all failure modes (see agent spec)
- [ ] Has unit tests covering happy path + error cases
- [ ] Uses structlog for all logging
- [ ] LLM calls wrapped in try/except with fallback
- [ ] Respects boundaries defined in agent spec

## Testing Workflow Changes

```bash
# Run workflow-specific tests
pytest backend/tests/unit/test_workflows/ -v

# Test a full conversation flow
pytest backend/tests/integration/test_chat_flow.py -v
```

## Iterative Build Prompts

### Phase 1: Implement Triage
"Implement the triage_node function in backend/app/workflows/nodes/triage.py
following the spec in agents/02-triage.md. Include keyword fallback classifier
and LLM-based classification via LiteLLM."

### Phase 2: Implement Retrieval
"Implement the retrieval_node function following agents/03-retrieval.md.
Use pgvector for similarity search with keyword fallback."

### Phase 3: Implement Resolution
"Implement the resolution_node function following agents/04-resolution.md.
Use RAG pattern with confidence calibration formula."

### Phase 4: Implement Escalation + Ticketing
"Implement escalation_node and ticketing_node following their agent specs.
Escalation is deterministic. Ticketing uses LLM for summarization."

### Phase 5: Wire Graph
"Connect all nodes in graph.py with conditional routing following the
decision table in agents/01-orchestrator.md."
