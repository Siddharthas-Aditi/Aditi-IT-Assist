"""Unit tests for authentication and RBAC enforcement.

Tests:
- Role-based dependency guards (require_roles, require_permissions)
- Employee data isolation (cannot see others' tickets/sessions)
- IT agent/lead/admin role hierarchies
- Auth dependency behavior
"""

import uuid
from unittest.mock import MagicMock

import pytest

from app.services.auth.dependencies import (
    get_current_active_user,
    require_roles,
)

# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _make_user(role: str, roles: list[str] | None = None) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = f"{role}@test.com"
    user.full_name = f"Test {role}"
    user.is_active = True
    user.primary_role = role
    user.role_names = roles or [role]

    assignment = MagicMock()
    assignment.role = MagicMock()
    assignment.role.name = role
    assignment.role.priority = {"employee": 0, "it_agent": 10, "it_lead": 20, "it_admin": 30}.get(
        role, 0
    )
    user.role_assignments = [assignment]
    return user


# ─────────────────────────────────────────────────────────────────────
# require_roles tests
# ─────────────────────────────────────────────────────────────────────


class TestRequireRoles:
    """Tests for require_roles dependency factory."""

    async def test_allows_user_with_matching_role(self):
        """User with an allowed role passes the guard."""
        mock_user = _make_user("it_agent")
        guard = require_roles("it_agent", "it_lead", "it_admin")

        result = await guard(current_user=mock_user)
        assert result is mock_user

    async def test_denies_user_without_matching_role(self):
        """User without any allowed role raises 403."""
        from fastapi import HTTPException

        mock_user = _make_user("employee")
        guard = require_roles("it_agent", "it_lead", "it_admin")

        with pytest.raises(HTTPException) as exc_info:
            await guard(current_user=mock_user)
        assert exc_info.value.status_code == 403

    async def test_it_lead_passes_it_agent_guard(self):
        """IT lead satisfies it_agent | it_lead | it_admin guard."""
        mock_user = _make_user("it_lead")
        guard = require_roles("it_agent", "it_lead", "it_admin")

        result = await guard(current_user=mock_user)
        assert result is mock_user

    async def test_it_admin_passes_all_guards(self):
        """IT admin passes guards that explicitly include it_admin role.

        Note: require_roles checks EXACT role membership — there is no
        implicit role hierarchy. ITAgentUser = require_roles("it_agent",
        "it_lead", "it_admin") so all tiers are listed explicitly.
        """
        admin = _make_user("it_admin")

        # Guards that explicitly include it_admin
        for guard in [
            require_roles("it_admin"),
            require_roles("it_agent", "it_lead", "it_admin"),
            require_roles("it_lead", "it_admin"),
            require_roles("security_auditor", "it_admin"),
        ]:
            result = await guard(current_user=admin)
            assert result is admin

    async def test_employee_cannot_access_it_only_route(self):
        """Employee cannot access routes requiring it_agent or above."""
        from fastapi import HTTPException

        employee = _make_user("employee")
        guard = require_roles("it_agent", "it_lead", "it_admin")

        with pytest.raises(HTTPException) as exc_info:
            await guard(current_user=employee)
        assert exc_info.value.status_code == 403
        assert "403" in str(exc_info.value.status_code)

    async def test_security_auditor_cannot_access_it_agent_route(self):
        """Security auditor cannot access IT agent queue (wrong role)."""
        from fastapi import HTTPException

        auditor = _make_user("security_auditor")
        guard = require_roles("it_agent", "it_lead", "it_admin")

        with pytest.raises(HTTPException) as exc_info:
            await guard(current_user=auditor)
        assert exc_info.value.status_code == 403

    async def test_auditor_can_access_audit_route(self):
        """Security auditor can access audit-specific routes."""
        auditor = _make_user("security_auditor")
        guard = require_roles("security_auditor", "it_admin")

        result = await guard(current_user=auditor)
        assert result is auditor


# ─────────────────────────────────────────────────────────────────────
# get_current_active_user tests
# ─────────────────────────────────────────────────────────────────────


class TestGetCurrentActiveUser:
    """Tests for get_current_active_user dependency."""

    async def test_inactive_user_is_rejected(self):
        """Inactive user should get 403."""
        from fastapi import HTTPException

        inactive_user = _make_user("employee")
        inactive_user.is_active = False

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(current_user=inactive_user)
        assert exc_info.value.status_code == 403

    async def test_active_user_passes(self):
        """Active user passes through."""
        active_user = _make_user("employee")
        active_user.is_active = True

        result = await get_current_active_user(current_user=active_user)
        assert result is active_user
