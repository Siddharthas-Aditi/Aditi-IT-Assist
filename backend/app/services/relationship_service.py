"""Application service for read-only Change, Asset, and Ticket links."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.schemas.relationships import (
    AssetChangeLinksResponse,
    AssetTicketLinksResponse,
    ChangeAssetLinksResponse,
    LinkedAssetOut,
    LinkedChangeOut,
    LinkedTicketOut,
    TicketAssetLinksResponse,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class RelationshipNotFoundError(Exception):
    """The resource at the root of a relationship view does not exist."""


class RelationshipService:
    """Expose persisted links through a single API → service → repository path."""

    def __init__(self, db: AsyncSession) -> None:
        from app.repositories.relationship_repository import RelationshipRepository

        self._repo = RelationshipRepository(db)

    async def change_assets(self, change_id: uuid.UUID) -> ChangeAssetLinksResponse:
        if await self._repo.get_change(change_id) is None:
            raise RelationshipNotFoundError(f"Change {change_id} not found")
        assets = await self._repo.assets_for_change(change_id)
        return ChangeAssetLinksResponse(
            items=[
                LinkedAssetOut(
                    id=asset.id,
                    asset_tag=asset.asset_tag,
                    name=asset.name,
                    status=asset.status,
                )
                for asset in assets
            ]
        )

    async def asset_changes(self, asset_id: uuid.UUID) -> AssetChangeLinksResponse:
        if await self._repo.get_asset(asset_id) is None:
            raise RelationshipNotFoundError(f"Asset {asset_id} not found")
        changes = await self._repo.changes_for_asset(asset_id)
        return AssetChangeLinksResponse(
            items=[
                LinkedChangeOut(
                    id=change.id,
                    change_number=change.change_number,
                    title=change.title,
                    status=change.status,
                )
                for change in changes
            ]
        )

    async def asset_tickets(self, asset_id: uuid.UUID) -> AssetTicketLinksResponse:
        if await self._repo.get_asset(asset_id) is None:
            raise RelationshipNotFoundError(f"Asset {asset_id} not found")
        tickets = await self._repo.tickets_for_asset(asset_id)
        return AssetTicketLinksResponse(
            items=[
                LinkedTicketOut(
                    id=ticket.id,
                    ticket_number=ticket.ticket_number,
                    title=ticket.title,
                    status=ticket.status,
                    priority=ticket.priority,
                )
                for ticket in tickets
            ]
        )

    async def ticket_assets(self, ticket_id: uuid.UUID) -> TicketAssetLinksResponse:
        if await self._repo.get_ticket(ticket_id) is None:
            raise RelationshipNotFoundError(f"Ticket {ticket_id} not found")
        assets = await self._repo.assets_for_ticket(ticket_id)
        return TicketAssetLinksResponse(
            items=[
                LinkedAssetOut(
                    id=asset.id,
                    asset_tag=asset.asset_tag,
                    name=asset.name,
                    status=asset.status,
                )
                for asset in assets
            ]
        )


__all__ = ["RelationshipNotFoundError", "RelationshipService"]
