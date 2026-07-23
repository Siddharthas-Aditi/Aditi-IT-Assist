from __future__ import annotations

from app.core.config import Settings


def test_handoff_defaults_present():
    s = Settings()
    assert s.LIVE_OFFER_TTL_SECONDS == 30
    assert s.LIVE_OFFER_MAX_ROUNDS == 2
    assert s.LIVE_HANDOFF_FALLBACK_SECONDS == 120
    assert s.SPECIALIST_PRESENCE_TTL_SECONDS == 60
    assert s.HANDOFF_SWEEPER_ENABLED is True
    assert s.HANDOFF_SWEEPER_INTERVAL_SECONDS == 10
