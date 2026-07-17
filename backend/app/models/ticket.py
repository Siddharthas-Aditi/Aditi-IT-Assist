"""Enhanced ticket models with enterprise lifecycle management."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

TICKET_STATUSES = (
    "new",
    "triaged",
    "in_progress",
    "waiting_for_user",
    "escalated",
    "resolved",
    "closed",
)

TICKET_PRIORITIES = ("low", "medium", "high", "critical")

TICKET_SOURCES = (
    "chat",
    "email",
    "manual",
    "remote_session_followup",
    "api",
)


class Ticket(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Enterprise support ticket with full lifecycle."""

    __tablename__ = "tickets"

    # Core fields
    ticket_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)

    # Classification
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority: Mapped[str] = mapped_column(
        Enum(*TICKET_PRIORITIES, name="ticket_priority_v2"), default="medium"
    )
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    impact: Mapped[str | None] = mapped_column(
        Enum("individual", "team", "department", "organization", name="ticket_impact"),
        nullable=True,
    )
    urgency: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Status & Assignment
    status: Mapped[str] = mapped_column(
        Enum(*TICKET_STATUSES, name="ticket_status_v2"), default="new", index=True
    )
    source: Mapped[str] = mapped_column(Enum(*TICKET_SOURCES, name="ticket_source"), default="chat")

    # Relationships
    requester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    escalated_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("support_sessions.id"), nullable=True
    )
    remote_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("remote_support_sessions.id"), nullable=True
    )

    # SLA tracking
    sla_response_target: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sla_resolution_target: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_response_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # AI metadata
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_articles: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Additional metadata
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    custom_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    comments: Mapped[list["TicketComment"]] = relationship(
        back_populates="ticket", order_by="TicketComment.created_at"
    )
    events: Mapped[list["TicketEvent"]] = relationship(
        back_populates="ticket", order_by="TicketEvent.created_at"
    )


class TicketComment(UUIDPrimaryKeyMixin, Base):
    """Comment on a ticket — internal notes or employee-visible."""

    __tablename__ = "ticket_comments"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id"), index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False)
    comment_type: Mapped[str] = mapped_column(
        Enum("note", "reply", "system", "ai_suggestion", name="comment_type"),
        default="note",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    ticket: Mapped["Ticket"] = relationship(back_populates="comments")


class TicketEvent(UUIDPrimaryKeyMixin, Base):
    """Timeline event for ticket activity feed."""

    __tablename__ = "ticket_events"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id"), index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    description: Mapped[str] = mapped_column(Text)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    ticket: Mapped["Ticket"] = relationship(back_populates="events")
