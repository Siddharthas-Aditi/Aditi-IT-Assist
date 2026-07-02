# AGENTS.md — Backend (Python / FastAPI)

Scope: everything under `backend/`. Read the root `AGENTS.md` and `CLAUDE.md` first;
this file adds backend-local rules. Deeper context: `../memory/architecture-map.md`,
`../memory/domain-model.md`, `../memory/known-risks.md`.

## Layering (never skip)
`api/v1/*` (thin routes) → `services/*` (logic, injectable) → `repositories/*` (all DB)
→ `models/*`. Pydantic v2 DTOs in `schemas/*`. Config via `core/config.Settings`. Never
query the DB in a route; never call an LLM outside `services/llm_service.py`.

## Rules
- Python 3.12+ type hints; `async` for I/O; structlog; 100-char lines; files < 300 lines.
- Enforce RBAC (`require_roles`/`require_permissions`) in **services**; keep employees
  isolated to their own data; hide internal notes/drafts/debug.
- Audit every mutation (before/after). No hardcoded secrets/config. Error-handle all I/O.
- AI-sensitive code (`services/agents`, `workflows`, `services/knowledge`): keep grounding,
  confidence, escalation-gate, tool/approval logic deterministic — see the invariants in
  `../memory/known-risks.md` and `../.github/instructions/ai-workflows.instructions.md`.

## Working method
Build model → schema → repository → service → route → test. Add pytest coverage; run the
matching eval in `tests/data/*.yaml` for agent/tool/MCP/retrieval changes. Migrations:
`make db-revision`, next id after `009`, always with a tested `downgrade`.

## Validate before done
`make lint-backend && make typecheck && make test-backend` (or `uv run ...`). Update
`../memory/domain-model.md` + owning `../docs/architecture/*` when contracts change.

## Blockers
Don't hack around a failing safety gate, fabricate data, or silence a type/lint error to
go green. Report the blocker + options. See `../docs/development/engineering-workflow.md`.
