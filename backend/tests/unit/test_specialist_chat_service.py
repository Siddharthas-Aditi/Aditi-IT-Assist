"""Unit tests for SpecialistChatService idle math + state transitions.

DB-backed tests are deferred to the integration suite. These tests pin
the *pure* logic — the idle evaluator + the typed-end-reason mapping —
which is what makes the auto-end-on-timeout invariant safe to deploy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.services.specialist_chat_service import (
    SpecialistChatService,
    _end_message_for_reason,
    _status_for_reason,
)


@dataclass
class _FakeSession:
    """Lightweight stand-in for SpecialistChatSession for pure-fn tests."""

    last_activity_at: datetime
    status: str = "active"
    idle_warning_seconds: int = 120
    idle_end_seconds: int = 180


def _now() -> datetime:
    return datetime.now(UTC)


class TestIdleDefaults:
    """The default idle policy is 7-minute warning + 2-minute grace. These
    pin the contract so a regression to the old 2/3-min values is caught."""

    def test_start_request_defaults_are_7_and_9_minutes(self) -> None:
        import uuid

        from app.schemas.specialist_chat import StartLiveChatRequest

        req = StartLiveChatRequest(ticket_id=uuid.uuid4())
        assert req.idle_warning_seconds == 420  # 7 min
        assert req.idle_end_seconds == 540  # 7 + 2 min grace

    def test_warning_at_7min_not_before(self) -> None:
        svc = SpecialistChatService(db=MagicMock())
        session = _FakeSession(
            last_activity_at=_now() - timedelta(seconds=400),  # < 420
            idle_warning_seconds=420,
            idle_end_seconds=540,
        )
        assert svc.evaluate_idle(session, now=_now()).is_idle_warning is False
        # Past 7 min: warning fires, end does not (still in the 2-min grace).
        session.last_activity_at = _now() - timedelta(seconds=480)
        ev = svc.evaluate_idle(session, now=_now())
        assert ev.is_idle_warning is True
        assert ev.is_idle_end is False

    def test_auto_end_after_grace(self) -> None:
        svc = SpecialistChatService(db=MagicMock())
        session = _FakeSession(
            last_activity_at=_now() - timedelta(seconds=541),  # > 540
            idle_warning_seconds=420,
            idle_end_seconds=540,
        )
        assert svc.evaluate_idle(session, now=_now()).is_idle_end is True


class TestIdleEvaluation:
    """The deterministic idle math is what the polling endpoint AND the
    background sweeper share. One source of truth — pin it."""

    def test_fresh_session_is_active(self) -> None:
        svc = SpecialistChatService(db=MagicMock())
        session = _FakeSession(last_activity_at=_now())
        ev = svc.evaluate_idle(session, now=_now())
        assert not ev.is_idle_warning
        assert not ev.is_idle_end
        assert ev.seconds_since_activity < 1

    def test_past_warning_but_not_end(self) -> None:
        svc = SpecialistChatService(db=MagicMock())
        # 150s back: past warning (120s), under end (180s).
        session = _FakeSession(last_activity_at=_now() - timedelta(seconds=150))
        ev = svc.evaluate_idle(session, now=_now())
        assert ev.is_idle_warning is True
        assert ev.is_idle_end is False

    def test_past_end_threshold(self) -> None:
        svc = SpecialistChatService(db=MagicMock())
        session = _FakeSession(last_activity_at=_now() - timedelta(seconds=200))
        ev = svc.evaluate_idle(session, now=_now())
        assert ev.is_idle_warning is True
        assert ev.is_idle_end is True

    def test_thresholds_are_per_session(self) -> None:
        """The session can override the defaults — high-priority incidents
        keep the chat alive longer."""
        svc = SpecialistChatService(db=MagicMock())
        session = _FakeSession(
            last_activity_at=_now() - timedelta(seconds=200),
            idle_warning_seconds=600,
            idle_end_seconds=1200,
        )
        ev = svc.evaluate_idle(session, now=_now())
        assert ev.is_idle_warning is False
        assert ev.is_idle_end is False


class TestEndReasonMapping:
    """Every typed end reason maps to exactly one status — no free-text drift."""

    @pytest.mark.parametrize(
        "reason, expected_status",
        [
            ("resolved", "ended_by_specialist"),
            ("specialist_ended", "ended_by_specialist"),
            ("user_left", "ended_by_user"),
            ("idle_timeout", "ended_by_timeout"),
            ("session_error", "ended_by_system"),
        ],
    )
    def test_reason_maps_to_typed_status(self, reason: str, expected_status: str) -> None:
        assert _status_for_reason(reason) == expected_status

    def test_unknown_reason_falls_back_to_system(self) -> None:
        assert _status_for_reason("anything-else") == "ended_by_system"

    @pytest.mark.parametrize(
        "reason",
        ["resolved", "specialist_ended", "user_left", "idle_timeout", "session_error"],
    )
    def test_every_reason_has_user_message(self, reason: str) -> None:
        msg = _end_message_for_reason(reason)
        assert msg and isinstance(msg, str)
        assert len(msg) > 10  # not just a placeholder


class TestParticipationGuard:
    """The participation check is part of the security contract — only the
    user, specialist (or an admin) can post / end."""

    def test_outside_user_blocked(self) -> None:
        import uuid

        from app.services.specialist_chat_service import _is_participant

        session = MagicMock()
        session.user_id = uuid.uuid4()
        session.specialist_id = uuid.uuid4()

        outsider = MagicMock()
        outsider.id = uuid.uuid4()

        assert _is_participant(session, outsider) is False

    def test_user_allowed(self) -> None:
        import uuid

        from app.services.specialist_chat_service import _is_participant

        session = MagicMock()
        user_id = uuid.uuid4()
        session.user_id = user_id
        session.specialist_id = uuid.uuid4()

        u = MagicMock()
        u.id = user_id
        assert _is_participant(session, u) is True
