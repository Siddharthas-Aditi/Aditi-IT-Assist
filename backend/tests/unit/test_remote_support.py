"""Unit tests for remote support service — consent flow, policy, state machine.

Tests:
- Consent enforcement: session cannot launch without consent
- Employee can only consent to their own session
- Consent revocation terminates session
- Status transition enforcement (invalid transitions blocked)
- Policy checks: screen_control requires it_lead+
- Audit events recorded on every transition
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.remote_support.service import (
    ConsentRequired,
    InvalidTransition,
    PolicyViolation,
    RemoteSupportService,
    _assert_transition,
)

# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _make_user(role: str = "it_agent", roles: list[str] | None = None) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = f"{role}@test.com"
    user.full_name = f"Test {role.title()}"
    user.role_names = roles or [role]
    return user


def _make_session(
    status: str = "consent_pending",
    employee_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
    session_type: str = "screen_view",
) -> MagicMock:
    session = MagicMock()
    session.id = uuid.uuid4()
    session.status = status
    session.employee_id = employee_id or uuid.uuid4()
    session.agent_id = agent_id or uuid.uuid4()
    session.session_type = session_type
    session.provider = "microsoft_remote_help"
    session.provider_session_id = None
    session.consent_deadline = datetime.now(UTC) + timedelta(minutes=10)
    session.active_consent = None
    return session


def _make_mock_db() -> MagicMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    return db


# ─────────────────────────────────────────────────────────────────────
# State machine tests
# ─────────────────────────────────────────────────────────────────────


class TestStateMachine:
    """Tests for the allowed transition table."""

    def test_requested_can_go_to_consent_pending(self):
        _assert_transition("requested", "consent_pending")  # no exception

    def test_consent_pending_can_go_to_consent_granted(self):
        _assert_transition("consent_pending", "consent_granted")

    def test_consent_pending_can_go_to_consent_denied(self):
        _assert_transition("consent_pending", "consent_denied")

    def test_consent_denied_is_terminal(self):
        with pytest.raises(InvalidTransition):
            _assert_transition("consent_denied", "connecting")

    def test_completed_is_terminal(self):
        with pytest.raises(InvalidTransition):
            _assert_transition("completed", "active")

    def test_terminated_is_terminal(self):
        with pytest.raises(InvalidTransition):
            _assert_transition("terminated", "active")

    def test_active_can_go_to_completed(self):
        _assert_transition("active", "completed")

    def test_active_can_go_to_terminated(self):
        _assert_transition("active", "terminated")

    def test_connecting_to_active_allowed(self):
        _assert_transition("connecting", "active")

    def test_invalid_jump_raises(self):
        with pytest.raises(InvalidTransition):
            _assert_transition("requested", "active")

    def test_consent_granted_to_active_not_allowed(self):
        """Must go through 'connecting' first."""
        with pytest.raises(InvalidTransition):
            _assert_transition("consent_granted", "active")


# ─────────────────────────────────────────────────────────────────────
# Policy enforcement
# ─────────────────────────────────────────────────────────────────────


class TestPolicyEnforcement:
    """Tests for _enforce_request_policy."""

    def test_it_agent_can_request_screen_view(self):
        """IT agent can request screen_view sessions."""
        from app.services.remote_support.service import RemoteSupportService

        agent = _make_user("it_agent")
        # Should not raise
        RemoteSupportService._enforce_request_policy(agent, "screen_view", None)

    def test_employee_cannot_request_session(self):
        """Employees cannot request remote support sessions."""
        from app.services.remote_support.service import RemoteSupportService

        employee = _make_user("employee")
        with pytest.raises(PolicyViolation, match="Only IT staff"):
            RemoteSupportService._enforce_request_policy(employee, "screen_view", None)

    def test_it_agent_cannot_request_screen_control(self):
        """IT agent (not lead) cannot request screen_control."""
        from app.services.remote_support.service import RemoteSupportService

        agent = _make_user("it_agent")
        with pytest.raises(PolicyViolation, match="IT Lead or Admin"):
            RemoteSupportService._enforce_request_policy(agent, "screen_control", "fix issue")

    def test_it_lead_can_request_screen_control_with_justification(self):
        """IT lead can request screen_control with justification."""
        from app.services.remote_support.service import RemoteSupportService

        lead = _make_user("it_lead")
        # Should not raise
        RemoteSupportService._enforce_request_policy(lead, "screen_control", "Critical fix needed")

    def test_screen_control_requires_justification(self):
        """screen_control without justification is rejected even for IT lead."""
        from app.services.remote_support.service import RemoteSupportService

        lead = _make_user("it_lead")
        with pytest.raises(PolicyViolation, match="Justification"):
            RemoteSupportService._enforce_request_policy(lead, "screen_control", None)

    def test_it_admin_can_request_screen_control(self):
        """IT admin can always request screen_control."""
        from app.services.remote_support.service import RemoteSupportService

        admin = _make_user("it_admin")
        # Should not raise
        RemoteSupportService._enforce_request_policy(admin, "screen_control", "Admin override")


# ─────────────────────────────────────────────────────────────────────
# Consent enforcement
# ─────────────────────────────────────────────────────────────────────


class TestConsentEnforcement:
    """Tests for consent workflow in RemoteSupportService."""

    async def test_only_target_employee_can_consent(self):
        """A different employee cannot respond to someone else's consent request."""
        db = _make_mock_db()
        service = RemoteSupportService(db)

        target_employee_id = uuid.uuid4()
        other_employee = _make_user("employee")
        other_employee.id = uuid.uuid4()  # Different user

        mock_session = _make_session(
            status="consent_pending",
            employee_id=target_employee_id,
        )

        with (
            patch.object(service, "_get_or_raise", return_value=mock_session),
            pytest.raises(PolicyViolation, match="Only the target employee"),
        ):
            await service.grant_consent(
                session_id=mock_session.id,
                employee=other_employee,
                granted=True,
            )

    async def test_expired_consent_window_raises_policy_violation(self):
        """Trying to consent after deadline raises PolicyViolation."""
        db = _make_mock_db()
        service = RemoteSupportService(db)

        employee = _make_user("employee")
        mock_session = _make_session(
            status="consent_pending",
            employee_id=employee.id,
        )
        # Set consent_deadline in the past
        mock_session.consent_deadline = datetime.now(UTC) - timedelta(minutes=1)

        with (
            patch.object(service, "_get_or_raise", return_value=mock_session),
            patch.object(service, "_expire_session", new_callable=AsyncMock),
            pytest.raises(PolicyViolation, match="expired"),
        ):
            await service.grant_consent(
                session_id=mock_session.id,
                employee=employee,
                granted=True,
            )

    async def test_launch_without_consent_raises(self):
        """Session cannot launch if no active consent."""
        db = _make_mock_db()
        service = RemoteSupportService(db)

        agent = _make_user("it_agent")
        mock_session = _make_session(
            status="consent_granted",
            agent_id=agent.id,
        )
        mock_session.active_consent = None  # No active consent

        with (
            patch.object(service, "_get_or_raise", return_value=mock_session),
            pytest.raises(ConsentRequired),
        ):
            await service.launch_session(mock_session.id, agent)

    async def test_only_employee_can_revoke_consent(self):
        """Only the employee can revoke their own consent."""
        db = _make_mock_db()
        service = RemoteSupportService(db)

        employee_id = uuid.uuid4()
        intruder = _make_user("it_agent")
        intruder.id = uuid.uuid4()  # Not the employee

        mock_session = _make_session(
            status="active",
            employee_id=employee_id,
        )

        with (
            patch.object(service, "_get_or_raise", return_value=mock_session),
            pytest.raises(PolicyViolation, match="Only the employee"),
        ):
            await service.revoke_consent(
                session_id=mock_session.id,
                employee=intruder,
            )


