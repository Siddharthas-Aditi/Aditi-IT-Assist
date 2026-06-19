"""API test for the employee live-chat join endpoint (GET /specialist-chat/active).

Lets the employee discover a specialist session the moment it starts. Service
is patched so no DB is required for the no-session path.
"""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

URL = "/api/v1/specialist-chat/active"


class TestActiveSession:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get(URL)
        assert resp.status_code == 401

    async def test_returns_null_when_no_session(self, employee_client: AsyncClient):
        with patch("app.api.v1.specialist_chat.SpecialistChatService") as cls:
            cls.return_value.get_active_for_participant = AsyncMock(return_value=None)
            resp = await employee_client.get(URL)
        assert resp.status_code == 200
        assert resp.json()["session_id"] is None
