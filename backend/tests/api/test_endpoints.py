"""API integration tests."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    async def test_health_check(self, client: AsyncClient):
        """Should return healthy status."""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "aditi-it-assist"

    async def test_readiness_check_ready_when_db_ok(self, client: AsyncClient):
        """Readiness returns ready + per-dependency checks when the DB responds."""
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def fake_connect():
            conn = AsyncMock()
            yield conn

        fake_engine = MagicMock()
        fake_engine.connect = fake_connect
        fake_redis = AsyncMock()

        with (
            patch("app.core.database.engine", fake_engine),
            patch("redis.asyncio.from_url", return_value=fake_redis),
        ):
            response = await client.get("/api/v1/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["checks"]["database"] == "ok"
        assert data["checks"]["redis"] == "ok"

    async def test_readiness_check_503_when_db_down(self, client: AsyncClient):
        """Readiness must gate on the database — LBs stop routing on 503."""
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def broken_connect():
            raise ConnectionError("db down")
            yield  # pragma: no cover

        fake_engine = MagicMock()
        fake_engine.connect = broken_connect

        with patch("app.core.database.engine", fake_engine):
            response = await client.get("/api/v1/health/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "not_ready"


class TestChatEndpoint:
    """Tests for the chat endpoint."""

    async def test_send_message_requires_auth(self, client: AsyncClient):
        """Chat endpoint requires authentication."""
        response = await client.post(
            "/api/v1/chat/message",
            json={"message": "My Outlook is not receiving emails"},
        )
        assert response.status_code == 401

    async def test_send_message_returns_response(self, employee_client: AsyncClient):
        """Authenticated user should get a structured response."""
        response = await employee_client.post(
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

    async def test_send_message_with_session_id(self, employee_client: AsyncClient):
        """Should use provided session_id."""
        response = await employee_client.post(
            "/api/v1/chat/message",
            json={"session_id": "my-session-123", "message": "Help with Zoom"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "my-session-123"

    async def test_send_empty_message_rejected(self, employee_client: AsyncClient):
        """Should reject empty messages."""
        response = await employee_client.post(
            "/api/v1/chat/message",
            json={"message": ""},
        )
        assert response.status_code == 422  # Validation error

    async def test_list_sessions_requires_auth(self, client: AsyncClient):
        """Session list requires authentication."""
        response = await client.get("/api/v1/chat/sessions")
        assert response.status_code == 401

    async def test_list_sessions_authenticated(self, employee_client: AsyncClient):
        """Authenticated user gets empty session list."""
        response = await employee_client.get("/api/v1/chat/sessions")
        assert response.status_code == 200
        assert response.json() == []


class TestTicketEndpointAuth:
    """Tests that ticket endpoints enforce authentication."""

    async def test_create_ticket_requires_auth(self, client: AsyncClient):
        """Creating a ticket without auth should return 401."""
        response = await client.post(
            "/api/v1/tickets",
            json={
                "title": "Camera not working",
                "description": "Camera is broken after update",
            },
        )
        assert response.status_code == 401

    async def test_list_my_tickets_requires_auth(self, client: AsyncClient):
        """Listing own tickets without auth should return 401."""
        response = await client.get("/api/v1/tickets/my")
        assert response.status_code == 401

    async def test_queue_requires_it_agent_role(self, client: AsyncClient):
        """Queue endpoint requires IT agent or above."""
        response = await client.get("/api/v1/tickets/queue")
        assert response.status_code == 401


class TestTicketEndpointWithAuth:
    """Tests for ticket endpoints with proper authentication."""

    async def test_create_ticket_as_employee(self, employee_client: AsyncClient):
        """Employee can create a ticket when authenticated."""
        # Mock the TicketService so no real DB is needed
        mock_ticket = MagicMock()
        mock_ticket.id = uuid.uuid4()
        mock_ticket.ticket_number = "TKT-2026-0001"
        mock_ticket.title = "Camera not working after update"
        mock_ticket.description = "After Windows update, my webcam stopped working"
        mock_ticket.status = "new"
        mock_ticket.priority = "high"
        mock_ticket.category = "hardware/camera"
        mock_ticket.requester_id = uuid.uuid4()
        mock_ticket.assigned_to = None
        mock_ticket.created_at = datetime.now(UTC)
        mock_ticket.sla_response_target = None
        mock_ticket.sla_resolution_target = None
        mock_ticket.ai_summary = None
        mock_ticket.resolution_notes = None

        with patch("app.api.v1.tickets.TicketService") as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.create_ticket.return_value = mock_ticket
            mock_svc_cls.return_value = mock_svc

            response = await employee_client.post(
                "/api/v1/tickets",
                json={
                    "title": "Camera not working after update",
                    "description": "After Windows update, my webcam stopped working",
                    "priority": "high",
                    "category": "hardware/camera",
                },
            )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["status"] == "new"
        assert data["priority"] == "high"

    async def test_list_my_tickets_as_employee(self, employee_client: AsyncClient):
        """Employee can list their own tickets."""
        with patch("app.api.v1.tickets.TicketService") as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.list_tickets_for_employee.return_value = []
            mock_svc_cls.return_value = mock_svc

            response = await employee_client.get("/api/v1/tickets/my")
        assert response.status_code == 200
        data = response.json()
        assert "tickets" in data
        assert data["tickets"] == []
        assert "total" in data

    async def test_queue_accessible_to_it_agent(self, agent_client: AsyncClient):
        """IT agent can access the ticket queue."""
        with patch("app.api.v1.tickets.TicketService") as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.list_tickets_for_agent.return_value = ([], 0)
            mock_svc_cls.return_value = mock_svc

            response = await agent_client.get("/api/v1/tickets/queue")
        assert response.status_code == 200

    async def test_employee_cannot_access_queue(self, employee_client: AsyncClient):
        """Employee cannot access the IT agent queue."""
        response = await employee_client.get("/api/v1/tickets/queue")
        assert response.status_code == 403


class TestKnowledgeEndpoint:
    """Tests for the knowledge base endpoint."""

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

    async def test_list_articles(self, client: AsyncClient):
        """Should list knowledge articles."""
        response = await client.get("/api/v1/knowledge")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestAnalyticsEndpointAuth:
    """Tests that analytics endpoints enforce IT Lead+ role."""

    async def test_dashboard_requires_auth(self, client: AsyncClient):
        """Analytics dashboard requires authentication."""
        response = await client.get("/api/v1/analytics/dashboard")
        assert response.status_code == 401

    async def test_dashboard_forbidden_for_employee(self, employee_client: AsyncClient):
        """Analytics dashboard is forbidden for regular employees."""
        response = await employee_client.get("/api/v1/analytics/dashboard")
        assert response.status_code == 403

    async def test_dashboard_accessible_to_it_lead(self, lead_client: AsyncClient):
        """IT lead can access analytics dashboard."""
        with patch("app.api.v1.analytics.AnalyticsService") as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.get_dashboard_summary.return_value = {
                "ticket_metrics": {},
                "ai_metrics": {},
                "sla_metrics": {},
                "remote_support_metrics": {},
                "period": {},
            }
            mock_svc_cls.return_value = mock_svc
            response = await lead_client.get("/api/v1/analytics/dashboard")
        assert response.status_code == 200


class TestAdminEndpointAuth:
    """Tests that admin endpoints enforce it_admin / security_auditor roles."""

    async def test_stats_requires_auth(self, client: AsyncClient):
        """Admin stats require authentication."""
        response = await client.get("/api/v1/admin/stats")
        assert response.status_code == 401

    async def test_stats_forbidden_for_employee(self, employee_client: AsyncClient):
        """Regular employees cannot access admin stats."""
        response = await employee_client.get("/api/v1/admin/stats")
        assert response.status_code == 403

    async def test_stats_forbidden_for_it_agent(self, agent_client: AsyncClient):
        """IT agents cannot access admin stats."""
        response = await agent_client.get("/api/v1/admin/stats")
        assert response.status_code == 403

    async def test_stats_accessible_to_admin(self, admin_client: AsyncClient):
        """IT admin can access admin stats.

        AdminStatsService is mocked (like AuditQueryService below): this class
        tests RBAC enforcement, not aggregation SQL — aggregation is covered by
        service-level tests against a real DB.
        """
        from app.schemas.admin import SystemStats

        with patch("app.api.v1.admin.AdminStatsService") as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.get_system_stats.return_value = SystemStats()
            mock_svc_cls.return_value = mock_svc
            response = await admin_client.get("/api/v1/admin/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_sessions" in data
        assert "resolution_rate" in data

    async def test_audit_log_requires_auth(self, client: AsyncClient):
        """Audit log requires authentication."""
        response = await client.get("/api/v1/admin/audit-log")
        assert response.status_code == 401

    async def test_audit_log_forbidden_for_employee(self, employee_client: AsyncClient):
        """Regular employees cannot access audit log."""
        response = await employee_client.get("/api/v1/admin/audit-log")
        assert response.status_code == 403

    async def test_audit_log_accessible_to_admin(self, admin_client: AsyncClient):
        """IT admin can access audit log."""
        with patch("app.api.v1.admin.AuditQueryService") as mock_svc_cls:
            mock_svc = AsyncMock()
            mock_svc.list_events.return_value = ([], 0)
            mock_svc_cls.return_value = mock_svc
            response = await admin_client.get("/api/v1/admin/audit-log")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "total" in data
