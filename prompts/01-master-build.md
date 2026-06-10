# Master Build Prompt

> Use this prompt when starting a new feature or major change that touches
> multiple parts of the system.

---

## Context

You are building **Aditi IT Assist** — an agentic AI-powered IT support platform.

**Read these files first** (in order):
1. `CLAUDE.md` — Coding rules and architecture overview
2. `AGENTS.md` — Multi-agent system design
3. The relevant `agents/*.md` file for the agent you're modifying
4. The relevant `skills/**/*.md` file for implementation patterns

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12 / FastAPI / SQLAlchemy / LangGraph / LiteLLM |
| Frontend | React 18 / TypeScript / Vite / Tailwind / shadcn/ui |
| Database | PostgreSQL 16 + pgvector |
| Cache | Redis 7 |
| Infra | Docker Compose / Makefile |

## Build Priority

1. **Make it work** — Functional correctness first
2. **Make it clean** — Readable, maintainable, follows patterns
3. **Make it tested** — Unit + integration tests
4. **Make it documented** — Update docs with changes

## Implementation Order

When building a new feature:

```
1. backend/app/models/          → SQLAlchemy model
2. backend/app/schemas/         → Pydantic request/response schemas
3. backend/app/repositories/    → Database operations
4. backend/app/services/        → Business logic
5. backend/app/api/v1/          → API route
6. backend/app/workflows/nodes/ → Workflow node (if agent-related)
7. frontend/src/types/          → TypeScript types
8. frontend/src/lib/api.ts      → API client method
9. frontend/src/store/          → Zustand store (if needed)
10. frontend/src/features/      → UI components
11. backend/tests/              → Tests
```

## Validation Checklist

Before considering work done:
- [ ] All new code has type hints (Python) / types (TypeScript)
- [ ] Service methods have unit tests
- [ ] Error handling covers likely failure modes
- [ ] No hardcoded config values
- [ ] Docs updated if architecture changed
- [ ] `make lint` passes
- [ ] `make test` passes
