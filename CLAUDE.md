# CLAUDE.md - AI Agent Instructions for Aditi IT Assist

> **Purpose**: This is the master context file for AI coding assistants (Claude, Copilot, etc.)
> working on this codebase. Read this first before making any changes.

---

## Project Overview

**Aditi IT Assist** is an enterprise-grade internal IT service platform for Aditi Consulting.
It uses a multi-agent workflow (LangGraph) to intake employee IT issues, classify them,
retrieve relevant knowledge, guide troubleshooting, and escalate when needed.

**Enterprise capabilities include:**
- Role-based access control (employee, it_agent, it_lead, it_admin, security_auditor)
- Future-ready SAML SSO integration (pluggable auth providers)
- Enterprise ticket lifecycle with SLA tracking
- Remote assistance orchestration (Microsoft Remote Help integration ready)
- Analytics dashboards for IT leadership
- Audit logging and compliance controls
- Live agent support workflow

## Architecture Quick Reference

| Layer | Technology | Location |
|-------|-----------|----------|
| Backend API | Python 3.12+ / FastAPI / SQLAlchemy | `backend/` |
| AI Orchestration | LangGraph / LiteLLM | `backend/app/workflows/` |
| Auth & RBAC | JWT / Pluggable Providers / SAML stub | `backend/app/services/auth/` |
| Database | PostgreSQL 16 / pgvector | Docker (port 5432) |
| Cache | Redis 7 | Docker (port 6379) |
| Frontend | React 18 / TypeScript / Vite | `frontend/` |
| UI System | Tailwind CSS / shadcn/ui / Radix | `frontend/src/components/` |
| Package Mgmt | uv (backend) / npm (frontend) | `pyproject.toml` / `package.json` |

## Key Enterprise Patterns

### Authentication
- Pluggable provider: `app/services/auth/providers/base.py`
- Local auth: `app/services/auth/providers/local.py`
- SAML stub: `app/services/auth/providers/saml.py`
- Dependencies: `app/services/auth/dependencies.py`

### Authorization
- Role guards: `require_roles("it_agent", "it_lead", "it_admin")`
- Permission guards: `require_permissions("ticket:assign")`
- Type aliases: `CurrentUser`, `ITAgentUser`, `ITLeadUser`, `AdminUser`

### Data Isolation
- Employees see ONLY their own data (tickets, chats)
- Internal notes hidden from employees
- Audit logs restricted to admin/auditor roles

### Knowledge Management
- Structured, governed articles with a lifecycle: `draft → in_review → approved → published → archived`
- **The chat agent retrieves published articles only** (`KnowledgeRetrievalService`); drafts are never exposed to employee chat
- Three boundaries: KB management (`services/knowledge/management.py`), KB retrieval (`retrieval.py`), indexing (`indexing.py`)
- Per-action lifecycle permissions enforced in the service; coarse API gating via `require_permissions(knowledge:*)`
- Publish triggers indexing; archive removes from the index; both snapshot a version
- Docs: `docs/architecture/knowledge-management.md`, `docs/architecture/retrieval-and-indexing.md`, `docs/product/knowledge-workflow.md`, `docs/security/knowledge-access-control.md`

### Grounded Troubleshooting (chat agent)
- The chat agent must behave like a real IT analyst: identify the **issue subtype**, retrieve **only relevant** knowledge, track tried steps, **advance on failure**, and escalate when grounded help is exhausted. It must **never mix unrelated KB content** (this fixed the "inbox full → password reset / Windows Update / repeated steps" bug).
- Three non-prompt enforcement points:
  - **Subtype classification**: `app/services/agents/subtype_classifier.py` (deterministic; sets `DiagnosticContext.issue_subtype`, e.g. `mailbox-full`; vague → `None` → ask).
  - **Retrieval guardrail**: `app/services/agents/grounding.py` `ground_results` (wired in `workflows/nodes/retrieval.py`) — rejects cross-family articles, reranks the subtype match first, returns a kept/rejected trace.
  - **Composite confidence**: `app/services/agents/confidence.py` — confidence can't be high without grounding; loop/unresolved penalties apply.
