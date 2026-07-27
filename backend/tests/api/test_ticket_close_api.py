from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

TID = "00000000-0000-0000-0000-000000000123"


def _closed_ticket():
    t = MagicMock()
    t.id = TID
    t.ticket_number = "ITA-0001"
    t.title = "VPN"
    t.description = "down"
    t.status = "closed"
    t.priority = "medium"
    t.category = "Incident"
    t.subcategory = "Network Connectivity"
    t.item = "VPN"
    t.ticket_type = None
    t.source = "chat"
    t.urgency = None
    t.impact = None
    t.requester_id = "00000000-0000-0000-0000-000000000099"
    t.assigned_to = None
    t.created_at = MagicMock()
    t.created_at.isoformat.return_value = "2026-07-27T00:00:00+00:00"
    t.sla_response_target = None
    t.sla_resolution_target = None
    t.ai_summary = None
    t.resolution_notes = "Fixed"
    t.close_notes = None
    t.closed_by = "00000000-0000-0000-0000-000000000001"
    t.closed_at = MagicMock()
    t.closed_at.isoformat.return_value = "2026-07-27T01:00:00+00:00"
    t.resolved_at = t.closed_at
    return t


class TestCloseApi:
    async def test_employee_forbidden(self, employee_client: AsyncClient):
        resp = await employee_client.post(
            f"/api/v1/tickets/{TID}/close",
            json={
                "resolution_notes": "done",
                "category": "Incident",
                "subcategory": "Network Connectivity",
                "item": "VPN",
            },
        )
        assert resp.status_code == 403

    async def test_status_closed_rejected(self, agent_client: AsyncClient):
        with patch("app.api.v1.tickets.TicketService") as cls:
            cls.return_value.update_status = AsyncMock(
                side_effect=ValueError("Use POST /tickets/{id}/close")
            )
            resp = await agent_client.post(
                f"/api/v1/tickets/{TID}/status",
                json={"status": "closed"},
            )
        assert resp.status_code == 409

    async def test_close_ok(self, agent_client: AsyncClient):
        with patch("app.api.v1.tickets.TicketService") as cls:
            cls.return_value.close_ticket = AsyncMock(return_value=_closed_ticket())
            resp = await agent_client.post(
                f"/api/v1/tickets/{TID}/close",
                json={
                    "resolution_notes": "Fixed VPN profile",
                    "category": "Incident",
                    "subcategory": "Network Connectivity",
                    "item": "VPN",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "closed"
