from __future__ import annotations

import pytest

from app.services import scheduler

pytestmark = pytest.mark.asyncio


async def test_advance_handoff_offers_once_runs_without_error(monkeypatch):
    called = {"n": 0}

    class _FakeSvc:
        def __init__(self, db):  # noqa: D401
            pass

        async def advance_once(self):
            called["n"] += 1
            return {"reoffered": 0, "broadened": 0, "fallback": 0, "held": 0}

    monkeypatch.setattr(scheduler, "HandoffService", _FakeSvc, raising=False)
    await scheduler._advance_handoff_offers_once()
    assert called["n"] == 1