- Loop control / tried-step memory: `DiagnosticContext.suggested_steps`/`failed_steps` + `workflows/nodes/resolution.py` `_build_progression` (present only NEW steps; never repeat a failed batch; escalate when exhausted). Context is persisted across turns by `ChatService`.
- KB rule: each article's `subcategory` MUST equal a real subtype from `subtype_classifier.known_subtypes(category)`; keep steps scoped to that subtype. No monolithic "all issues" articles.
- IT/admin-only `debug` trace on the chat response (employees never get it).
- **Escalation → ticket → live agent**: when grounded help is exhausted (or the user asks for a human), the agent *offers* to raise a ticket; a real ticket is persisted **only on explicit confirmation** ("Connect with a specialist" → `POST /chat/request-live-agent`, or typed "yes"), and always **before** the human handoff. Persistence is in the service layer (`ChatService._handle_ticketing` / `request_live_agent`), not the workflow nodes — `ticketing.py` only builds a draft + offer. Idempotent per session. See `docs/architecture/escalation-and-live-agent-handoff.md`.
- Docs: `docs/architecture/chat-grounding-rules.md`, `docs/architecture/retrieval-guardrails.md`, `docs/architecture/troubleshooting-state-machine.md`, `docs/architecture/escalation-and-live-agent-handoff.md`, `docs/development/chat-debugging-guide.md`, `docs/development/golden-conversations.md`

## Build Order (When Implementing Features)

1. Define data models and schemas first
2. Write service layer with proper abstractions
3. Create API endpoints that delegate to services
4. Build workflow nodes that compose services
5. Add frontend pages and wire to API
6. Write tests for the critical path
7. Update documentation

---

## Coding Guardrails

### Python (Backend)

```python
# ✅ CORRECT: Typed, async, service-layer pattern
@router.post("/chat/message", response_model=ChatResponse)
async def send_message(
    data: ChatMessageCreate,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    return await service.process_message(data)

# ❌ WRONG: No types, sync, logic in handler
@router.post("/chat/message")
def send_message(request):
    result = db.query(...)  # Never access DB in route handler
    return {"response": call_llm(result)}  # Never call LLM directly
```

**Rules**:
- Use Python 3.12+ features (type hints, match statements where appropriate)
- Follow clean architecture: routes → services → repositories → models
- All API endpoints must use Pydantic v2 schemas for request/response
- Use `async` for all I/O-bound operations
- Service classes must be injectable (dependency injection via FastAPI Depends)
- Never hardcode LLM provider calls — always go through the abstraction layer
- Use structlog for all logging with structured context
- Database queries go through repository layer, never in route handlers
- All environment config via `app.core.config.Settings` (Pydantic BaseSettings)
- Line length: 100 characters max
- Linter/formatter: Ruff

### TypeScript (Frontend)

```typescript
// ✅ CORRECT: Typed props, functional, uses design system
interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled = false }: ChatInputProps) {
  const [input, setInput] = useState('');
  return (/* JSX using Tailwind + shadcn */);
}

// ❌ WRONG: No types, class component, inline styles
export class ChatInput extends React.Component<any> {
  render() {
    return <div style={{color: 'red'}}>...</div>;
  }
}
```

**Rules**:
- Strict TypeScript — no `any` types unless absolutely necessary
- Components follow single responsibility principle
- API calls through dedicated `src/lib/api.ts` layer with React Query
- State management via Zustand stores (keep stores small and focused)
- All UI components use the design system tokens
- Pages compose features, features compose components
- Error boundaries around feature boundaries

### General Rules

- No giant files (>300 lines should be split)
- Meaningful variable/function names
- Docstrings on all service classes and complex functions
- Comments explain "why", not "what"
- TODO markers must include context: `# TODO(username): description - ticket/issue ref`

---

## No-Shortcuts Policy

