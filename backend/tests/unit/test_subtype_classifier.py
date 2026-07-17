"""Tests for deterministic issue-subtype classification.

These lock in the core grounding fix: "my inbox is full" must map to the
mailbox/storage subtype and never to account-lock / password / Windows-update
subtypes.
"""

import pytest

from app.services.agents.subtype_classifier import classify_subtype, known_subtypes


class TestOutlookSubtypes:
    @pytest.mark.parametrize(
        "text",
        [
            "my inbox is full",
            "my mailbox is full",
            "mailbox storage is full, can't receive mail",
            "I am over my mailbox quota",
            "outlook says I am out of space",
        ],
    )
    def test_mailbox_full_variants(self, text):
        m = classify_subtype(text, "email/outlook")
        assert m is not None
        assert m.subtype == "mailbox-full", (text, m.subtype)
        assert m.confidence >= 0.55

    def test_mailbox_full_is_not_misclassified_as_access(self):
        m = classify_subtype("my inbox is full", "email/outlook")
        assert m.subtype not in {
            "account-locked",
            "password-expired",
            "sign-in-problem",
            "mfa-not-working",
        }

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("I can't send emails", "sending-failure"),
            ("emails are stuck in my outbox", "sending-failure"),
            ("I am not receiving any emails", "not-receiving-emails"),
            ("outlook is really slow and freezing", "outlook-slow"),
            ("outlook keeps crashing", "outlook-crash"),
            ("outlook is stuck working offline", "offline-mode"),
            ("I can't sign in to outlook", "sign-in-problem"),
        ],
    )
    def test_other_outlook_subtypes(self, text, expected):
        m = classify_subtype(text, "email/outlook")
        assert m is not None and m.subtype == expected, (text, m and m.subtype)

    def test_vague_message_returns_none(self):
        # "I have an issue with outlook" has no subtype signal → stay generic.
        assert classify_subtype("I have an issue with outlook", "email/outlook") is None

    def test_anti_keyword_suppresses_mailbox_full(self):
        m = classify_subtype("my inbox is not full but mail is missing", "email/outlook")
        # Should not be mailbox-full because of the "not full" anti-keyword.
        assert m is None or m.subtype != "mailbox-full"


class TestCrossCategory:
    def test_access_account_locked(self):
        m = classify_subtype("my account is locked out", "access/permissions")
        assert m is not None and m.subtype == "account-locked"

    def test_unknown_category_returns_none(self):
        assert classify_subtype("anything", "totally/unknown") is None

    def test_known_subtypes_listing(self):
        subs = known_subtypes("email/outlook")
        assert "mailbox-full" in subs and "sending-failure" in subs


class TestLaptopSubtypes:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("my keyboard is not working", "keyboard-not-working"),
            ("keys are typing wrong characters", "keyboard-not-working"),
            ("the touchpad is not responding", "trackpad-not-working"),
            ("my trackpad cursor keeps jumping", "trackpad-not-working"),
            ("laptop won't turn on at all", "laptop-wont-power-on"),
            ("my laptop is not powering on, no display", "laptop-wont-power-on"),
            ("battery is not charging when plugged in", "battery-not-charging"),
            ("plugged in but not charging", "battery-not-charging"),
            ("external monitor not detected", "external-monitor-not-detected"),
            ("my second screen won't display anything", "external-monitor-not-detected"),
        ],
    )
    def test_laptop_subtypes(self, text, expected):
        m = classify_subtype(text, "hardware/laptop")
        assert m is not None and m.subtype == expected, (text, m and m.subtype)

    def test_known_subtypes_laptop(self):
        subs = known_subtypes("hardware/laptop")
        assert set(subs) == {
            "keyboard-not-working",
            "trackpad-not-working",
            "laptop-wont-power-on",
            "battery-not-charging",
            "external-monitor-not-detected",
        }


class TestPerformanceSubtype:
    @pytest.mark.parametrize(
        "text",
        ["my laptop is really slow", "everything is lagging and freezing", "very sluggish today"],
    )
    def test_slow_performance(self, text):
        m = classify_subtype(text, "system/performance")
        assert m is not None and m.subtype == "slow-performance", (text, m and m.subtype)


class TestWindowsUpdateSubtype:
    @pytest.mark.parametrize(
        "text",
        ["windows update is stuck", "windows update failed to install", "update error on windows"],
    )
    def test_windows_update(self, text):
        m = classify_subtype(text, "software/windows-update")
        assert m is not None and m.subtype == "windows-update-failure", (text, m and m.subtype)


class TestHardwareOtherNoLongerAudioAlias:
    def test_hardware_other_keyboard_not_audio(self):
        # Regression: hardware/other used to alias _AUDIO_RULES, so "keyboard"
        # text scored against audio subtypes. It must now reach a hardware subtype.
        m = classify_subtype("my keyboard is not working", "hardware/other")
        assert m is not None
        assert m.subtype == "keyboard-not-working", m.subtype

    def test_hardware_other_still_matches_audio(self):
        # hardware/other must still cover audio (combined table), not lose it.
        m = classify_subtype("no sound from my speakers", "hardware/other")
        assert m is not None and m.subtype == "no-audio-output", m and m.subtype
