"""Change management models — Change request lifecycle, approvals, tasks, and audit trail."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ChangeType(StrEnum):
    STANDARD = "standard"
    NORMAL = "normal"
    EMERGENCY = "emergency"


class ChangeStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PLANNING = "planning"
    PENDING_APPROVAL = "pending_approval"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    CLOSED = "closed"


# Terminal statuses — no further transitions allowed.
CHANGE_TERMINAL_STATUSES = {ChangeStatus.CLOSED, ChangeStatus.CANCELLED}

# Valid transitions: from_status → set of allowed to_statuses.
CHANGE_TRANSITIONS: dict[ChangeStatus, set[ChangeStatus]] = {
    ChangeStatus.DRAFT: {ChangeStatus.SUBMITTED, ChangeStatus.PLANNING, ChangeStatus.CANCELLED},
    ChangeStatus.SUBMITTED: {
        ChangeStatus.PLANNING,
        ChangeStatus.PENDING_APPROVAL,
        ChangeStatus.CANCELLED,
    },
    ChangeStatus.PLANNING: {
        ChangeStatus.PENDING_APPROVAL,
        ChangeStatus.SCHEDULED,
        ChangeStatus.CANCELLED,
    },
    ChangeStatus.PENDING_APPROVAL: {
        ChangeStatus.SCHEDULED,
        ChangeStatus.REJECTED,
        ChangeStatus.PLANNING,
        ChangeStatus.CANCELLED,
    },
    ChangeStatus.SCHEDULED: {
        ChangeStatus.IN_PROGRESS,
        ChangeStatus.PLANNING,
        ChangeStatus.CANCELLED,
    },
    ChangeStatus.IN_PROGRESS: {
        ChangeStatus.IMPLEMENTED,
        ChangeStatus.ROLLED_BACK,
        ChangeStatus.CANCELLED,
    },
    ChangeStatus.IMPLEMENTED: {ChangeStatus.CLOSED},
    ChangeStatus.ROLLED_BACK: {ChangeStatus.PLANNING},
    ChangeStatus.REJECTED: {ChangeStatus.PLANNING},
    ChangeStatus.CANCELLED: set(),
    ChangeStatus.CLOSED: set(),
}


class ApprovalDecision(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ChangeEventType(StrEnum):
    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_DECIDED = "approval_decided"
    TASK_UPDATED = "task_updated"
    FIELD_UPDATED = "field_updated"
    ASSET_LINKED = "asset_linked"
    ASSET_UNLINKED = "asset_unlinked"
    NOTE_ADDED = "note_added"


class Change(Base):
    """A formal change request following an ITIL-aligned lifecycle."""

    __tablename__ = "changes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    change_number: Mapped[str] = mapped_column(
        sa.String(32), unique=True, nullable=False, index=True
    )
    source_ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True
    )
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    change_type: Mapped[str] = mapped_column(
        Enum(ChangeType, name="change_type_enum"), nullable=False, default=ChangeType.NORMAL
    )
    status: Mapped[str] = mapped_column(
        Enum(ChangeStatus, name="change_status_enum"),
        nullable=False,
        default=ChangeStatus.DRAFT,
        index=True,
    )
    priority: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="medium")
    impact: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="medium")
    risk: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="medium")
    department: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    category: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    maintenance_window: Mapped[str | None] = mapped_column(sa.String(256), nullable=True)
    planned_start: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    planned_end: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    actual_start: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    actual_end: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    closure_notes: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    emergency_justification: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    # Stores the nine planning text fields (reasonForChange, impactAnalysis, etc.)
    planning_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    approvals: Mapped[list[ChangeApproval]] = relationship(
        "ChangeApproval",
        back_populates="change",
        cascade="all, delete-orphan",
        order_by="ChangeApproval.stage",
    )
    tasks: Mapped[list[ChangeTask]] = relationship(
        "ChangeTask",
        back_populates="change",
        cascade="all, delete-orphan",
        order_by="ChangeTask.position",
    )
    events: Mapped[list[ChangeEvent]] = relationship(
        "ChangeEvent",
        back_populates="change",
        cascade="all, delete-orphan",
        order_by="ChangeEvent.created_at",
    )
    asset_links: Mapped[list[ChangeAssetLink]] = relationship(
        "ChangeAssetLink", back_populates="change", cascade="all, delete-orphan"
    )


class ChangeApproval(Base):
    """One approval stage on a Change record."""

    __tablename__ = "change_approvals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    change_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("changes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    approver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    decision: Mapped[str] = mapped_column(
        Enum(ApprovalDecision, name="approval_decision_enum"),
        nullable=False,
        default=ApprovalDecision.PENDING,
    )
    comments: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    decided_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    change: Mapped[Change] = relationship("Change", back_populates="approvals")


class ChangeTask(Base):
    """An implementation task checklist item on a Change."""

    __tablename__ = "change_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    change_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("changes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    done: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    change: Mapped[Change] = relationship("Change", back_populates="tasks")


class ChangeEvent(Base):
    """Immutable audit trail entry for a Change."""

    __tablename__ = "change_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    change_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("changes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    from_status: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    detail: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    change: Mapped[Change] = relationship("Change", back_populates="events")


class ChangeAssetLink(Base):
    """M2M: which assets a Change touches."""

    __tablename__ = "change_asset_links"

    change_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("changes.id", ondelete="CASCADE"), primary_key=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True
    )

    change: Mapped[Change] = relationship("Change", back_populates="asset_links")


class TicketAssetLink(Base):
    """Link between a support ticket and an asset (backend-persisted)."""

    __tablename__ = "ticket_asset_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    linked_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


__all__ = [
    "ApprovalDecision",
    "CHANGE_TERMINAL_STATUSES",
    "CHANGE_TRANSITIONS",
    "Change",
    "ChangeApproval",
    "ChangeAssetLink",
    "ChangeEvent",
    "ChangeEventType",
    "ChangeStatus",
    "ChangeTask",
    "ChangeType",
    "TicketAssetLink",
]
