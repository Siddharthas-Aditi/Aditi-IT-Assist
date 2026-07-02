---
applyTo: "backend/app/{services/agents,workflows,services/knowledge}/**"
---
# AI / agent workflow instructions

The most safety-sensitive code in the repo. Apply on top of the backend instructions.
Read `memory/known-risks.md` (#1–8) and `docs/architecture/multi-agent-support-architecture.md` first.

## Non-negotiable invariants
- **No fabricated IT advice.** Retrieval is published-only and subtype-scoped.
  Cross-family KB is rejected by `grounding.py::ground_results`.
- **Deterministic enforcement, not prompt magic.** Keep logic in `subtype_classifier.py`,
  `grounding.py`, `confidence.py`, `escalation_policy.py`, `resolution_strategy.py`.
  Confidence can't be high without grounding.
- **Escalation gate**: `handoff_context_sufficient` must pass before any human handoff
  or ticket creation. Tickets persist only on explicit confirmation, idempotent per session.
- **Escalation artifacts are immutable**: no update path on `TranscriptSnapshot`; never
  mix post-escalation human↔human messages in; never dump raw chat into a ticket description.
- **Tools/MCP**: only declared, enumerated, versioned specs are callable; every call goes
  through `AgentToolRuntime` (allow-list → RBAC → approval → execute, all audited).
  Write actions are `approval=human` with **0 unapproved executions**.
- **No uncontrolled self-learning**: improvement signals feed human-reviewed KB candidates
  only. Nothing auto-publishes.

## Discipline
- Declarative + versioned: bump `*_VERSION` when changing a registry/contract; keep
  ranking weights summing to 1.0; degrade safely (keyword floor, KB-only on tool error).
- Update the matching `agents/*.md` when behavior changes, plus the owning
  `docs/architecture/*`. Add/extend the relevant eval in `backend/tests/data/`.

Reference: `agents/dev/ai-workflow.md`, `skills/playbooks/rag-and-knowledge-workflow.md`,
`skills/playbooks/chat-to-ticket-handoff.md`, `skills/backend/langgraph-workflows.md`.
