"""API tests for the Admin Console endpoints — RBAC gating & contracts.

Follows the project pattern: role-overridden clients (conftest) + patched
service classes so no real database is required. Permissions resolve from the
canonical registry so gating reflects the real RBAC matrix.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.core.permissions import UserRole, get_effective_permissions
from app.schemas.admin import (
    AuditEventDetail,
    SystemStats,
    UserDetail,
)

BASE = "/api/v1/admin"


async def _effective(self, user):  # patched onto AuthService.get_user_permissions
    try:
        return {str(p) for p in get_effective_permissions(UserRole(user.primary_role))}
    except ValueError:
        return set()


@pytest.fixture(autouse=True)
def _patch_permissions():
    with patch("app.services.auth.service.AuthService.get_user_permissions", new=_effective):
        yield


def _sample_user_detail() -> UserDetail:
    return UserDetail(
        id="00000000-0000-0000-0000-000000000010",
        email="someone@aditi.com",
        full_name="Some One",
        is_active=True,
        primary_role="it_agent",
        roles=["it_agent"],
    )


# ─────────────────────────────────────────────────────────────────────
# User management — gating
# ─────────────────────────────────────────────────────────────────────


class TestUserListGating:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get(f"{BASE}/users")
        assert resp.status_code == 401

    async def test_employee_forbidden(self, employee_client: AsyncClient):
        resp = await employee_client.get(f"{BASE}/users")
        assert resp.status_code == 403

    async def test_lead_forbidden_no_manage_users(self, lead_client: AsyncClient):
        # it_lead lacks admin:manage_users in the registry.
        resp = await lead_client.get(f"{BASE}/users")
        assert resp.status_code == 403

    async def test_admin_can_list(self, admin_client: AsyncClient):
        with patch("app.api.v1.admin.AdminUserService") as cls:
            cls.return_value.list_users = AsyncMock(return_value=([], 0))
            resp = await admin_client.get(f"{BASE}/users")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["users"] == []

    async def test_admin_list_passes_filters(self, admin_client: AsyncClient):
        with patch("app.api.v1.admin.AdminUserService") as cls:
            list_mock = AsyncMock(return_value=([], 0))
            cls.return_value.list_users = list_mock
            resp = await admin_client.get(
                f"{BASE}/users", params={"search": "ann", "role": "it_agent", "status": "active"}
            )
        assert resp.status_code == 200
        _, kwargs = list_mock.call_args
        assert kwargs["search"] == "ann"
        assert kwargs["role"] == "it_agent"
        assert kwargs["status"] == "active"


class TestRoleManagementGating:
    async def test_assign_role_requires_assign_perm(self, lead_client: AsyncClient):
        resp = await lead_client.post(
            f"{BASE}/users/00000000-0000-0000-0000-000000000010/roles",
            json={"role": "it_agent"},
        )
        assert resp.status_code == 403

    async def test_admin_can_assign_role(self, admin_client: AsyncClient):
        with patch("app.api.v1.admin.AdminUserService") as cls:
            cls.return_value.assign_role = AsyncMock(return_value=_sample_user_detail())
            resp = await admin_client.post(
                f"{BASE}/users/00000000-0000-0000-0000-000000000010/roles",
                json={"role": "it_agent"},
            )
        assert resp.status_code == 200
        assert resp.json()["email"] == "someone@aditi.com"

    async def test_admin_can_revoke_role(self, admin_client: AsyncClient):
        with patch("app.api.v1.admin.AdminUserService") as cls:
            cls.return_value.revoke_role = AsyncMock(return_value=_sample_user_detail())
            resp = await admin_client.delete(
                f"{BASE}/users/00000000-0000-0000-0000-000000000010/roles/it_agent"
            )
        assert resp.status_code == 200

    async def test_update_user_admin_ok(self, admin_client: AsyncClient):
        with patch("app.api.v1.admin.AdminUserService") as cls:
            cls.return_value.update_user = AsyncMock(return_value=_sample_user_detail())
            resp = await admin_client.patch(
                f"{BASE}/users/00000000-0000-0000-0000-000000000010",
                json={"is_active": False},
            )
        assert resp.status_code == 200

    async def test_invalid_uuid_rejected(self, admin_client: AsyncClient):
        resp = await admin_client.get(f"{BASE}/users/not-a-uuid")
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────
# Audit log — gating
# ─────────────────────────────────────────────────────────────────────


class TestAuditLogGating:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get(f"{BASE}/audit-log")
        assert resp.status_code == 401

    async def test_employee_forbidden(self, employee_client: AsyncClient):
        resp = await employee_client.get(f"{BASE}/audit-log")
        assert resp.status_code == 403

    async def test_agent_forbidden(self, agent_client: AsyncClient):
        resp = await agent_client.get(f"{BASE}/audit-log")
        assert resp.status_code == 403

    async def test_auditor_can_view(self, auditor_client: AsyncClient):
        with patch("app.api.v1.admin.AuditQueryService") as cls:
            cls.return_value.list_events = AsyncMock(return_value=([], 0))
            resp = await auditor_client.get(f"{BASE}/audit-log")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    async def test_admin_can_view(self, admin_client: AsyncClient):
        with patch("app.api.v1.admin.AuditQueryService") as cls:
            cls.return_value.list_events = AsyncMock(return_value=([], 0))
            resp = await admin_client.get(f"{BASE}/audit-log", params={"severity": "warning"})
        assert resp.status_code == 200

    async def test_event_detail_404(self, admin_client: AsyncClient):
        with patch("app.api.v1.admin.AuditQueryService") as cls:
            cls.return_value.get_event = AsyncMock(return_value=None)
            resp = await admin_client.get(
                f"{BASE}/audit-log/00000000-0000-0000-0000-0000000000ff"
            )
        assert resp.status_code == 404

    async def test_event_detail_ok(self, admin_client: AsyncClient):
        detail = AuditEventDetail(
            id="00000000-0000-0000-0000-0000000000ff",
            action="role_assigned",
            resource_type="user",
            severity="warning",
            created_at=datetime.now(UTC),
        )
        with patch("app.api.v1.admin.AuditQueryService") as cls:
            cls.return_value.get_event = AsyncMock(return_value=detail)
            resp = await admin_client.get(
                f"{BASE}/audit-log/00000000-0000-0000-0000-0000000000ff"
            )
        assert resp.status_code == 200
        assert resp.json()["action"] == "role_assigned"


# ─────────────────────────────────────────────────────────────────────
# System stats — gating
# ─────────────────────────────────────────────────────────────────────


class TestStatsGating:
    async def test_lead_forbidden(self, lead_client: AsyncClient):
        # /stats requires it_admin role specifically.
        resp = await lead_client.get(f"{BASE}/stats")
        assert resp.status_code == 403

    async def test_admin_ok(self, admin_client: AsyncClient):
        with patch("app.api.v1.admin.AdminStatsService") as cls:
            cls.return_value.get_system_stats = AsyncMock(
                return_value=SystemStats(total_users=5, active_users=4, published_articles=3)
            )
            resp = await admin_client.get(f"{BASE}/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_users"] == 5
        assert body["resolution_rate"] == 0.0
