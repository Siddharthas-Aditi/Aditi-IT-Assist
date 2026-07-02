# Dev Agent: AI Workflow & Agentic Systems

## Mandate
Evolve the LangGraph workflow, specialist agents, retrieval, tools, and MCP integrations
while preserving grounding, safety, and human-in-the-loop governance. This is the
highest-risk area of the codebase.

## Must-read context
`memory/known-risks.md` (#1–8), `memory/architecture-map.md` (AI stack),
`docs/architecture/multi-agent-support-architecture.md`, `agent-architecture.md`,
`chat-grounding-rules.md`, `retrieval-guardrails.md`, `troubleshooting-state-machine.md`,
`agent-tooling.md`, `mcp-integrations.md`, `agent-write-actions-and-tasks.md`,
`skills/backend/langgraph-workflows.md`, `skills/playbooks/rag-and-knowledge-workflow.md`,
`plans/agentic-ops-platform-evolution.md`.

## Method
1. Locate the deterministic enforcement point for the behavior (`subtype_classifier`,
   `grounding`, `confidence`, `escalation_policy`, `resolution_strategy`,
   tool `runtime`, MCP `profiles`). Change logic there, not in a prompt.
2. Keep specs declarative + versioned; bump `*_VERSION`. Degrade safely (keyword floor,
   deterministic fallback, KB-only on tool error).
3. Extend the matching eval in `backend/tests/data/*.yaml` and add a golden-conversation
   case for new chat behavior. Run the eval — never weaken it to pass.
4. Update the matching `agents/0X-*.md` and owning `docs/architecture/*`.

## Hard invariants (never break)
- Published-only, subtype-scoped retrieval; no cross-family KB mixing; no fabricated advice.
- Confidence can't be high without grounding.
- `handoff_context_sufficient` gates every human handoff/ticket; tickets are
  confirmation-gated + idempotent; escalation artifacts are immutable.
- Only declared/enumerated tools are callable; all calls go through `AgentToolRuntime`
  (allow-list → RBAC → approval → execute, audited). Write actions = human approval,
  0 unapproved executions. No uncontrolled self-learning.

## Flags
Keep new capability behind a `FEATURE_*` flag (default off) with safe fallback. Update
`memory/current-rollout-state.md`.
