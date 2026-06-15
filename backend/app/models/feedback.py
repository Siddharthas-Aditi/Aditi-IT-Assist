"""Feedback models — post-chat survey and message-level reactions.

Two tables capture the enterprise feedback loop:

- ``ConversationFeedback`` — one record per support session (idempotent; the
  employee submits a 5-step progressive-disclosure survey after resolution).
- ``MessageFeedback``      — one record per message per employee (thumbs
  up / down inline reaction on individual AI answers).

Design rules:
- Both tables carry ``review_flag`` (auto-set for low signals) so admins
  can triage negative feedback without scanning every row.
- ``quality_bucket`` is a denormalised derived column (POSITIVE / NEUTRAL /
  NEGATIVE) computed at write time to make analytics queries fast.
- Foreign keys deliberately mirror the exact column names from the existing
  ``support_sessions``, ``messages``, and ``tickets`` tables.
"""

from __future__ import annotations

import enum
import uuid as _uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


# ─────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────


class SupportMode(str, enum.Enum):
    """How the support session was delivered — mirrors session_type on SupportSession."""

    AI_ONLY = "ai_only"
    AI_PLUS_LIVE_AGENT = "ai_plus_live_agent"
    LIVE_AGENT_ONLY = "live_agent_only"


class FeedbackSource(str, enum.Enum):
    """Where in the product the feedback was collected."""

    INLINE_CHAT = "inline_chat"
    TICKET_PAGE = "ticket_page"
    FOLLOWUP = "followup"


class QualityBucket(str, enum.Enum):
    """Coarse quality signal, computed at submission time."""

    POSITIVE = "positive"   # helpful=True AND resolved=True AND (rating is None OR rating >= 4)
    NEUTRAL = "neutral"     # mixed signals — at least one positive, at least one negative
    NEGATIVE = "negative"   # helpful=False OR resolved=False OR rating <= 2


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ─────────────────────────────────────────────────────────────────────
# ConversationFeedback
# ─────────────────────────────────────────────────────────────────────


class ConversationFeedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Post-chat survey — one record per support session per employee.

    Idempotency: enforced by the UNIQUE constraint on
    (conversation_id, submitted_by_user_id).  Re-submissions update the
    existing row; they do not create duplicates.
    """

    __tablename__ = "conversation_feedback"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "submitted_by_user_id",
            name="uq_feedback_conversation_user",
        ),
    )

    # ── Core linkage ────────────────────────────────────────────────
    conversation_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("support_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticket_id: Mapped[_uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tickets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    submitted_by_user_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Survey answers ──────────────────────────────────────────────
    helpful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    resolved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)   # 1–5
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Submission metadata ─────────────────────────────────────────
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    channel: Mapped[str] = mapped_column(String(50), default="web_chat", nullable=False)
    feedback_source: Mapped[str] = mapped_column(
        Enum(FeedbackSource, name="feedback_source_enum"),
        default=FeedbackSource.INLINE_CHAT,
        nullable=False,
    )

    # ── Session context (auto-populated at submission) ──────────────
    support_mode: Mapped[str] = mapped_column(
        Enum(SupportMode, name="support_mode_enum"),
        default=SupportMode.AI_ONLY,
        nullable=False,
    )
    agent_user_id: Mapped[_uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    escalation_occurred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)
    knowledge_article_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # ── Timing (seconds) ────────────────────────────────────────────
    session_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_response_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Derived / analytics columns ─────────────────────────────────
    sentiment_label: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # set by async analytics job
    quality_bucket: Mapped[str | None] = mapped_column(
        Enum(QualityBucket, name="quality_bucket_enum"), nullable=True
    )
    review_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    review_flag_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Relationships ────────────────────────────────────────────────
    session: Mapped["app.models.support.SupportSession"] = relationship(  # type: ignore[name-defined]
        "SupportSession", foreign_keys=[conversation_id], lazy="select"
    )
    submitted_by: Mapped["app.models.auth.User"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[submitted_by_user_id], lazy="select"
    )


# ─────────────────────────────────────────────────────────────────────
# MessageFeedback
# ─────────────────────────────────────────────────────────────────────


class MessageFeedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Inline thumbs up / down on individual AI messages.

    Idempotency: UNIQUE constraint on (message_id, submitted_by_user_id).
    Re-submitting simply flips the ``helpful`` value.
    """

    __tablename__ = "message_feedback"
    __table_args__ = (
        UniqueConstraint(
            "message_id",
            "submitted_by_user_id",
            name="uq_msg_feedback_message_user",
        ),
    )

    message_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("support_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    submitted_by_user_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # True = thumbs up, False = thumbs down
    helpful: Mapped[bool] = mapped_column(Boolean, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    knowledge_article_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    # ── Relationships ────────────────────────────────────────────────
    submitted_by: Mapped["app.models.auth.User"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[submitted_by_user_id], lazy="select"
    )