| Rule | Consequence of Violation |
|------|--------------------------|
| Do NOT skip error handling | Silent failures, poor user experience |
| Do NOT use `# type: ignore` without comment | Hides real type errors |
| Do NOT commit commented-out code | Clutters codebase |
| Do NOT use `any` in TypeScript | Breaks type safety |
| Do NOT bypass service layer | Untestable, coupled code |
| Do NOT hardcode secrets or config | Security vulnerability |
| Do NOT skip input validation | Injection attacks, crashes |
| Do NOT fabricate knowledge in agents | Hallucinated IT advice to users |

---

## Testing Expectations

| Area | Framework | Coverage Target |
|------|-----------|----------------|
| Backend services | pytest (async) | 80%+ |
| Workflow nodes | pytest + mocked LLM | 100% of happy path |
| Frontend components | Vitest + RTL | Key interactions |
| API integration | pytest + httpx | Critical flows |

```bash
# Run tests
make test-backend       # Backend unit + integration
make test-frontend      # Frontend unit
make test-e2e           # Playwright E2E (needs backend running + seeded)
make test               # Everything
make lint               # Linting (both)
```

### Code-quality hooks (enabled via `make install-hooks`)
- **Post-edit (Claude Code)**: `.claude/settings.json` runs `scripts/claude-lint-file.sh` on each edited file — ESLint for frontend `.ts/.tsx`, Ruff for backend `.py`. Lint failures are surfaced back; fix them in the same turn rather than ignoring.
- **Pre-push (git)**: `.githooks/pre-push` gates pushes on frontend lint+typecheck+vitest and backend ruff+mypy+pytest (backend via `uv`). Bypass only with `git push --no-verify` / `SKIP_PREPUSH=1` when intentional.
- Frontend `lint` runs with `--max-warnings=0` — warnings fail. ESLint config: `frontend/.eslintrc.cjs`.

---

## Documentation Expectations

- Every new feature needs a doc update
- Agent changes require updating the corresponding `agents/*.md` file
- API changes require updating OpenAPI schemas (auto-generated from Pydantic)
- Workflow changes require updating `docs/architecture/workflows.md`
- New skills require a new `skills/**/*.md` file

---

## How to Safely Modify Code

1. **Read context first** — Check `agents/*.md` and `skills/**/*.md` for the area you're changing
2. **Check existing tests** — Understand expected behavior before modifying
3. **Make changes incrementally** — Small, focused commits with clear messages
4. **Run validation** — `make lint` and `make test` before considering work done
5. **Update docs** — If you changed architecture, update the relevant `.md` file
6. **Verify workflow** — If modifying the graph, trace the full path manually

---

## Implementation Status

> Last validated: 2026-06-19 — see `plans/phase1-hardening.md` for the full iteration log.

### ✅ Fully Implemented
| Area | Status | Notes |
|------|--------|-------|
| FastAPI backend | ✅ | All routes, CORS, lifespan + background scheduler |
| JWT Auth (local) | ✅ | Login, register, /me, logout, **/auth/refresh**, typed 401 error codes |
| RBAC (5 roles) | ✅ | `require_roles`, `require_permissions`, **typed specialist-chat + KB-promote permissions** |
| Ticket lifecycle | ✅ | SLA, assignment, events, isolation |
| LangGraph workflow | ✅ | 6 nodes + **supervisor shadow node** (Phase-1 dual-run mode) |
| Conversational intent classifier | ✅ | Hybrid LLM-first + keyword safety net; 11 typed intents; versioned |
| Multi-agent registry + supervisor | ✅ | Declarative AGENT_REGISTRY, 7 specialists, pure-function routing decisions, guardrails (handoff cap, loop detection, confidence floor) |
| Specialist agents (7) | ✅ | Outlook + Access/MFA + Zoom/Meetings + Intune + Sixth Sense + Hardware + Network/VPN. Shared `_progression` helper. |
| Knowledge retrieval | ✅ | Grounded published-only retrieval + citations; subtype-aware reranking |
| Knowledge Management | ✅ | Structured articles, lifecycle/governance, versioning, taxonomy, indexing, analytics |
| Knowledge Improvement Loop | ✅ | `KnowledgeCandidate` model + service; review-gated promotion; six signal sources |
| Controlled web fallback | ✅ | `ControlledWebResearchAgent`: registry opt-in, trust-tier filter, mandatory candidate creation, audit log |
| LLM integration | ✅ | LiteLLM abstraction, hybrid intent path, structural-validity guard on LLM picks |
| Remote support | ✅ | Session, consent, audit trail |
| Live IT Specialist Chat | ✅ | Dedicated tables, lifecycle state machine, **3-min idle timeout** (configurable), typed end reasons, full transcript persistence |
| Specialist Queue + My Assigned | ✅ | Atomic claim (DB-level), typed HandoffPackage v1.0, REST API, **frontend UI** wired and verified |
| Background scheduler | ✅ | Pure-asyncio loop in FastAPI lifespan; idle sweeper every 30 s |
| Analytics API | ✅ | Dashboard metrics, SLA, workload |
| Audit logging | ✅ | AuditEvent model + service; every specialist-chat transition audited |
| Session expiry handling | ✅ | Typed 401 error codes, single API interceptor, refresh-once mutex, proactive idle-tab logout, centralized redirect, `next=` open-redirect guard |
| Frontend routing | ✅ | Role-aware routes, guards |
| Frontend auth store | ✅ | Zustand persist, **refresh_token + tokenExpiresAt persistence**, idle-tab timer, session-expired event listener |
| Frontend specialist UX | ✅ | `LiveQueuePage`, `AssignedTicketsPage`, `LiveChatPage` — all polling-based, tsc + eslint clean |
| Docker compose | ✅ | Dev + prod targets, health checks |
| Alembic migrations | ✅ | 002…**008** (007=knowledge_candidates, 008=specialist_chat) |

