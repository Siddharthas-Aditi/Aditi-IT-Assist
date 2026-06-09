# CLAUDE.md - AI Agent Instructions for Aditi IT Assist

## Project Overview

**Aditi IT Assist** is an agentic AI-powered internal IT support platform for Aditi Consulting.
It uses a multi-agent workflow (LangGraph) to intake employee IT issues, classify them,
retrieve relevant knowledge, guide troubleshooting, and escalate when needed.

## Architecture Quick Reference

- **Backend**: Python 3.12+ / FastAPI / SQLAlchemy / PostgreSQL / Redis / LangGraph
- **Frontend**: React / TypeScript / Vite / Tailwind CSS / shadcn/ui
- **AI Orchestration**: LangGraph with LiteLLM provider abstraction
- **Vector Store**: pgvector for knowledge retrieval
- **Dependency Management**: uv (backend), npm (frontend)

## Build Order (When Implementing Features)

1. Define data models and schemas first
2. Write service layer with proper abstractions
3. Create API endpoints that delegate to services
4. Build workflow nodes that compose services
5. Add frontend pages and wire to API
6. Write tests for the critical path
7. Update documentation

## Coding Guardrails

### Python (Backend)
- Use Python 3.12+ features (type hints, match statements where appropriate)
- Follow clean architecture: routes → services → repositories → models
- All API endpoints must use Pydantic v2 schemas for request/response
- Use `async` for all I/O-bound operations
- Service classes must be injectable (dependency injection via FastAPI Depends)
- Never hardcode LLM provider calls — always go through the abstraction layer
- Use structlog for all logging with structured context
- Database queries go through repository layer, never in route handlers
- All environment config via `app.core.config.Settings` (Pydantic BaseSettings)

### TypeScript (Frontend)
- Strict TypeScript — no `any` types unless absolutely necessary
- Components follow single responsibility principle
- API calls through dedicated api/ layer with React Query
- State management via Zustand stores (keep stores small and focused)
- All UI components use the design system tokens from theme/
- Pages compose features, features compose components
- Error boundaries around feature boundaries

### General
- No giant files (>300 lines should be split)
- Meaningful variable/function names
- Docstrings on all service classes and complex functions
- Comments explain "why", not "what"
- TODO markers must include context: `# TODO(username): description - ticket/issue ref`

## Testing Expectations

- Backend: pytest with async support, mock external services
- Frontend: Vitest + React Testing Library
- Integration tests for critical API flows
- Minimum 80% coverage on service layer
- All agent workflow nodes must have unit tests

## Documentation Expectations

- Every new feature needs a doc update
- Agent changes require updating the corresponding agents/*.md file
- API changes require updating OpenAPI schemas (auto-generated from Pydantic)
- Workflow changes require updating docs/architecture/workflows.md

## No-Shortcuts Policy

- Do NOT skip error handling
- Do NOT use `# type: ignore` without a comment explaining why
- Do NOT commit commented-out code
- Do NOT use `any` in TypeScript without a suppression comment
- Do NOT bypass the service layer from route handlers
- Do NOT hardcode secrets or configuration values
- Do NOT skip input validation

## How to Safely Modify Code

1. Read the relevant agent/skill docs first
2. Check existing tests to understand expected behavior
3. Make changes incrementally (small, focused commits)
4. Run `make lint` and `make test` before considering work done
5. Update related documentation
6. If modifying workflow graph, update the state diagram in docs

## Key File Locations

| Concern | Location |
|---------|----------|
| API routes | `backend/app/api/v1/` |
| Database models | `backend/app/models/` |
| Pydantic schemas | `backend/app/schemas/` |
| Service layer | `backend/app/services/` |
| LangGraph workflow | `backend/app/workflows/` |
| Knowledge base | `backend/app/knowledge_base/seed/` |
| Frontend pages | `frontend/src/pages/` |
| Frontend components | `frontend/src/components/` |
| Feature modules | `frontend/src/features/` |
| API client | `frontend/src/api/` |
| State stores | `frontend/src/store/` |
| Theme/tokens | `frontend/src/theme/` |

## Agent Workflow Overview

```
User Message → Orchestrator → Triage Agent → Knowledge Retrieval
    → Resolution Agent → [Success | Low Confidence]
        → If Low Confidence: Escalation Agent → Ticket/Email Agent
```

## Confidence Scoring

- Confidence > 0.8: Provide resolution directly
- Confidence 0.5-0.8: Provide resolution with disclaimer, offer escalation
- Confidence < 0.5: Escalate immediately

## Environment Setup

```bash
# Quick start
make bootstrap     # First-time setup
make dev           # Start with Docker
make dev-backend   # Backend only
make dev-frontend  # Frontend only
```
