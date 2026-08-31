"""Repository for the durable approval queue.

All DB access for PendingApprovalRecord goes through this class. The
ApprovalQueue service holds no session; each method receives or creates
one via the caller's async context.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from app.models.pending_approval import PendingApprovalRecord

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class PendingApprovalRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, record: PendingApprovalRecord) -> PendingApprovalRecord:
        self._db.add(record)
        await self._db.flush()
        return record

    async def get(self, approval_id: str) -> PendingApprovalRecord | None:
        result = await self._db.execute(
            select(PendingApprovalRecord).where(PendingApprovalRecord.id == approval_id)
        )
        return result.scalar_one_or_none()

    async def get_for_update(self, approval_id: str) -> PendingApprovalRecord | None:
        """Acquire a row-level lock for atomic claim-before-execute."""
        result = await self._db.execute(
            select(PendingApprovalRecord)
            .where(PendingApprovalRecord.id == approval_id)
            .with_for_update(nowait=False)
        )
        return result.scalar_one_or_none()

    async def list_by_status(self, status: str | None = None) -> list[PendingApprovalRecord]:
        stmt = select(PendingApprovalRecord).order_by(PendingApprovalRecord.created_at.desc())
        if status is not None:
            stmt = stmt.where(PendingApprovalRecord.status == status)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_executing(self) -> list[PendingApprovalRecord]:
        """Return all rows stuck in EXECUTING state (crash recovery)."""
        result = await self._db.execute(
            select(PendingApprovalRecord).where(PendingApprovalRecord.status == "executing")
        )
        return list(result.scalars().all())

    async def reset_executing_to_pending(self) -> int:
        """Startup reconciliation: reset crashed-mid-execution rows to PENDING.

        Sets ``recovered_at`` to NOW so approvers can see these are stale.
        Returns the number of rows recovered.
        """
        now = datetime.now(UTC)
        result = await self._db.execute(
            update(PendingApprovalRecord)
            .where(PendingApprovalRecord.status == "executing")
            .values(status="pending", recovered_at=now)
            .returning(PendingApprovalRecord.id)
        )
        rows = result.fetchall()
        await self._db.flush()
        return len(rows)


__all__ = ["PendingApprovalRepository"]
