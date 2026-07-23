"""DTOs for specialist presence + live-handoff offers.

Presence (`PresenceUpdate`/`PresenceOut`) wraps
``app/services/specialist_presence_service.py`` (explicit Available/Away +
heartbeat freshness). Offers (`OfferOut`) expose the connection-attempt
lifecycle from ``app/services/specialist_handoff_service.py`` so a specialist
can see (and accept) an offer targeted to them.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.specialist_queue import HandoffSummary


class PresenceUpdate(BaseModel):
    """Body for ``PUT /specialist-queue/availability``."""

    status: Literal["available", "away"]


class PresenceOut(BaseModel):
    """A specialist's current presence, including computed freshness.

    ``is_available`` is derived (not stored) — see
    ``specialist_presence_service.is_available`` — so it always reflects the
    current heartbeat TTL rather than a snapshot that can go stale.
    """

    user_id: uuid.UUID
    status: Literal["available", "away"]
    last_heartbeat_at: datetime | None
    is_available: bool


class OfferOut(BaseModel):
    """One active live-handoff offer targeted to the caller."""

    ticket_id: uuid.UUID
    ticket_number: str
    offered_at: datetime
    expires_at: datetime
    round_index: int
    state: str
    summary: HandoffSummary


__all__ = ["OfferOut", "PresenceOut", "PresenceUpdate"]
