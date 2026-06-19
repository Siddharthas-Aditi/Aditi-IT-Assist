"""API tests for the staff ticket-detail endpoint (GET /tickets/{id}).

RBAC: it_agent and above only. Service is patched so no DB is required.
"""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

TID = "00000000-0000-0000-0000-000000000123"


class TestStaffTicketDetail:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get(f"/api/v1/tickets/{TID}")
        assert resp.status_code == 401

    async def test_employee_forbidden(self, employee_client: AsyncClient):
        resp = await employee_client.get(f"/api/v1/tickets/{TID}")
        assert resp.status_code == 403

    async def test_agent_404_when_missing(self, agent_client: AsyncClient):
        with patch("app.api.v1.tickets.TicketService") as cls:
            cls.return_value.get_ticket_for_agent = AsyncMock(return_value=None)
            resp = await agent_client.get(f"/api/v1/tickets/{TID}")
        assert resp.status_code == 404
