"""Repository for Change management — all DB access goes through here."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.models.change import (
    Change,
    ChangeApproval,
    ChangeAssetLink,
    ChangeEvent,
    ChangeStatus,
    ChangeTask,
    TicketAssetLink,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class ChangeRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, change: Change) -> Change:
        self._db.add(change)
        await self._db.flush()
        return change

    async def get(self, change_id: uuid.UUID) -> Change | None:
        result = await self._db.execute(select(Change).where(Change.id == change_id))
        return result.scalar_one_or_none()

    async def get_by_number(self, change_number: str) -> Change | None:
        result = await self._db.execute(select(Change).where(Change.change_number == change_number))
        return result.scalar_one_or_none()

    async def find_all(
        self,
        *,
        status: ChangeStatus | None = None,
        requested_by_id: uuid.UUID | None = None,
        assigned_to_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Change], int]:
        stmt = select(Change)
        if status is not None:
            stmt = stmt.where(Change.status == status)
        if requested_by_id is not None:
            stmt = stmt.where(Change.requested_by_id == requested_by_id)
        if assigned_to_id is not None:
            stmt = stmt.where(Change.assigned_to_id == assigned_to_id)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._db.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(Change.created_at.desc()).limit(limit).offset(offset)
        rows = (await self._db.execute(stmt)).scalars().all()
        return list(rows), int(total)

    async def update(self, change: Change) -> Change:
        change.updated_at = datetime.now(UTC)
        self._db.add(change)
        await self._db.flush()
        return change

    async def delete(self, change: Change) -> None:
        await self._db.delete(change)
        await self._db.flush()

    async def next_change_number(self) -> str:
        result = await self._db.execute(select(func.max(Change.change_number)))
        max_val: str | None = result.scalar()
        if max_val:
            try:
                num = int(max_val.replace("CHG-", ""))
            except ValueError:
                num = 1000
        else:
            num = 1000
        return f"CHG-{num + 1}"

    # ── Approvals ──────────────────────────────────────────────────────

    async def add_approval(self, approval: ChangeApproval) -> ChangeApproval:
        self._db.add(approval)
        await self._db.flush()
        return approval

    async def get_approval(self, approval_id: uuid.UUID) -> ChangeApproval | None:
        result = await self._db.execute(
            select(ChangeApproval).where(ChangeApproval.id == approval_id)
        )
        return result.scalar_one_or_none()

    async def update_approval(self, approval: ChangeApproval) -> ChangeApproval:
        self._db.add(approval)
        await self._db.flush()
        return approval

    # ── Tasks ───────────────────────────────────────────────────────────

    async def add_task(self, task: ChangeTask) -> ChangeTask:
        self._db.add(task)
        await self._db.flush()
        return task

    async def get_task(self, task_id: uuid.UUID) -> ChangeTask | None:
        result = await self._db.execute(select(ChangeTask).where(ChangeTask.id == task_id))
        return result.scalar_one_or_none()

    async def update_task(self, task: ChangeTask) -> ChangeTask:
        self._db.add(task)
        await self._db.flush()
        return task

    async def delete_task(self, task: ChangeTask) -> None:
        await self._db.delete(task)
        await self._db.flush()

    # ── Events (append-only audit trail) ────────────────────────────────

    async def append_event(self, event: ChangeEvent) -> ChangeEvent:
        self._db.add(event)
        await self._db.flush()
        return event

    # ── Asset links ─────────────────────────────────────────────────────

    async def set_asset_links(self, change_id: uuid.UUID, asset_ids: list[uuid.UUID]) -> None:
        existing = (
            (
                await self._db.execute(
                    select(ChangeAssetLink).where(ChangeAssetLink.change_id == change_id)
                )
            )
            .scalars()
            .all()
        )
        for link in existing:
            await self._db.delete(link)
        for aid in asset_ids:
            self._db.add(ChangeAssetLink(change_id=change_id, asset_id=aid))
        await self._db.flush()

    async def get_asset_ids(self, change_id: uuid.UUID) -> list[uuid.UUID]:
        rows = (
            (
                await self._db.execute(
                    select(ChangeAssetLink.asset_id).where(ChangeAssetLink.change_id == change_id)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    # ── Ticket-Asset links ───────────────────────────────────────────────

    async def link_ticket_asset(self, link: TicketAssetLink) -> TicketAssetLink:
        self._db.add(link)
        await self._db.flush()
        return link

    async def get_assets_for_ticket(self, ticket_id: uuid.UUID) -> list[uuid.UUID]:
        rows = (
            (
                await self._db.execute(
                    select(TicketAssetLink.asset_id).where(TicketAssetLink.ticket_id == ticket_id)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)


__all__ = ["ChangeRepository"]
