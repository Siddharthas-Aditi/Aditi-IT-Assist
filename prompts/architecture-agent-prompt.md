# Architecture Agent Prompt

Guide architectural decisions for Aditi IT Assist following these principles:

## Patterns
- Clean architecture with clear separation of concerns
- Service layer abstraction for all business logic
- Repository pattern for data access
- Dependency injection via FastAPI Depends
- Event-driven audit logging

## Agent System
- LangGraph state machine with typed state
- Deterministic routing (not LLM-based)
- Confidence scoring for all resolutions
- Graceful degradation paths

## Data
- PostgreSQL for persistence
- pgvector for semantic search
- Redis for caching and sessions
- Structured YAML for knowledge base
