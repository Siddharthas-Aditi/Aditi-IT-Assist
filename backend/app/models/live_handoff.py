"""Live-handoff presence + offer models.

`specialist_availability` — one row per specialist tracking Available/Away + a
heartbeat, so auto-routing only offers to genuinely-present specialists (survives
restarts and is correct across workers).

`live_handoff_offers` — the connection-attempt lifecycle for a queued live-support
ticket: a targeted offer to one specialist that the sweeper advances (re-offer →
broaden → fallback) until a specialist accepts or the attempt is exhausted.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

SPECIALIST_AVAILABILITY_STATUSES = ("available", "away")
LIVE_HANDOFF_OFFER_STATES = ("offered", "accepted", "expired", "broadened", "fallback")


class SpecialistAvailability(TimestampMixin, Base):
    """Presence for a single specialist. PK is the user id (one row per specialist)."""

    __tablename__ = "specialist_availability"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(
        Enum(*SPECIALIST_AVAILABILITY_STATUSES, name="specialist_availability_status"),
        nullable=False,
        default="away",
        server_default="away",
    )
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class LiveHandoffOffer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One connection attempt for a queued live-support ticket."""

    __tablename__ = "live_handoff_offers"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    offered_to: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    offered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    round_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str] = mapped_column(
        Enum(*LIVE_HANDOFF_OFFER_STATES, name="live_handoff_offer_state"),
        nullable=False,
        default="offered",
        index=True,
    )
