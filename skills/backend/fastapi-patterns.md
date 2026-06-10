# Skill: FastAPI Patterns

> Implementation standards for the Aditi IT Assist backend API layer.

---

## Pattern 1: Route → Service → Repository

Every API endpoint follows the same delegation chain:

```python
# ✅ CORRECT: Route delegates to service
@router.post("/chat/message", response_model=ChatResponse)
async def send_message(
    data: ChatMessageCreate,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    return await service.process_message(data)

# ❌ WRONG: Logic in route handler
@router.post("/chat/message")
async def send_message(data: dict, db: Session = Depends(get_db)):
    result = db.execute(...)  # Never query in routes
    llm_response = await call_llm(result)  # Never call LLM in routes
    return {"response": llm_response}
```

---

## Pattern 2: Dependency Injection

Services are injected via FastAPI's `Depends`:

```python
# Service factory
def get_chat_service(
    db: AsyncSession = Depends(get_db_session),
    llm: LLMService = Depends(get_llm_service),
    knowledge: KnowledgeRepository = Depends(get_knowledge_repo),
) -> ChatService:
    return ChatService(db=db, llm=llm, knowledge=knowledge)

# Usage in route
@router.post("/resource")
async def create(
    data: ResourceCreate,
    service: ResourceService = Depends(get_resource_service),
) -> ResourceResponse:
    return await service.create(data)
```

---

## Pattern 3: Pydantic Schemas

Request and response schemas are always Pydantic v2 models:

```python
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID

# Request schema (what the client sends)
class ChatMessageCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: str | None = None

# Response schema (what we return)
class ChatResponse(BaseModel):
    session_id: str
    message: str
    confidence: float = Field(ge=0.0, le=1.0)
    needs_escalation: bool = False
    created_at: datetime

# Database schema (for ORM → API conversion)
class ChatSessionDB(BaseModel):
    id: UUID
    user_id: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
```

---

## Pattern 4: Error Handling

All errors are handled consistently:

```python
from fastapi import HTTPException, status

class ServiceError(Exception):
    """Base service error."""
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code

# In service layer
async def get_session(self, session_id: str) -> ChatSession:
    session = await self.repo.get(session_id)
    if not session:
        raise ServiceError("Session not found", status_code=404)
    return session

# Global exception handler
@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )
```

---

## Pattern 5: Async Database Operations

All database access uses async SQLAlchemy:

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

class SessionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, session_id: str) -> ChatSession | None:
        result = await self.db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def create(self, session: ChatSession) -> ChatSession:
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session
```

---

## Pattern 6: Structured Logging

All logging uses structlog with context:

```python
import structlog

logger = structlog.get_logger()

async def process_message(self, data: ChatMessageCreate) -> ChatResponse:
    logger.info(
        "chat.message_received",
        session_id=data.session_id,
        message_length=len(data.message),
    )
    # ... processing ...
    logger.info(
        "chat.message_processed",
        session_id=data.session_id,
        confidence=result.confidence,
        escalated=result.needs_escalation,
    )
```

---

## Pattern 7: Configuration

All config through Pydantic Settings:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "aditi_assist"
    postgres_user: str = "aditi"
    postgres_password: str = ""

    # LLM
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    model_config = SettingsConfigDict(env_file=".env")
```

---

## Anti-Patterns (Do NOT Do)

| Anti-Pattern | Why It's Wrong | Correct Approach |
|-------------|----------------|------------------|
| DB queries in route handlers | Untestable, violates separation | Use repository via service |
| Returning `dict` from routes | No validation, no docs | Use Pydantic response model |
| Synchronous I/O | Blocks event loop | Use `async`/`await` |
| Hardcoded config values | Can't change per environment | Use Settings class |
| `try: ... except: pass` | Silences errors | Handle specific exceptions, log |
| Global mutable state | Race conditions | Use DI, request-scoped state |

---

## File Locations

| Concern | Path |
|---------|------|
| Route definitions | `backend/app/api/v1/*.py` |
| Service classes | `backend/app/services/*.py` |
| Repository classes | `backend/app/repositories/*.py` |
| Pydantic schemas | `backend/app/schemas/*.py` |
| SQLAlchemy models | `backend/app/models/*.py` |
| Config | `backend/app/core/config.py` |
| Dependencies | `backend/app/core/deps.py` |
