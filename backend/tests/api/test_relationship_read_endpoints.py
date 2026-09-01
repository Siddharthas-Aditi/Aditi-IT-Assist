"""Read-contract and RBAC coverage for persisted ITSM relationship tables."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch
from uuid import UUID

from app.schemas.relationships import (
    AssetChangeLinksResponse,
    AssetTicketLinksResponse,
    ChangeAssetLinksResponse,
    LinkedAssetOut,
    LinkedChangeOut,
    LinkedTicketOut,
    TicketAssetLinksResponse,
)
from app.services.relationship_service import RelationshipNotFoundError

if TYPE_CHECKING:
    from httpx import AsyncClient

CHANGE_ID = UUID("00000000-0000-0000-0000-000000000101")
ASSET_ID = UUID("00000000-0000-0000-0000-000000000102")
TICKET_ID = UUID("00000000-0000-0000-0000-000000000103")


class TestChangeAssetLinkReads:
    async def test_employee_can_read_persisted_change_asset_links(
        self, employee_client: AsyncClient
    ):
        payload = ChangeAssetLinksResponse(
            items=[
                LinkedAssetOut(
                    id=ASSET_ID, asset_tag="LT-104", name="Aditi laptop", status="in_use"
                )
            ]
        )
        with patch("app.api.v1.changes.RelationshipService") as service:
            service.return_value.change_assets = AsyncMock(return_value=payload)
            response = await employee_client.get(f"/api/v1/changes/{CHANGE_ID}/asset-links")

        assert response.status_code == 200
        assert response.json() == {
            "items": [
                {
                    "id": str(ASSET_ID),
                    "asset_tag": "LT-104",
                    "name": "Aditi laptop",
                    "status": "in_use",
                }
            ]
        }

    async def test_empty_change_asset_links_are_a_real_empty_result(
        self, employee_client: AsyncClient
    ):
        with patch("app.api.v1.changes.RelationshipService") as service:
            service.return_value.change_assets = AsyncMock(
                return_value=ChangeAssetLinksResponse(items=[])
            )
            response = await employee_client.get(f"/api/v1/changes/{CHANGE_ID}/asset-links")

        assert response.status_code == 200
        assert response.json() == {"items": []}

    async def test_missing_change_is_not_reported_as_empty(self, employee_client: AsyncClient):
        with patch("app.api.v1.changes.RelationshipService") as service:
            service.return_value.change_assets = AsyncMock(
                side_effect=RelationshipNotFoundError("Change missing")
            )
            response = await employee_client.get(f"/api/v1/changes/{CHANGE_ID}/asset-links")

        assert response.status_code == 404


class TestAssetRelationshipReads:
    async def test_employee_can_read_asset_change_links(self, employee_client: AsyncClient):
        payload = AssetChangeLinksResponse(
            items=[
                LinkedChangeOut(
                    id=CHANGE_ID,
                    change_number="CHG-000042",
                    title="Mail migration",
                    status="scheduled",
                )
            ]
        )
        with patch("app.api.v1.assets.RelationshipService") as service:
            service.return_value.asset_changes = AsyncMock(return_value=payload)
            response = await employee_client.get(f"/api/v1/assets/{ASSET_ID}/change-links")

        assert response.status_code == 200
        assert response.json()["items"][0]["change_number"] == "CHG-000042"

    async def test_employee_cannot_read_asset_ticket_links(self, employee_client: AsyncClient):
        response = await employee_client.get(f"/api/v1/assets/{ASSET_ID}/ticket-links")
        assert response.status_code == 403

    async def test_agent_can_read_asset_ticket_links(self, agent_client: AsyncClient):
        payload = AssetTicketLinksResponse(
            items=[
                LinkedTicketOut(
                    id=TICKET_ID,
                    ticket_number="ITA-000042",
                    title="Mailbox full",
                    status="new",
                    priority="high",
                )
            ]
        )
        with patch("app.api.v1.assets.RelationshipService") as service:
            service.return_value.asset_tickets = AsyncMock(return_value=payload)
            response = await agent_client.get(f"/api/v1/assets/{ASSET_ID}/ticket-links")

        assert response.status_code == 200
        assert response.json()["items"][0]["ticket_number"] == "ITA-000042"


class TestTicketAssetLinkReads:
    async def test_employee_cannot_read_ticket_asset_links(self, employee_client: AsyncClient):
        response = await employee_client.get(f"/api/v1/tickets/{TICKET_ID}/asset-links")
        assert response.status_code == 403

    async def test_agent_can_read_ticket_asset_links(self, agent_client: AsyncClient):
        payload = TicketAssetLinksResponse(
            items=[
                LinkedAssetOut(
                    id=ASSET_ID, asset_tag="LT-104", name="Aditi laptop", status="in_use"
                )
            ]
        )
        with patch("app.api.v1.tickets.RelationshipService") as service:
            service.return_value.ticket_assets = AsyncMock(return_value=payload)
            response = await agent_client.get(f"/api/v1/tickets/{TICKET_ID}/asset-links")

        assert response.status_code == 200
        assert response.json()["items"][0]["asset_tag"] == "LT-104"
