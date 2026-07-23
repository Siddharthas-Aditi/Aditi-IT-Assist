from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.services.specialist_handoff_service import HandoffDecision, decide_next

NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=UTC)
X = uuid.uuid4()


def _call(**kw):
    base = dict(
        offered_at=NOW,
        request_started_at=NOW,
        round_index=0,
        candidates_remaining=[X],
        any_available=True,
        now=NOW,
        offer_ttl_seconds=30,
        max_rounds=2,
        fallback_seconds=120,
    )
    base.update(kw)
    return decide_next(**base)


def test_fresh_offer_holds():
    assert _call(now=NOW + timedelta(seconds=10)).action == "hold"


def test_expired_offer_reoffers_next_candidate():
    d = _call(now=NOW + timedelta(seconds=31))
    assert d == HandoffDecision("reoffer", X)


def test_round_cap_broadens_when_available():
    d = _call(now=NOW + timedelta(seconds=31), round_index=1, max_rounds=2)
    assert d.action == "broaden"


def test_no_candidates_and_none_available_falls_back():
    d = _call(now=NOW + timedelta(seconds=31), candidates_remaining=[], any_available=False)
    assert d.action == "fallback"


def test_overall_deadline_forces_fallback():
    d = _call(now=NOW + timedelta(seconds=121))
    assert d.action == "fallback"
