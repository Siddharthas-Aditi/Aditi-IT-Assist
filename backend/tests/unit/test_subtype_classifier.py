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
            "account-locked", "password-expired", "sign-in-problem", "mfa-not-working",
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
