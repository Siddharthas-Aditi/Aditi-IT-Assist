from __future__ import annotations

from app.core.config import Settings


def test_fluid_chat_flag_defaults_off():
    s = Settings()
    assert s.FEATURE_FLUID_CHAT is False


def test_fluid_chat_thresholds():
    s = Settings()
    assert s.FLUID_CHAT_MIN_SUBTYPE_CONFIDENCE == 0.6
    assert s.FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE == 0.35