### 🚧 Stubbed / Scaffolded (Not Yet Functional)
| Area | Status | Notes |
|------|--------|-------|
| SAML SSO | 🚧 Stub | Endpoints exist; IdP call is `pass` |
| pgvector search | 🚧 Stub | YAML keyword fallback in use |
| WebSocket chat | ❌ Phase 2 | HTTP polling currently; API shape supports drop-in upgrade |
| Knowledge Candidate review UI | ❌ Phase 2 | Backend model + service ready; SME UI deferred |
| Refresh-token rotation + denylist | ❌ Phase 2 | Single long-lived refresh token currently |
| Cross-tab BroadcastChannel logout | ❌ Phase 2 | Each tab runs its own idle timer |
| Human Support Copilot | ❌ Future | Spec in agents/08-copilot.md |
| Token blacklisting | 🚧 TODO | Redis key storage needed |
| Rate limiting | 🚧 Config | `RATE_LIMIT_ENABLED=true` (middleware stub) |

### 🔑 Seeded Dev Users (see `scripts/seed_enterprise.py`)
| Email | Password | Role |
|-------|----------|------|
| `employee@aditi.com` | `employee123` | employee |
| `agent@aditi.com` | `agent123` | it_agent |
| `lead@aditi.com` | `lead123` | it_lead |
| `admin@aditi.com` | `admin123` | it_admin |
| `auditor@aditi.com` | `auditor123` | security_auditor |

---
| Pydantic schemas | `backend/app/schemas/` |
| Service layer | `backend/app/services/` |
| Repository layer | `backend/app/repositories/` |
| LangGraph workflow | `backend/app/workflows/` |
| Workflow nodes | `backend/app/workflows/nodes/` |
| Workflow state | `backend/app/workflows/state.py` |
| Workflow graph | `backend/app/workflows/graph.py` |
| LLM abstraction | `backend/app/services/llm_service.py` |
| Knowledge base seed | `backend/app/knowledge_base/seed/` |
| Frontend pages | `frontend/src/pages/` |
| Frontend components | `frontend/src/components/` |
| API client | `frontend/src/lib/api.ts` |
| State stores | `frontend/src/store/` |
| Type definitions | `frontend/src/types/` |

---

## Agent Workflow Overview

