"""Support session and message models."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class SupportSession(UUIDPrimaryKeyMixin, Base):
    """Support session — a conversation between user and AI/agent."""

    __tablename__ = "support_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        Enum(
            "active",
            "awaiting_user",
            "awaiting_agent",
            "live_support",
            "resolved",
            "escalated",
            "closed",
            name="session_status",
        ),
        default="active",
    )
    session_type: Mapped[str] = mapped_column(
        Enum("ai_chat", "live_support", "hybrid", name="session_type"),
        default="ai_chat",
    )
    issue_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issue_subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    urgency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    messages: Mapped[list["Message"]] = relationship(back_populates="session")


class Message(UUIDPrimaryKeyMixin, Base):
    """Message in a support session."""

    __tablename__ = "messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("support_sessions.id"), index=True
    )
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    role: Mapped[str] = mapped_column(
        Enum("user", "assistant", "system", "agent", name="message_role"),
    )
    content: Mapped[str] = mapped_column(Text)
    message_type: Mapped[str] = mapped_column(
        Enum("text", "system_event", "handoff", "resolution", name="message_type"),
        default="text",
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    session: Mapped["SupportSession"] = relationship(back_populates="messages")
