"""Data-access layer for post-chat feedback.

All persistence for ConversationFeedback and MessageFeedback is routed
through this repository — no inline queries in service code.  Methods
flush but do not commit; the unit-of-work is owned by the caller.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, select

from app.models.feedback import ConversationFeedback, MessageFeedback

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class FeedbackRepository:
    """Repository for ConversationFeedback and MessageFeedback records."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ──────────────────────────────────────────────────────────────
    # ConversationFeedback
    # ──────────────────────────────────────────────────────────────

    async def get_by_conversation_and_user(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ConversationFeedback | None:
        """Return the existing feedback record for this session + user, or None."""
        result = await self.db.execute(
            select(ConversationFeedback).where(
                and_(
                    ConversationFeedback.conversation_id == conversation_id,
                    ConversationFeedback.submitted_by_user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, feedback_id: uuid.UUID) -> ConversationFeedback | None:
        result = await self.db.execute(
            select(ConversationFeedback).where(ConversationFeedback.id == feedback_id)
        )
        return result.scalar_one_or_none()

    async def get_by_conversation(
        self, conversation_id: uuid.UUID
    ) -> list[ConversationFeedback]:
        """All feedback entries for a session (typically at most one)."""
        result = await self.db.execute(
            select(ConversationFeedback).where(
                ConversationFeedback.conversation_id == conversation_id
            )
        )
        return list(result.scalars().all())

    async def get_by_ticket(self, ticket_id: uuid.UUID) -> list[ConversationFeedback]:
        result = await self.db.execute(
            select(ConversationFeedback).where(
                ConversationFeedback.ticket_id == ticket_id
            )
        )
        return list(result.scalars().all())

    async def create(self, feedback: ConversationFeedback) -> ConversationFeedback:
        self.db.add(feedback)
        await self.db.flush()
        await self.db.refresh(feedback)
        return feedback

    async def update(
        self,
        feedback: ConversationFeedback,
        updates: dict,
    ) -> ConversationFeedback:
        for key, value in updates.items():
            if hasattr(feedback, key):
                setattr(feedback, key, value)
        await self.db.flush()
        await self.db.refresh(feedback)
        return feedback

    async def list_flagged(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        category: str | None = None,
    ) -> list[ConversationFeedback]:
        """Return review-flagged feedback records for the admin review queue."""
        query = (
            select(ConversationFeedback)
            .where(ConversationFeedback.review_flag.is_(True))
            .order_by(ConversationFeedback.submitted_at.desc())
        )
        if category:
            query = query.where(ConversationFeedback.category == category)
        query = query.limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_flagged(self, *, category: str | None = None) -> int:
        query = select(func.count(ConversationFeedback.id)).where(
            ConversationFeedback.review_flag.is_(True)
        )
        if category:
            query = query.where(ConversationFeedback.category == category)
        result = await self.db.execute(query)
        return result.scalar() or 0

    # ──────────────────────────────────────────────────────────────
    # Analytics queries
    # ──────────────────────────────────────────────────────────────

    async def get_analytics_rows(
        self,
        *,
        from_dt: datetime,
        to_dt: datetime,
        category: str | None = None,
        support_mode: str | None = None,
    ) -> list[ConversationFeedback]:
        """Return all feedback rows for the given window (used by analytics service)."""
        query = select(ConversationFeedback).where(
            and_(
                ConversationFeedback.submitted_at >= from_dt,
                ConversationFeedback.submitted_at <= to_dt,
            )
        )
        if category:
            query = query.where(ConversationFeedback.category == category)
        if support_mode:
            query = query.where(ConversationFeedback.support_mode == support_mode)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_rows_for_article(
        self,
        article_id: str,
        *,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> list[ConversationFeedback]:
        """Return feedback rows that reference a specific knowledge article."""
        # JSONB @> operator: check if list contains the article_id string
        query = select(ConversationFeedback).where(
            ConversationFeedback.knowledge_article_ids.contains([article_id])  # type: ignore[union-attr]
        )
        if from_dt:
            query = query.where(ConversationFeedback.submitted_at >= from_dt)
        if to_dt:
            query = query.where(ConversationFeedback.submitted_at <= to_dt)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_rows_for_agent(
        self,
        agent_user_id: uuid.UUID,
        *,
        from_dt: datetime,
        to_dt: datetime,
    ) -> list[ConversationFeedback]:
        query = select(ConversationFeedback).where(
            and_(
                ConversationFeedback.agent_user_id == agent_user_id,
                ConversationFeedback.submitted_at >= from_dt,
                ConversationFeedback.submitted_at <= to_dt,
            )
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ──────────────────────────────────────────────────────────────
    # MessageFeedback
    # ──────────────────────────────────────────────────────────────

    async def get_message_feedback(
        self,
        message_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> MessageFeedback | None:
        result = await self.db.execute(
            select(MessageFeedback).where(
                and_(
                    MessageFeedback.message_id == message_id,
                    MessageFeedback.submitted_by_user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def create_message_feedback(
        self, feedback: MessageFeedback
    ) -> MessageFeedback:
        self.db.add(feedback)
        await self.db.flush()
        await self.db.refresh(feedback)
        return feedback

    async def update_message_feedback(
        self,
        feedback: MessageFeedback,
        updates: dict,
    ) -> MessageFeedback:
        for key, value in updates.items():
            if hasattr(feedback, key):
                setattr(feedback, key, value)
        await self.db.flush()
        await self.db.refresh(feedback)
        return feedback