```
User Message
    │
    ▼
┌─────────────┐
│ Orchestrator │ ← Deterministic routing (no LLM)
└──────┬──────┘
       │
       ▼
┌─────────────┐     clarification needed
│   Triage    │ ─────────────────────────→ User
│   Agent     │
└──────┬──────┘
       │ classified
       ▼
┌─────────────┐
│ Knowledge   │
│ Retrieval   │
└──────┬──────┘
       │ articles found
       ▼
┌─────────────┐     confidence >= 0.8
│ Resolution  │ ─────────────────────────→ User (with steps)
│   Agent     │
└──────┬──────┘
       │ confidence < 0.8 OR user requests help
       ▼
┌─────────────┐
│ Escalation  │
│   Agent     │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Ticketing  │ → Draft ticket/email → User approval
│   Agent     │
└─────────────┘
```

## Confidence Scoring

- Confidence > 0.8: Provide resolution directly
- Confidence 0.5-0.8: Provide resolution with disclaimer, offer escalation
- Confidence < 0.5: Escalate immediately

---

## Environment Setup

### Local Container (Docker Compose) — Recommended

```bash
# 1. Copy and configure environment (required — file is gitignored)
cp .env.example .env
# Edit .env if needed — defaults work for local dev without LLM

# 2. Build images and start all 4 services (postgres, redis, backend, frontend)
docker compose up --build

# Or in detached mode:
docker compose up --build -d

# 3. Seed dev users + knowledge base (first time only)
docker compose exec backend uv run python -m scripts.seed_enterprise

# 4. Verify everything is running
docker compose ps
# Expected: all services STATUS=Up (healthy)
```

**Service URLs once running:**
| Service | URL |
|---------|-----|
| Frontend (React/Vite) | http://localhost:5173 |
| Backend API (FastAPI) | http://localhost:8000 |
| API Docs (Swagger UI) | http://localhost:8000/docs |
| API Docs (ReDoc) | http://localhost:8000/redoc |
| Health check | http://localhost:8000/api/v1/health |

**Dev users (seeded by `seed_enterprise.py`):**
| Email | Password | Role |
|-------|----------|------|
| `employee@aditi.com` | `employee123` | employee |
| `agent@aditi.com` | `agent123` | it_agent |
| `lead@aditi.com` | `lead123` | it_lead |
| `admin@aditi.com` | `admin123` | it_admin |
| `auditor@aditi.com` | `auditor123` | security_auditor |

**Key `.env` notes for local container setup:**
- `LLM_API_KEY` can be left empty — the app falls back to keyword-based triage/resolution
- `POSTGRES_HOST`/`REDIS_HOST` in `.env` stay as `localhost`; docker-compose.yml overrides them to `postgres`/`redis` for the backend container
- `RATE_LIMIT_ENABLED=false` is recommended for local dev to avoid hitting limits during testing
- `SECRET_KEY` in `.env` only needs to be cryptographically strong in production

**Stop / clean up:**
```bash
docker compose down          # Stop containers (data volumes preserved)
docker compose down -v       # Stop + delete all data volumes (full reset)
```

### Local Development (no Docker for app)

```bash
# Infrastructure only (Postgres + Redis in Docker)
make dev-infra        # Starts postgres + redis containers

# Then run app locally
make dev-backend      # Backend with uvicorn --reload (requires uv installed)
make dev-frontend     # Frontend with Vite HMR (requires Node 20+)
```

### First-time setup (local, non-Docker)

```bash
cp .env.example .env  # Configure environment
make bootstrap        # Install all deps (uv sync + npm install)
make db-migrate       # Run Alembic migrations
```

### Windows-specific notes
- The `Makefile` uses `/bin/zsh` as shell; on Windows use `docker compose` commands directly or Git Bash/WSL
- Hot-reload source volumes (`./backend/app`, `./frontend/src`) work on Windows with Docker Desktop WSL2 backend enabled

---

## Iterative Development Protocol

When asked to build a new feature or fix a bug:

1. **Clarify scope** — What exactly needs to change? Which agents are affected?
2. **Check existing code** — Read related files before writing new ones
3. **Implement backend first** — Models → Schemas → Services → Routes → Tests
4. **Then frontend** — Types → API → Store → Components → Page
5. **Validate** — Run tests, check types, verify manually
6. **Document** — Update relevant `.md` files

When in doubt, ask rather than assume.
