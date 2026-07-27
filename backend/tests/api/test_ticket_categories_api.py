"""API tests for /ticket-categories — RBAC + basic tree read."""

from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient


class TestTicketCategoriesRBAC:
    async def test_tree_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/ticket-categories/tree")
        assert resp.status_code == 401

    async def test_tree_employee_forbidden(self, employee_client: AsyncClient):
        resp = await employee_client.get("/api/v1/ticket-categories/tree")
        assert resp.status_code == 403

    async def test_tree_agent_ok(self, agent_client: AsyncClient):
        with patch("app.api.v1.ticket_categories.TicketCategoryService") as cls:
            inst = cls.return_value
            inst.tree = AsyncMock(return_value={"categories": []})
            resp = await agent_client.get("/api/v1/ticket-categories/tree")
        assert resp.status_code == 200
        assert resp.json() == {"categories": []}

    async def test_create_agent_forbidden(self, agent_client: AsyncClient):
        resp = await agent_client.post(
            "/api/v1/ticket-categories",
            json={"name": "Incident", "level": 1},
        )
        assert resp.status_code == 403

    async def test_create_admin_ok(self, admin_client: AsyncClient):
        cat = MagicMock()
        cat.id = "00000000-0000-0000-0000-000000000001"
        cat.name = "Incident"
        cat.level = 1
        cat.parent_id = None
        cat.is_active = True
        cat.sort_order = 0
        with patch("app.api.v1.ticket_categories.TicketCategoryService") as cls:
            cls.return_value.create = AsyncMock(return_value=cat)
            resp = await admin_client.post(
                "/api/v1/ticket-categories",
                json={"name": "Incident", "level": 1},
            )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Incident"
