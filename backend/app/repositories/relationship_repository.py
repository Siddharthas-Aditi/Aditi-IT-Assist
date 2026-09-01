"""Persistence boundary for read-only ITSM relationship views."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.asset import Asset
from app.models.change import Change, ChangeAssetLink, TicketAssetLink
from app.models.ticket import Ticket

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class RelationshipRepository:
    """Fetch existing M2M links without changing their lifecycle semantics."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_change(self, change_id: uuid.UUID) -> Change | None:
        return await self._db.get(Change, change_id)

    async def get_asset(self, asset_id: uuid.UUID) -> Asset | None:
        return await self._db.get(Asset, asset_id)

    async def get_ticket(self, ticket_id: uuid.UUID) -> Ticket | None:
        return await self._db.get(Ticket, ticket_id)

    async def assets_for_change(self, change_id: uuid.UUID) -> list[Asset]:
        result = await self._db.scalars(
            select(Asset)
            .join(ChangeAssetLink, ChangeAssetLink.asset_id == Asset.id)
            .where(ChangeAssetLink.change_id == change_id)
            .order_by(Asset.asset_tag)
        )
        return list(result.all())

    async def changes_for_asset(self, asset_id: uuid.UUID) -> list[Change]:
        result = await self._db.scalars(
            select(Change)
            .join(ChangeAssetLink, ChangeAssetLink.change_id == Change.id)
            .where(ChangeAssetLink.asset_id == asset_id)
            .order_by(Change.created_at.desc())
        )
        return list(result.all())

    async def tickets_for_asset(self, asset_id: uuid.UUID) -> list[Ticket]:
        result = await self._db.scalars(
            select(Ticket)
            .join(TicketAssetLink, TicketAssetLink.ticket_id == Ticket.id)
            .where(TicketAssetLink.asset_id == asset_id)
            .order_by(Ticket.created_at.desc())
        )
        return list(result.all())

    async def assets_for_ticket(self, ticket_id: uuid.UUID) -> list[Asset]:
        result = await self._db.scalars(
            select(Asset)
            .join(TicketAssetLink, TicketAssetLink.asset_id == Asset.id)
            .where(TicketAssetLink.ticket_id == ticket_id)
            .order_by(Asset.asset_tag)
        )
        return list(result.all())


__all__ = ["RelationshipRepository"]
