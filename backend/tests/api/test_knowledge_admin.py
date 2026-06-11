"""API tests for knowledge management endpoints — permission gating & contracts.

Follows the project pattern: role-overridden clients (from conftest) + patched
service classes so no real database is required. Per-role permissions are
resolved from the canonical permission registry so the gating reflects the real
RBAC matrix.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.core.permissions import UserRole, get_effective_permissions

ADMIN_BASE = "/api/v1/knowledge/admin"


async def _effective(self, user):  # patched onto AuthService.get_user_permissions
    try:
        return {str(p) for p in get_effective_permissions(UserRole(user.primary_role))}
    except ValueError:
        return set()


@pytest.fixture(autouse=True)
def _patch_permissions():
    """Resolve permissions from the registry instead of the DB for all tests here."""
    with patch("app.services.auth.service.AuthService.get_user_permissions", new=_effective):
        yield


# ─────────────────────────────────────────────────────────────────────
# Listing / read gating (KNOWLEDGE_VIEW_INTERNAL)
# ─────────────────────────────────────────────────────────────────────


class TestArticleListGating:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get(f"{ADMIN_BASE}/articles")
        assert resp.status_code == 401

    async def test_employee_forbidden(self, employee_client: AsyncClient):
        resp = await employee_client.get(f"{ADMIN_BASE}/articles")
        assert resp.status_code == 403

    async def test_agent_can_list(self, agent_client: AsyncClient):
        with patch("app.api.v1.knowledge_admin.KnowledgeManagementService") as cls:
            cls.return_value.list_articles = AsyncMock(return_value=([], 0))
            resp = await agent_client.get(f"{ADMIN_BASE}/articles")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    async def test_auditor_can_list(self, auditor_client: AsyncClient):
        with patch("app.api.v1.knowledge_admin.KnowledgeManagementService") as cls:
            cls.return_value.list_articles = AsyncMock(return_value=([], 0))
            resp = await auditor_client.get(f"{ADMIN_BASE}/articles")
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────
# Create gating (KNOWLEDGE_CREATE — agents and above)
# ─────────────────────────────────────────────────────────────────────


class TestCreateGating:
    _payload = {"title": "New KB article", "category": "email/outlook"}

    async def test_employee_cannot_create(self, employee_client: AsyncClient):
        resp = await employee_client.post(f"{ADMIN_BASE}/articles", json=self._payload)
        assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────
# Review queue gating (KNOWLEDGE_REVIEW — lead and above)
# ─────────────────────────────────────────────────────────────────────


class TestReviewQueueGating:
    async def test_agent_cannot_view_review_queue(self, agent_client: AsyncClient):
        resp = await agent_client.get(f"{ADMIN_BASE}/review-queue")
        assert resp.status_code == 403

    async def test_lead_can_view_review_queue(self, lead_client: AsyncClient):
        with patch("app.api.v1.knowledge_admin.KnowledgeManagementService") as cls:
            cls.return_value.review_queue = AsyncMock(return_value=[])
            resp = await lead_client.get(f"{ADMIN_BASE}/review-queue")
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────
# Lifecycle transition error mapping (publish blocked for agents)
# ─────────────────────────────────────────────────────────────────────


class TestTransitionGating:
    async def test_agent_publish_forbidden(self, agent_client: AsyncClient):
        with patch("app.api.v1.knowledge_admin.KnowledgeManagementService") as cls:
            cls.return_value.transition = AsyncMock(
                side_effect=PermissionError("Permission 'knowledge:publish' required to publish")
            )
            resp = await agent_client.post(
                f"{ADMIN_BASE}/articles/00000000-0000-0000-0000-000000000001/transition",
                json={"action": "publish"},
            )
        assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────
# Indexing & analytics gating
# ─────────────────────────────────────────────────────────────────────


class TestIndexingGating:
    _status = {
        "total_articles": 3,
        "published_articles": 3,
        "indexed_articles": 3,
        "pending_articles": 0,
        "stale_articles": 0,
        "failed_articles": 0,
        "total_chunks": 12,
        "index_version": 1,
        "last_indexed_at": None,
        "vector_store": "pgvector",
    }

    async def test_employee_forbidden_status(self, employee_client: AsyncClient):
        resp = await employee_client.get(f"{ADMIN_BASE}/indexing/status")
        assert resp.status_code == 403

    async def test_agent_can_view_status(self, agent_client: AsyncClient):
        with patch("app.api.v1.knowledge_admin.KnowledgeIndexingService") as cls:
            cls.return_value.get_status = AsyncMock(return_value=self._status)
            resp = await agent_client.get(f"{ADMIN_BASE}/indexing/status")
        assert resp.status_code == 200

    async def test_lead_cannot_reindex(self, lead_client: AsyncClient):
        # Reindex requires KNOWLEDGE_REINDEX (admin only).
        resp = await lead_client.post(f"{ADMIN_BASE}/indexing/reindex", json={"only_stale": True})
        assert resp.status_code == 403

    async def test_admin_can_reindex(self, admin_client: AsyncClient):
        with patch("app.api.v1.knowledge_admin.KnowledgeIndexingService") as cls:
            cls.return_value.reindex = AsyncMock(
                return_value={
                    "requested": 0,
                    "reindexed": 0,
                    "chunks_written": 0,
                    "skipped": 0,
                    "errors": [],
                }
            )
            resp = await admin_client.post(
                f"{ADMIN_BASE}/indexing/reindex", json={"only_stale": True}
            )
        assert resp.status_code == 200


class TestAnalyticsGating:
    async def test_agent_forbidden(self, agent_client: AsyncClient):
        resp = await agent_client.get(f"{ADMIN_BASE}/analytics/summary")
        assert resp.status_code == 403

    async def test_lead_can_view(self, lead_client: AsyncClient):
        summary = {
            "total_articles": 1,
            "by_status": {"published": 1},
            "published_articles": 1,
            "stale_articles": 0,
            "avg_quality_score": 0.8,
            "total_views": 10,
            "total_usage": 5,
            "avg_resolution_rate": 0.6,
            "top_articles": [],
            "low_performers": [],
        }
        with patch("app.api.v1.knowledge_admin.KnowledgeAnalyticsService") as cls:
            cls.return_value.summary = AsyncMock(return_value=summary)
            resp = await lead_client.get(f"{ADMIN_BASE}/analytics/summary")
        assert resp.status_code == 200
        assert resp.json()["published_articles"] == 1
