"""Unit tests for AdminUserService business-rule guardrails.

These exercise the service-layer rules directly (no DB): self-suspension is
refused, and a user's last role cannot be revoked.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.admin.user_service import AdminUserError, AdminUserService


def _svc() -> AdminUserService:
    svc = AdminUserService(AsyncMock())
    svc.audit = AsyncMock()
    return svc


class TestSelfSuspendGuard:
    async def test_admin_cannot_suspend_self(self):
        svc = _svc()
        uid = uuid.uuid4()
        actor = SimpleNamespace(id=uid)
        user = SimpleNamespace(id=uid, email="me@aditi.com")
        svc._require = AsyncMock(return_value=user)

        with pytest.raises(AdminUserError) as exc:
            await svc.update_user(uid, is_active=False, actor=actor)
        assert exc.value.status_code == 409

    async def test_admin_can_suspend_other(self):
        svc = _svc()
        target_id = uuid.uuid4()
        actor = SimpleNamespace(id=uuid.uuid4())
        user = SimpleNamespace(
            id=target_id,
            email="other@aditi.com",
            full_name="Other",
            department=None,
            job_title=None,
            phone=None,
            is_active=True,
        )
        svc._require = AsyncMock(return_value=user)
        svc._reload_detail = AsyncMock(return_value="DETAIL")

        result = await svc.update_user(target_id, is_active=False, actor=actor)
        assert result == "DETAIL"
        assert user.is_active is False
        svc.audit.log.assert_awaited()  # mutation was audited


class TestLastRoleGuard:
    async def test_cannot_revoke_last_role(self):
        svc = _svc()
        uid = uuid.uuid4()
        role = SimpleNamespace(id=uuid.uuid4(), name="it_admin")
        only_assignment = SimpleNamespace(role_id=role.id)
        user = SimpleNamespace(id=uid, email="solo@aditi.com", role_assignments=[only_assignment])

        svc._require = AsyncMock(return_value=user)
        svc._role_by_name = AsyncMock(return_value=role)

        with pytest.raises(AdminUserError) as exc:
            await svc.revoke_role(uid, "it_admin", actor=SimpleNamespace(id=uuid.uuid4()))
        assert exc.value.status_code == 409
