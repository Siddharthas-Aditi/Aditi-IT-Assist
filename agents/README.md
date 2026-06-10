# agents/ — Agent Role Definitions

This directory contains detailed specifications for each agent in the
Aditi IT Assist multi-agent system.

## Directory Contents

| File | Agent | Description |
|------|-------|-------------|
| `01-orchestrator.md` | Orchestrator | Deterministic routing logic |
| `02-triage.md` | Intake & Triage | Issue classification & clarification |
| `03-retrieval.md` | Knowledge Retrieval | Vector/keyword search |
| `04-resolution.md` | Resolution | RAG-based step generation |
| `05-escalation.md` | Escalation | Handoff decision & summary |
| `06-ticketing.md` | Ticketing | Ticket/email draft creation |
| `07-learning.md` | Knowledge Learning | Async gap analysis |
| `08-copilot.md` | Human Support Copilot | Future: live agent assist |

## How to Read These Files

Each agent spec follows a consistent structure:

1. **Role** — What the agent does (one sentence)
2. **Interface** — Inputs, outputs, dependencies
3. **Algorithm** — Step-by-step processing logic
4. **Prompt Template** — The system prompt used (if LLM-powered)
5. **Failure Modes** — What can go wrong and how we recover
6. **Boundaries** — What the agent must NEVER do
7. **Tests** — What to validate in unit tests
8. **Dependencies** — External systems or other agents

## Relationship to Code

Each agent maps to a file in `backend/app/workflows/nodes/`:

```
agents/02-triage.md  →  backend/app/workflows/nodes/triage.py
agents/03-retrieval.md  →  backend/app/workflows/nodes/retrieval.py
agents/04-resolution.md  →  backend/app/workflows/nodes/resolution.py
agents/05-escalation.md  →  backend/app/workflows/nodes/escalation.py
agents/06-ticketing.md  →  backend/app/workflows/nodes/ticketing.py
```

The Orchestrator is implemented as conditional edges in `graph.py`, not as a node.

## Adding a New Agent

See `AGENTS.md` section "Adding a New Agent" for the full checklist.
