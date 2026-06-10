# CLAUDE.md - AI Agent Instructions for Aditi IT Assist

> **Purpose**: This is the master context file for AI coding assistants (Claude, Copilot, etc.)
> working on this codebase. Read this first before making any changes.

---

## Project Overview

**Aditi IT Assist** is an agentic AI-powered internal IT support platform for Aditi Consulting.
It uses a multi-agent workflow (LangGraph) to intake employee IT issues, classify them,
retrieve relevant knowledge, guide troubleshooting, and escalate when needed.

## Architecture Quick Reference

| Layer | Technology | Location |
|-------|-----------|----------|
| Backend API | Python 3.12+ / FastAPI / SQLAlchemy | `backend/` |
| AI Orchestration | LangGraph / LiteLLM | `backend/app/workflows/` |
| Database | PostgreSQL 16 / pgvector | Docker (port 5432) |
| Cache | Redis 7 | Docker (port 6379) |
| Frontend | React 18 / TypeScript / Vite | `frontend/` |
| UI System | Tailwind CSS / shadcn/ui / Radix | `frontend/src/components/` |
| Package Mgmt | uv (backend) / npm (frontend) | `pyproject.toml` / `package.json` |

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
make test               # Everything
make lint               # Linting (both)
```

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

## Key File Locations

| Concern | Location |
|---------|----------|
| API routes | `backend/app/api/v1/` |
| Database models | `backend/app/models/` |
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

```bash
# Quick start (Docker — recommended)
make dev              # Full stack with hot-reload

# Local development (no Docker for app, only infra)
make dev-infra        # Start Postgres + Redis only
make dev-backend      # Backend with uvicorn --reload
make dev-frontend     # Frontend with Vite HMR

# First-time setup
cp .env.example .env  # Configure environment
make bootstrap        # Install all deps
```

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
