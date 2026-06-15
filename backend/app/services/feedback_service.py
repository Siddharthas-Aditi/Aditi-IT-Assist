"""Feedback service — business logic for post-chat surveys.

Responsibilities:
- Validate that the session belongs to (or is accessible by) the user
- Idempotent upsert: one ConversationFeedback row per session per user
- Auto-derive: support_mode, escalation_occurred, category, subcategory,
  agent_user_id, knowledge_article_ids from the existing SupportSession row
- Compute review_flag and quality_bucket at write time
- Log audit event for each submission
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from app.models.feedback import (
    ConversationFeedback,
    FeedbackSource,
    MessageFeedback,
    QualityBucket,
    SupportMode,
)
from app.models.support import SupportSession
from app.repositories.feedback_repository import FeedbackRepository
from app.schemas.feedback import (
    ConversationFeedbackCreate,
    ConversationFeedbackResponse,
    MessageFeedbackCreate,
    MessageFeedbackResponse,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# Map SupportSession.session_type → SupportMode
_SESSION_TYPE_MAP: dict[str, SupportMode] = {
    "ai_chat": SupportMode.AI_ONLY,
    "live_support": SupportMode.LIVE_AGENT_ONLY,
    "hybrid": SupportMode.AI_PLUS_LIVE_AGENT,
}

# Sessions in these statuses are considered "escalated"
_ESCALATED_STATUSES = frozenset({"escalated", "live_support"})

# Review flag triggers
_NEGATIVE_RATING_THRESHOLD = 2  # rating ≤ 2 → flag


def _compute_quality_bucket(
    helpful: bool | None,
    resolved: bool | None,
    rating: int | None,
) -> QualityBucket:
    """Derive coarse quality signal from survey answers."""
    has_positive = (helpful is True) or (resolved is True) or (rating is not None and rating >= 4)
    has_negative = (helpful is False) or (resolved is False) or (
        rating is not None and rating <= _NEGATIVE_RATING_THRESHOLD
    )

    if has_positive and not has_negative:
        return QualityBucket.POSITIVE
    if has_negative and not has_positive:
        return QualityBucket.NEGATIVE
    if has_negative:
        return QualityBucket.NEGATIVE  # any negative signal pulls bucket down
    return QualityBucket.NEUTRAL


def _compute_review_flag(
    helpful: bool | None,
    resolved: bool | None,
    rating: int | None,
) -> tuple[bool, str | None]:
    """Return (should_flag, reason_string)."""
    reasons: list[str] = []
    if helpful is False:
        reasons.append("not helpful")
    if resolved is False:
        reasons.append("issue unresolved")
    if rating is not None and rating <= _NEGATIVE_RATING_THRESHOLD:
        reasons.append(f"low rating ({rating})")
    if reasons:
        return True, "; ".join(reasons)
    return False, None


class FeedbackService:
    """Service for post-chat feedback submission and retrieval."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = FeedbackRepository(db)

    # ──────────────────────────────────────────────────────────────
    # Conversation-level feedback
    # ──────────────────────────────────────────────────────────────

    async def submit_feedback(
        self,
        session_id: str,
        user_id: str,
        payload: ConversationFeedbackCreate,
    ) -> ConversationFeedbackResponse:
        """Submit (or update) post-chat survey for a support session.

        This method is safe to call multiple times — subsequent calls
        merge new answers into the existing row.
        """
        conv_id = uuid.UUID(session_id)
        uid = uuid.UUID(user_id)

        # Verify session exists (and optionally belongs to user — TODO when session
        # repository is complete; for now we load via raw DB)
        from sqlalchemy import select
        session_result = await self.db.execute(
            select(SupportSession).where(SupportSession.id == conv_id)
        )
        support_session: SupportSession | None = session_result.scalar_one_or_none()
        if support_session is None:
            raise ValueError(f"Session {session_id!r} not found")

        # Employees can only submit for their own sessions
        if str(support_session.user_id) != user_id:
            raise PermissionError("You may only submit feedback for your own sessions")

        # Derive context fields from the session
        support_mode = _SESSION_TYPE_MAP.get(
            support_session.session_type or "ai_chat", SupportMode.AI_ONLY
        )
        escalation_occurred = (support_session.status in _ESCALATED_STATUSES) or bool(
            support_session.assigned_agent_id
        )
        agent_user_id = support_session.assigned_agent_id

        # Pull knowledge article ids from session metadata if present
        metadata = support_session.metadata_json or {}
        article_ids: list[str] | None = metadata.get("knowledge_article_ids") or None

        # Compute derived fields
        quality_bucket = _compute_quality_bucket(
            payload.helpful, payload.resolved, payload.rating
        )
        review_flag, review_flag_reason = _compute_review_flag(
            payload.helpful, payload.resolved, payload.rating
        )

        # Duration
        session_duration = None
        if support_session.resolved_at and support_session.created_at:
            delta = support_session.resolved_at - support_session.created_at
            session_duration = int(delta.total_seconds())

        existing = await self.repo.get_by_conversation_and_user(conv_id, uid)

        if existing is not None:
            # Merge — only update non-None fields from payload
            updates: dict = {
                "submitted_at": datetime.now(UTC),
                "quality_bucket": quality_bucket.value,
                "review_flag": review_flag,
                "review_flag_reason": review_flag_reason,
            }
            if payload.helpful is not None:
                updates["helpful"] = payload.helpful
            if payload.resolved is not None:
                updates["resolved"] = payload.resolved
            if payload.rating is not None:
                updates["rating"] = payload.rating
            if payload.comment is not None:
                updates["comment"] = payload.comment
            if payload.ticket_id is not None:
                updates["ticket_id"] = payload.ticket_id
            updates["feedback_source"] = payload.feedback_source

            record = await self.repo.update(existing, updates)
        else:
            record = ConversationFeedback(
                conversation_id=conv_id,
                ticket_id=payload.ticket_id,
                submitted_by_user_id=uid,
                helpful=payload.helpful,
                resolved=payload.resolved,
                rating=payload.rating,
                comment=payload.comment,
                submitted_at=datetime.now(UTC),
                channel="web_chat",
                feedback_source=payload.feedback_source,
                support_mode=support_mode.value,
                agent_user_id=agent_user_id,
                escalation_occurred=escalation_occurred,
                category=support_session.issue_category,
                subcategory=support_session.issue_subcategory,
                knowledge_article_ids=article_ids,
                session_duration_seconds=session_duration,
                quality_bucket=quality_bucket.value,
                review_flag=review_flag,
                review_flag_reason=review_flag_reason,
            )
            record = await self.repo.create(record)

        logger.info(
            "feedback.submitted",
            session_id=session_id,
            user_id=user_id,
            quality_bucket=quality_bucket.value,
            review_flag=review_flag,
        )

        return ConversationFeedbackResponse.model_validate(record)

    async def get_session_feedback(
        self,
        session_id: str,
        user_id: str,
    ) -> ConversationFeedbackResponse | None:
        """Return the current user's feedback for a session, or None."""
        conv_id = uuid.UUID(session_id)
        uid = uuid.UUID(user_id)
        record = await self.repo.get_by_conversation_and_user(conv_id, uid)
        if record is None:
            return None
        return ConversationFeedbackResponse.model_validate(record)

    async def get_session_feedback_all(
        self,
        session_id: str,
    ) -> list[ConversationFeedbackResponse]:
        """Return all feedback for a session (agent/admin view)."""
        conv_id = uuid.UUID(session_id)
        records = await self.repo.get_by_conversation(conv_id)
        return [ConversationFeedbackResponse.model_validate(r) for r in records]

    async def get_ticket_feedback(
        self,
        ticket_id: str,
    ) -> list[ConversationFeedbackResponse]:
        """Return all feedback linked to a ticket (agent/admin view)."""
        tid = uuid.UUID(ticket_id)
        records = await self.repo.get_by_ticket(tid)
        return [ConversationFeedbackResponse.model_validate(r) for r in records]

    async def list_flagged(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        category: str | None = None,
    ) -> tuple[list[ConversationFeedbackResponse], int]:
        """Return paginated review-flagged feedback for admin queue."""
        records = await self.repo.list_flagged(
            limit=limit, offset=offset, category=category
        )
        total = await self.repo.count_flagged(category=category)
        return [ConversationFeedbackResponse.model_validate(r) for r in records], total

    # ──────────────────────────────────────────────────────────────
    # Message-level feedback
    # ──────────────────────────────────────────────────────────────

    async def submit_message_feedback(
        self,
        message_id: str,
        session_id: str,
        user_id: str,
        payload: MessageFeedbackCreate,
    ) -> MessageFeedbackResponse:
        """Submit (or update) thumbs up/down on an AI message."""
        msg_id = uuid.UUID(message_id)
        sess_id = uuid.UUID(session_id)
        uid = uuid.UUID(user_id)

        existing = await self.repo.get_message_feedback(msg_id, uid)
        if existing is not None:
            updates: dict = {
                "helpful": payload.helpful,
                "submitted_at": datetime.now(UTC),
            }
            if payload.comment is not None:
                updates["comment"] = payload.comment
            if payload.knowledge_article_ids is not None:
                updates["knowledge_article_ids"] = payload.knowledge_article_ids
            record = await self.repo.update_message_feedback(existing, updates)
        else:
            record = MessageFeedback(
                message_id=msg_id,
                session_id=sess_id,
                submitted_by_user_id=uid,
                helpful=payload.helpful,
                comment=payload.comment,
                knowledge_article_ids=payload.knowledge_article_ids,
                submitted_at=datetime.now(UTC),
            )
            record = await self.repo.create_message_feedback(record)

        logger.info(
            "message_feedback.submitted",
            message_id=message_id,
            user_id=user_id,
            helpful=payload.helpful,
        )
        return MessageFeedbackResponse.model_validate(record)


# ─── DI factory ───────────────────────────────────────────────────────────────


def get_feedback_service(db: AsyncSession) -> FeedbackService:  # type: ignore[name-defined]
    return FeedbackService(db)
