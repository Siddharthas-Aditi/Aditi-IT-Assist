from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.specialist_presence_service import is_available

NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=UTC)


def test_available_with_fresh_heartbeat():
    assert is_available("available", NOW - timedelta(seconds=30), NOW, 60) is True


def test_available_but_stale_heartbeat_is_unavailable():
    assert is_available("available", NOW - timedelta(seconds=120), NOW, 60) is False


def test_away_is_never_available():
    assert is_available("away", NOW, NOW, 60) is False


def test_missing_heartbeat_is_unavailable():
    assert is_available("available", None, NOW, 60) is False
