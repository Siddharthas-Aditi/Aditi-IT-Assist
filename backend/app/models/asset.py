"""Asset management models — IT asset lifecycle and audit trail."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AssetStatus(StrEnum):
    IN_STOCK = "in_stock"
    ASSIGNED = "assigned"
    IN_USE = "in_use"
    UNDER_REPAIR = "under_repair"
    RESERVED = "reserved"
    LOST = "lost"
    RETIRED = "retired"
    DISPOSED = "disposed"


ASSET_TERMINAL_STATUSES = {AssetStatus.RETIRED, AssetStatus.DISPOSED}
ASSET_ASSIGNMENT_STATUSES = {AssetStatus.ASSIGNED, AssetStatus.IN_USE}

# Assignment statuses require assigned_to_id and assigned_date.
# Terminal statuses require retirement_reason and retirement_date.


class AssetHardwareType(StrEnum):
    PHYSICAL = "physical"
    VIRTUAL = "virtual"


class AssetUsageType(StrEnum):
    PERMANENT = "permanent"
    LOANER = "loaner"
    TEMPORARY = "temporary"
    SHARED = "shared"


class AssetCondition(StrEnum):
    NEW = "new"
    GOOD = "good"
    FAIR = "fair"
    MINOR_DAMAGE = "minor_damage"
    DAMAGED = "damaged"
    FAULTY = "faulty"


class AssetEventType(StrEnum):
    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    ASSIGNED = "assigned"
    UNASSIGNED = "unassigned"
    TRANSFERRED = "transferred"
    RETIRED = "retired"
    FIELD_UPDATED = "field_updated"
    LINKED_TO_CHANGE = "linked_to_change"
    LINKED_TO_TICKET = "linked_to_ticket"


class Asset(Base):
    """An IT asset with full lifecycle and assignment tracking."""

    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_tag: Mapped[str] = mapped_column(sa.String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(sa.String(128), nullable=False, default="")
    impact: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="low")
    description: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        Enum(AssetStatus, name="asset_status_enum"),
        nullable=False,
        default=AssetStatus.IN_STOCK,
        index=True,
    )
    hardware_type: Mapped[str] = mapped_column(
        Enum(AssetHardwareType, name="asset_hardware_type_enum"),
        nullable=False,
        default=AssetHardwareType.PHYSICAL,
    )
    usage_type: Mapped[str] = mapped_column(
        Enum(AssetUsageType, name="asset_usage_type_enum"),
        nullable=False,
        default=AssetUsageType.PERMANENT,
    )
    condition: Mapped[str] = mapped_column(
        Enum(AssetCondition, name="asset_condition_enum"),
        nullable=False,
        default=AssetCondition.GOOD,
    )

    # Hardware identification
    physical_subtype: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    virtual_subtype: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    product: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    model: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    vendor: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(sa.String(255), nullable=True, index=True)
    classification: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)

    # Financial and procurement
    cost: Mapped[float | None] = mapped_column(sa.Numeric(14, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(sa.String(3), nullable=True)
    warranty_info: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    acquisition_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    warranty_expiry: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    po_number: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    contract: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)

    # Network / access point
    ip_address: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    mac_address: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)

    # Ownership and location
    location: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    managed_by_group: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)

    # Lifecycle
    end_of_life: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    retirement_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    retirement_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    source: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    parent_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
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


class AssetEvent(Base):
    """Immutable audit trail entry for an Asset."""

    __tablename__ = "asset_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("assets.id", ondelete="CASCADE"),
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


__all__ = [
    "ASSET_ASSIGNMENT_STATUSES",
    "ASSET_TERMINAL_STATUSES",
    "Asset",
    "AssetCondition",
    "AssetEvent",
    "AssetEventType",
    "AssetHardwareType",
    "AssetStatus",
    "AssetUsageType",
]
