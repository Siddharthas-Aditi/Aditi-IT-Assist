# System Architecture — Aditi IT Assist

## Overview

Aditi IT Assist follows a **layered architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (React/Vite)                      │
│  Pages → Features → Components → API Client → React Query     │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP/WebSocket
┌──────────────────────────────▼──────────────────────────────┐
│                    API Gateway (FastAPI)                       │
│  Routes → Schemas → Services → Repositories → Models          │
├───────────────────────────────────────────────────────────────┤
│                   Agent Workflow (LangGraph)                   │
│  Orchestrator → Agents → Tools → State Management             │
├───────────────────────────────────────────────────────────────┤
│                    Infrastructure Layer                        │
│  PostgreSQL │ pgvector │ Redis │ LLM Provider │ SMTP           │
└───────────────────────────────────────────────────────────────┘
```

## Component Diagram

### Frontend Layer
- **Pages**: Login, Chat, Tickets, Admin, Knowledge
- **Features**: Chat module, Ticket module, Knowledge module, Admin module
- **Shared Components**: Layout, Design System, Forms
- **State**: Zustand stores for session, UI, auth
- **API Client**: Typed fetch wrapper with React Query integration

### API Layer (FastAPI)
- **v1 Routes**: /health, /chat, /tickets, /knowledge, /admin, /auth
- **Middleware**: Auth, CORS, rate limiting, request tracing
- **Schemas**: Pydantic v2 models for all request/response types
- **Dependencies**: Database sessions, current user, service injection

### Service Layer
- **ChatService**: Manages conversation sessions and message flow
- **AgentService**: Invokes LangGraph workflow, manages state
- **KnowledgeService**: CRUD for knowledge articles, vector search
- **TicketService**: Ticket creation and lifecycle management
- **NotificationService**: Email drafts and notifications
- **LLMService**: Provider-agnostic LLM invocation via LiteLLM

### Agent Workflow Layer (LangGraph)
- **Graph Definition**: Nodes, edges, conditional routing
- **State Schema**: TypedDict with all workflow fields
- **Nodes**: One per agent (triage, retrieval, resolution, escalation, ticketing)
- **Tools**: Knowledge search, classification, confidence scoring

### Data Layer
- **PostgreSQL**: Primary data store (users, sessions, messages, tickets, knowledge)
- **pgvector**: Vector embeddings for semantic knowledge search
- **Redis**: Session cache, rate limiting, background job queue
- **Alembic**: Database migrations

## Data Flow

### Happy Path (Issue Resolved by AI)
```
1. User sends message → POST /api/v1/chat/message
2. ChatService creates/updates session
3. AgentService invokes LangGraph workflow
4. Triage node classifies issue
5. Retrieval node searches knowledge base
6. Resolution node generates steps
7. Response returned with confidence > 0.8
8. User follows steps → issue resolved
9. Session closed with success status
```

### Escalation Path
```
1. Resolution confidence < 0.5 OR user requests human
2. Escalation node prepares handoff summary
3. Check human agent availability (future: real-time)
4. If available: route to human with context
5. If not available: Ticket node creates draft
6. Draft presented to user for approval
7. Ticket/email sent upon approval
```

## Infrastructure

### Local Development
- Docker Compose orchestrates all services
- Hot-reload enabled for both frontend and backend
- Seeded database with sample data

### Production (Future)
- Kubernetes deployment on Azure AKS
- Azure Database for PostgreSQL
- Azure Cache for Redis
- Azure OpenAI for LLM
- Azure Application Insights for observability

## Security Architecture

- JWT-based authentication (future: Azure AD SSO)
- Role-based access control (employee, IT agent, admin)
- All LLM calls go through internal proxy (no direct employee→LLM)
- PII handling: conversation data encrypted at rest
- Audit logging for all agent decisions
- Rate limiting on all API endpoints

## Scalability Considerations

- Stateless API servers (horizontal scaling)
- Redis for session state and caching
- Background jobs for async operations (knowledge indexing, learning)
- Database connection pooling via SQLAlchemy
- Vector search with pgvector indexes (IVFFlat or HNSW)
