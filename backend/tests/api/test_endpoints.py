"""API integration tests."""

import pytest
from httpx import ASGITransport, AsyncClient

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
    async def test_send_message_returns_response(self, client: AsyncClient):
        """Should accept a chat message and return structured response."""
        response = await client.post(
            "/api/v1/chat/message",
            json={"message": "My Outlook is not receiving emails"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "message_id" in data
        assert "content" in data
        assert "confidence_score" in data
        assert isinstance(data["confidence_score"], float)

    @pytest.mark.asyncio
    async def test_send_message_with_session_id(self, client: AsyncClient):
        """Should use provided session_id."""
        response = await client.post(
            "/api/v1/chat/message",
            json={"session_id": "my-session-123", "message": "Help with Zoom"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "my-session-123"

    @pytest.mark.asyncio
    async def test_send_empty_message_rejected(self, client: AsyncClient):
        """Should reject empty messages."""
        response = await client.post(
            "/api/v1/chat/message",
            json={"message": ""},
        )
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_list_sessions(self, client: AsyncClient):
        """Should return session list (empty for now)."""
        response = await client.get("/api/v1/chat/sessions")
        assert response.status_code == 200
        assert response.json() == []


class TestTicketEndpoint:
    """Tests for the ticket endpoint."""

    @pytest.mark.asyncio
    async def test_create_ticket(self, client: AsyncClient):
        """Should create a new ticket."""
        response = await client.post(
            "/api/v1/tickets",
            json={
                "title": "Camera not working after update",
                "description": "After Windows update, my webcam stopped functioning in all apps",
                "priority": "high",
                "category": "hardware/camera",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "ticket_id" in data
        assert data["title"] == "Camera not working after update"
        assert data["status"] == "open"
        assert data["priority"] == "high"

    @pytest.mark.asyncio
    async def test_create_ticket_validation(self, client: AsyncClient):
        """Should reject ticket with too-short title."""
        response = await client.post(
            "/api/v1/tickets",
            json={"title": "Hi", "description": "This is a valid description"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_tickets(self, client: AsyncClient):
        """Should return paginated ticket list."""
        response = await client.get("/api/v1/tickets")
        assert response.status_code == 200
        data = response.json()
        assert "tickets" in data
        assert "total" in data


class TestKnowledgeEndpoint:
    """Tests for the knowledge base endpoint."""

    @pytest.mark.asyncio
    async def test_search_knowledge(self, client: AsyncClient):
        """Should search knowledge base."""
        response = await client.get(
            "/api/v1/knowledge/search",
            params={"query": "outlook email"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "total" in data
        assert data["query"] == "outlook email"

    @pytest.mark.asyncio
    async def test_list_articles(self, client: AsyncClient):
        """Should list knowledge articles."""
        response = await client.get("/api/v1/knowledge")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
