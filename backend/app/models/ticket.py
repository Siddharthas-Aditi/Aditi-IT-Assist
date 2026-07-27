"""Enhanced ticket models with enterprise lifecycle management."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
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
    # 3rd level of the managed ticket category hierarchy (admin-configured)
    item: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # High-level ticket type tag (Incident / Service Request / Problem / Change / Other)
    ticket_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
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
    # Close details — populated by IT staff on close; employees cannot close tickets
    close_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

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


class TicketCategory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Admin-managed 3-level ticket category hierarchy.

    Level 1 = top-level type (e.g. 'Incident', 'Service Requests').
    Level 2 = sub-category (e.g. 'Network Connectivity').
    Level 3 = item (e.g. 'VPN', 'Wi-Fi').

    Children are protected by FK ON DELETE RESTRICT so a parent cannot be
    deleted while it has children — admin must remove children first.
    """

    __tablename__ = "ticket_categories"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # 1 | 2 | 3
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ticket_categories.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Self-referential tree helpers (no eager load — use explicit joins for perf)
    children: Mapped[list["TicketCategory"]] = relationship(
        "TicketCategory",
        foreign_keys=[parent_id],
        back_populates="parent",
        order_by="TicketCategory.sort_order, TicketCategory.name",
    )
    parent: Mapped["TicketCategory | None"] = relationship(
        "TicketCategory",
        foreign_keys=[parent_id],
        back_populates="children",
        remote_side="TicketCategory.id",
    )
