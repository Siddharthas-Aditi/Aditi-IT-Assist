# Skill: Database Patterns

> SQLAlchemy async patterns for Aditi IT Assist.

---

## Pattern 1: Model Definition

```python
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from app.models.base import Base
import uuid
from datetime import datetime

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="active")
    issue_category = Column(String, nullable=True)
    resolution_confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("ChatMessage", back_populates="session")
```

---

## Pattern 2: Repository Layer

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

class SessionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, session_id: str) -> ChatSession | None:
        result = await self.db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> ChatSession:
        session = ChatSession(**kwargs)
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def list_by_user(self, user_id: str, limit: int = 20) -> list[ChatSession]:
        result = await self.db.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
```

---

## Pattern 3: pgvector Search

```python
from pgvector.sqlalchemy import Vector
from sqlalchemy import text

class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String, nullable=False, index=True)
    embedding = Column(Vector(1536))  # text-embedding-3-small dimension

class KnowledgeRepository:
    async def vector_search(
        self, query_embedding: list[float], category: str | None, top_k: int = 5
    ) -> list[dict]:
        """Cosine similarity search using pgvector."""
        query = text("""
            SELECT id, title, content, category,
                   1 - (embedding <=> :embedding) AS similarity
            FROM knowledge_articles
            WHERE (:category IS NULL OR category = :category)
            ORDER BY embedding <=> :embedding
            LIMIT :top_k
        """)
        result = await self.db.execute(
            query, {"embedding": str(query_embedding), "category": category, "top_k": top_k}
        )
        return [dict(row) for row in result.mappings()]
```

---

## Pattern 4: Migrations (Alembic)

```bash
# Create migration
alembic revision --autogenerate -m "add knowledge_articles table"

# Run migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

## Anti-Patterns

| Don't | Do Instead |
|-------|-----------|
| Query in route handlers | Use repository via service |
| Use sync SQLAlchemy | Use `AsyncSession` + `await` |
| Raw SQL without parameterization | Use `text()` with `:param` bindings |
| Commit in repository without refresh | Always `commit()` then `refresh()` |
| Skip indexes on query columns | Add `index=True` on filtered columns |
