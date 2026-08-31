from __future__ import annotations

from app.core.config import Settings


def test_fluid_chat_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("FEATURE_FLUID_CHAT", raising=False)
    s = Settings(_env_file=None)
    assert s.FEATURE_FLUID_CHAT is False


def test_fluid_chat_thresholds():
    s = Settings()
    assert s.FLUID_CHAT_MIN_SUBTYPE_CONFIDENCE == 0.6
    assert s.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE == 0.35


def test_resolution_fluid_step_cap_defaults_to_five():
    assert Settings().RESOLUTION_FLUID_STEP_CAP == 5
