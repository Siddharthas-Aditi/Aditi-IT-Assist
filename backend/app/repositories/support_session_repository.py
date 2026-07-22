"""Data-access layer for durable AI support sessions and messages."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.support import Message, SupportSession

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class SupportSessionRepository:
    """Repository for ``support_sessions`` and ``messages``."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, session_id: uuid.UUID) -> SupportSession | None:
        result = await self.db.execute(
            select(SupportSession).where(SupportSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_with_messages(self, session_id: uuid.UUID) -> SupportSession | None:
        result = await self.db.execute(
            select(SupportSession)
            .options(selectinload(SupportSession.messages))
            .where(SupportSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SupportSession]:
        result = await self.db.execute(
            select(SupportSession)
            .where(SupportSession.user_id == user_id)
            .order_by(SupportSession.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create(self, session: SupportSession) -> SupportSession:
        self.db.add(session)
        await self.db.flush()
        return session

    async def add_message(self, message: Message) -> Message:
        self.db.add(message)
        await self.db.flush()
        return message
