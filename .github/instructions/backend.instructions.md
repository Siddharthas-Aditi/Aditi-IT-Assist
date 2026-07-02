---
applyTo: "backend/**/*.py"
---
# Backend (Python / FastAPI) instructions

Apply these on top of `.github/copilot-instructions.md`.

## Architecture
- Strict layering: **route → service → repository → model**. Never query the DB in a
  route handler. Never call an LLM outside `app/services/llm_service.py`.
- All I/O is `async`. All config comes from `app.core.config.Settings` — no hardcoding.
- Request/response use Pydantic v2 schemas in `app/schemas/`. Services are injectable
  via FastAPI `Depends`. Repositories own all SQLAlchemy access.

## Conventions
- Python 3.12+ type hints everywhere; `match` where it clarifies. 100-char lines. Ruff.
- structlog with structured context for logging. Files < 300 lines.
- Mandatory error handling on I/O and external calls. No bare `# type: ignore`
  (add a reason). TODOs: `# TODO(user): why - ref`.

## RBAC & audit
- Guard endpoints with `require_roles(...)` / `require_permissions(...)`; enforce the
  specific permission in the **service**. Keep employees isolated to their own data;
  hide internal notes/drafts/debug from employees.
- Audit every mutation via `AuditService` with before/after. Keep `core/permissions.py`
  the source of truth (frontend mirrors it).

## AI / agents (see `memory/known-risks.md`)
- Grounding, confidence, escalation policy, subtype classifier are deterministic pure
  functions — don't move that logic into prompts. Retrieval is published-only + subtype-scoped.
- Tickets persist only on explicit confirmation and are idempotent per session; the
  handoff gate must pass before any human handoff. Tool/MCP calls stay within declared
  allow-lists; write actions require approval (0 unapproved executions).

## Tests
- Add pytest coverage for new service logic and workflow nodes (mock the LLM). Run the
  relevant eval in `backend/tests/data/*.yaml` when touching agents/tools/MCP/retrieval.

Reference: `memory/architecture-map.md`, `skills/playbooks/backend-api-changes.md`,
`skills/backend/*`, `agents/dev/backend-architect.md`.
