# Backend Agent Prompt

You are implementing the backend for Aditi IT Assist. Follow these rules:

## Architecture
- FastAPI with versioned routes under `/api/v1/`
- Service layer pattern: routes → services → repositories → models
- Pydantic v2 for all schemas
- SQLAlchemy async for database operations
- LangGraph for agent workflow orchestration

## File Conventions
- Models in `backend/app/models/`
- Schemas in `backend/app/schemas/`
- Services in `backend/app/services/`
- Routes in `backend/app/api/v1/`
- Workflow nodes in `backend/app/workflows/nodes/`

## Code Style
- Python 3.12+ with full type hints
- Async for all I/O operations
- structlog for logging
- 100 char line length
- Ruff for formatting

## Database
- PostgreSQL with pgvector extension
- Alembic for migrations
- UUID primary keys
- Timestamps on all tables

## Testing
- pytest with async support
- Mock external services (LLM, email)
- Test service layer comprehensively
