# Architecture Map

Clean architecture, strictly layered. **Never skip a layer.**

## Backend layering

```
API route (app/api/v1/*)        ← thin; validates via Pydantic, delegates only
  → Service (app/services/*)    ← business logic, orchestration, injectable (DI)
    → Repository (app/repositories/*) ← ALL database access lives here
      → Model (app/models/*)    ← SQLAlchemy ORM
Schemas (app/schemas/*)         ← Pydantic v2 request/response DTOs
Core (app/core/*)               ← config (Settings), permissions, security
```

Hard rules: no DB queries in route handlers; no direct LLM calls outside
`app/services/llm_service.py`; all config via `app.core.config.Settings`; all I/O `async`.

## AI / agent stack (`backend/app/services/agents/`)

- **Workflow graph**: `app/workflows/` — `graph.py`, `state.py`, `nodes/`
  (orchestrator → triage → retrieval → resolution → escalation → ticketing +
  supervisor shadow node). Deterministic orchestration; LLM only where abstracted.
- **Chat service**: `agents/chat_service.py` — owns turn processing, context
  persistence across turns, ticket persistence (`_handle_ticketing`,
  `request_live_agent`), escalation-artifact creation (`_persist_and_queue`).
- **Deterministic enforcement points** (not prompt magic):
  - `subtype_classifier.py` — sets `DiagnosticContext.issue_subtype`.
  - `grounding.py::ground_results` — rejects cross-family KB, reranks subtype match.
  - `confidence.py` — composite confidence; no high score without grounding.
  - `escalation_policy.py::handoff_context_sufficient` — gates all human handoff.
- **Registry/supervisor**: `registry.py` (`AGENT_REGISTRY`), `supervisor.py`
  (pure-function routing). **Specialists**: `specialists/` (7 agents).
- **Tools/MCP (flagged)**: `tools/` (`TOOL_REGISTRY`, `AgentToolRuntime`),
  `mcp/` (`MCP_SERVER_REGISTRY`, sessions, typed tools), `tasks/` (background agents),
  `approvals.py`.
- **Knowledge**: `services/knowledge/` — `management.py`, `retrieval.py`,
  `indexing.py`, `lifecycle.py`, `ranking.py`; repo `repositories/knowledge_repository.py`.

## Request flow (employee chat, happy path)

```
POST /chat/message → ChatService.process_message
  → workflow graph (orchestrator/triage/retrieval/resolution)
    → grounded KB retrieval (published-only, subtype-scoped)
  → resolution steps returned  (confidence ≥ 0.8)
      OR escalation → offer ticket → (explicit yes) persist ticket
        → create transcript snapshot + escalation context → queue for specialist
```

## Live specialist flow

```
Employee waits in-window → GET /specialist-chat/active (poll)
Specialist: GET /specialist-queue → atomic claim → handoff-view (summary-first)
  → live chat (typing indicators both ways; 7-min idle warn + 2-min grace)
```

## Frontend layout

```
pages/ compose → features/ compose → components/ (+ components/admin, components/ui)
lib/api.ts        ← all HTTP, React Query
lib/permissions.ts ← UI gating; MUST mirror backend permission registry
store/            ← Zustand (small, focused; auth store persists tokens)
```

Workspaces by route prefix: `/support/*` (employee), `/operations/*` (agent),
`/dashboard/*` (admin/lead), `/audit/*` (admin + auditor).
Feature modules: `admin`, `agent-ops`, `chat`, `ingestion`, `knowledge`, `specialist-chat`.

## Config & flags

`.env` / `.env.example`. Feature flags (all default **off** in code):
`FEATURE_VECTOR_RETRIEVAL`, `FEATURE_AGENT_TOOLS`, `FEATURE_MCP_TOOLS`,
`FEATURE_AGENT_WRITE_ACTIONS`, `FEATURE_BACKGROUND_AGENTS`, `MCP_USE_MOCK` (dev true).
Full flag state → `memory/current-rollout-state.md`.

## Commands (see Makefile)

`make dev` (docker), `make dev-local`, `make db-migrate`, `make seed`,
`make test` / `test-backend` / `test-frontend`, `make lint`, `make typecheck`.

## Deeper docs

`docs/architecture/system-architecture.md`, `workflows.md`, `data-model.md`,
`multi-agent-support-architecture.md`, `agent-architecture.md`, and the many
feature-specific files under `docs/architecture/`. Index: `memory/feature-map.md`.
