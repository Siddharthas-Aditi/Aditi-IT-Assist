"""API integration tests."""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
async def client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Should return healthy status."""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "aditi-it-assist"

    @pytest.mark.asyncio
    async def test_readiness_check(self, client: AsyncClient):
        """Should return ready status."""
        response = await client.get("/api/v1/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"


class TestChatEndpoint:
    """Tests for the chat endpoint."""

    @pytest.mark.asyncio
    async def test_send_message(self, client: AsyncClient):
        """Should accept a chat message and return response."""
        response = await client.post(
            "/api/v1/chat/message",
            json={"message": "My Outlook is not receiving emails"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "content" in data
        assert data["role"] == "assistant"
