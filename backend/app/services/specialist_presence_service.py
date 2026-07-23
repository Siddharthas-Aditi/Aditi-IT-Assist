"""Specialist presence: explicit Available/Away + heartbeat freshness.

`is_available` is pure so routing decisions are unit-testable. The service is a
thin DB upsert/query layer; it does NOT commit (callers own the transaction).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.logging import get_logger
from app.models.live_handoff import SpecialistAvailability

if TYPE_CHECKING:
    import uuid

logger = get_logger(__name__)


def is_available(
    status: str,
    last_heartbeat_at: datetime | None,
    now: datetime,
    ttl_seconds: int,
) -> bool:
    """True only when explicitly Available AND the heartbeat is fresh."""
    if status != "available" or last_heartbeat_at is None:
        return False
    hb = last_heartbeat_at
    if hb.tzinfo is None:
        hb = hb.replace(tzinfo=UTC)
    return (now - hb) <= timedelta(seconds=ttl_seconds)


class PresenceService:
    def __init__(self, db) -> None:  # AsyncSession
        self.db = db

    async def _upsert(self, user_id: uuid.UUID, *, status: str | None, touch: bool):
        row = await self.db.get(SpecialistAvailability, user_id)
        now = datetime.now(UTC)
        if row is None:
            row = SpecialistAvailability(
                user_id=user_id,
                status=status or "away",
                last_heartbeat_at=now,
            )
            self.db.add(row)
        else:
            if status is not None:
                row.status = status
            if touch:
                row.last_heartbeat_at = now
        await self.db.flush()
        return row

    async def set_status(
        self, user_id: uuid.UUID, status: str
    ) -> SpecialistAvailability:
        if status not in ("available", "away"):
            raise ValueError(f"invalid status {status!r}")
        # Setting a status also counts as presence activity.
        return await self._upsert(user_id, status=status, touch=True)

    async def heartbeat(self, user_id: uuid.UUID) -> SpecialistAvailability:
        return await self._upsert(user_id, status=None, touch=True)

    async def get(self, user_id: uuid.UUID) -> SpecialistAvailability | None:
        return await self.db.get(SpecialistAvailability, user_id)

    async def list_available_ids(
        self, now: datetime | None = None
    ) -> list[uuid.UUID]:
        from app.core.config import settings

        ts = now or datetime.now(UTC)
        ttl = settings.SPECIALIST_PRESENCE_TTL_SECONDS
        rows = (await self.db.execute(select(SpecialistAvailability))).scalars().all()
        return [
            r.user_id for r in rows if is_available(r.status, r.last_heartbeat_at, ts, ttl)
        ]