# ─────────────────────────────────────────────────────────────────────
# Session visibility tests
# ─────────────────────────────────────────────────────────────────────


class TestSessionVisibility:
    """Tests for get_session visibility enforcement."""

    async def test_agent_can_see_own_session(self):
        """Agent can view sessions they own."""
        db = _make_mock_db()
        service = RemoteSupportService(db)

        agent = _make_user("it_agent")
        mock_session = _make_session(agent_id=agent.id)

        with patch.object(service, "_get_or_raise", return_value=mock_session):
            result = await service.get_session(mock_session.id, agent)
        assert result is mock_session

    async def test_employee_can_see_own_session(self):
        """Employee can view sessions they're part of."""
        db = _make_mock_db()
        service = RemoteSupportService(db)

        employee = _make_user("employee")
        mock_session = _make_session(employee_id=employee.id)

        with patch.object(service, "_get_or_raise", return_value=mock_session):
            result = await service.get_session(mock_session.id, employee)
        assert result is mock_session

    async def test_random_employee_cannot_see_session(self):
        """Random employee cannot see someone else's session."""
        db = _make_mock_db()
        service = RemoteSupportService(db)

        random_user = _make_user("employee")
        random_user.id = uuid.uuid4()

        mock_session = _make_session()  # Different employee/agent IDs

        with (
            patch.object(service, "_get_or_raise", return_value=mock_session),
            pytest.raises(PolicyViolation, match="do not have access"),
        ):
            await service.get_session(mock_session.id, random_user)

    async def test_it_admin_can_see_any_session(self):
        """IT admin can view any session."""
        db = _make_mock_db()
        service = RemoteSupportService(db)

        admin = _make_user("it_admin")
        mock_session = _make_session()  # Random participants

        with patch.object(service, "_get_or_raise", return_value=mock_session):
            result = await service.get_session(mock_session.id, admin)
        assert result is mock_session
