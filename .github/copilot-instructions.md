# Copilot Instructions for Aditi IT Assist

## Project Context

This is **Aditi IT Assist** — an enterprise-grade internal IT service platform for
Aditi Consulting. It uses a multi-agent LangGraph workflow to resolve employee
IT issues through a conversational interface, with full RBAC, ticketing lifecycle,
remote assistance orchestration, analytics, and future SAML SSO integration.

## Architecture

- **Backend**: Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL / LangGraph
- **Frontend**: React / TypeScript / Vite / Tailwind CSS / shadcn/ui
- **AI**: LangGraph orchestration with LiteLLM provider abstraction
- **Auth**: Pluggable provider (local + SAML stub) with JWT sessions
- **RBAC**: Role-based (employee, it_agent, it_lead, it_admin, security_auditor)
- **Vector Search**: pgvector for knowledge retrieval

## Enterprise Patterns

### Auth & RBAC
- Auth providers in `backend/app/services/auth/providers/`
- Use `CurrentUser`, `ITAgentUser`, `ITLeadUser`, `AdminUser` type aliases
- `require_roles()` and `require_permissions()` for endpoint guards
- Employees can ONLY see their own data (tickets, chats)
- Internal notes are hidden from employees

### Services
- `AuthService` — login, registration, token validation
- `TicketService` — full ticket lifecycle with SLA
- `RemoteSupportService` — remote assist orchestration
- `AnalyticsService` — dashboard metrics
- `AuditService` — immutable event logging

### Frontend Structure
- `/support/*` — Employee workspace (chat, tickets, profile)
- `/operations/*` — IT agent workspace (queue, tickets, remote assist)
- `/dashboard/*` — Admin/lead workspace (analytics, management)
- `/audit` — Audit log viewer (admin + auditor)

## Coding Conventions

### Python
- Use type hints everywhere
- Async functions for I/O operations
- Pydantic v2 for all schemas
- Service layer pattern (routes → services → repositories)
- structlog for logging
- 100 char line length
- Ruff for linting and formatting

### TypeScript
- Strict TypeScript (no `any`)
- Functional components with hooks
- React Query for server state
- Zustand for client state
- Tailwind CSS utility classes
- Component-per-file pattern

### General
- Small, focused files (< 300 lines)
- Meaningful names over comments
- Tests for all service methods
- Error handling is mandatory
- No hardcoded configuration values

## File Organization

When creating new features:
1. Backend: model → schema → repository → service → route
2. Frontend: types → api → store → components → page
3. Tests alongside implementation

## Key Patterns

### API Endpoints
```python
@router.post("/resource", response_model=ResourceResponse)
async def create_resource(
    data: ResourceCreate,
    service: ResourceService = Depends(get_resource_service),
) -> ResourceResponse:
    return await service.create(data)
```

### React Components
```typescript
interface Props {
  title: string;
  onAction: () => void;
}

export function Component({ title, onAction }: Props) {
  return (/* JSX */);
}
```

### LangGraph Nodes
```python
async def node_name(state: WorkflowState) -> WorkflowState:
    # Process state
    # Return updated state
    return {**state, "field": new_value}
```

## What NOT to Do
- Don't bypass the service layer
- Don't use `any` in TypeScript
- Don't skip error handling
- Don't hardcode secrets
- Don't create files > 300 lines
- Don't skip tests for services
