"""Tests for entity normalization — the core fix for the Sixth Sense conversation failure.

These tests validate that:
1. "sixthsenses", "sixth sense", "Sixth Sense" all normalize to "sixth_sense"
2. Other product variants are recognized
3. Intent detection catches login/lock/OTP patterns
4. Entity + intent combine to produce correct classification
"""

import pytest

from app.services.agents.entity_normalizer import (
    EntityMatch,
    detect_issue_intent,
    normalize_entity,
)


class TestSixthSenseEntityRecognition:
    """The specific failure scenario: Sixth Sense must be recognized."""

    def test_exact_match_sixth_sense(self):
        """'sixth sense' exact alias must match."""
        match = normalize_entity("sixth sense")
        assert match is not None
        assert match.canonical_name == "sixth_sense"
        assert match.category == "access/permissions"
        assert match.confidence >= 0.9

    def test_misspelled_sixthsenses(self):
        """'sixthsenses' — the exact typo from the failure scenario."""
        match = normalize_entity("I am having issue with sixthsenses")
        assert match is not None
        assert match.canonical_name == "sixth_sense"
        assert match.confidence >= 0.6

    def test_misspelled_sixthsense_no_space(self):
        """'sixthsense' without space."""
        match = normalize_entity("sixthsense")
        assert match is not None
        assert match.canonical_name == "sixth_sense"

    def test_sixth_sense_in_sentence(self):
        """Sixth Sense mentioned within a longer sentence."""
        match = normalize_entity("I am unable to login to sixth sense")
        assert match is not None
        assert match.canonical_name == "sixth_sense"

    def test_naukri_alias(self):
        """'naukri' alias should resolve to sixth_sense."""
        match = normalize_entity("having trouble with naukri")
        assert match is not None
        assert match.canonical_name == "sixth_sense"

    def test_sixth_sense_case_insensitive(self):
        """Case variations must all match."""
        for variant in ["Sixth Sense", "SIXTH SENSE", "sixth sense", "Sixth sense"]:
            match = normalize_entity(variant)
            assert match is not None, f"Failed for: {variant}"
            assert match.canonical_name == "sixth_sense"


class TestOtherEntityRecognition:
    """Validate entity recognition for other known systems."""

    def test_outlook_recognized(self):
        match = normalize_entity("My Outlook is crashing")
        assert match is not None
        assert match.canonical_name == "outlook"
        assert match.category == "email/outlook"

    def test_zoom_recognized(self):
        match = normalize_entity("Zoom audio not working")
        assert match is not None
        assert match.canonical_name == "zoom"

    def test_intune_recognized(self):
        match = normalize_entity("Intune shows non-compliant")
        assert match is not None
        assert match.canonical_name == "intune"

    def test_vpn_recognized(self):
        match = normalize_entity("VPN won't connect")
        assert match is not None
        assert match.canonical_name == "vpn"

    def test_keka_recognized(self):
        match = normalize_entity("Can't access Keka HR")
        assert match is not None
        assert match.canonical_name == "keka"

    def test_unknown_system_returns_none(self):
        """Unknown systems should return None, not a false match."""
        match = normalize_entity("something is broken")
        assert match is None

    def test_very_short_text_returns_none(self):
        match = normalize_entity("hi")
        assert match is None


class TestIntentDetection:
    """Tests for issue intent detection."""

    def test_login_intent_detected(self):
        result = detect_issue_intent("I am unable to login to sixth sense")
        assert result["intent"] == "login"
        assert result["is_login_issue"] is True

    def test_login_variants(self):
        """All login-related phrasings should be detected."""
        for msg in [
            "can't login", "cannot log in", "unable to sign in",
            "sign-in failed", "unable to access",
        ]:
            result = detect_issue_intent(msg)
            assert result["is_login_issue"] is True, f"Failed for: {msg}"

    def test_account_locked_detected(self):
        result = detect_issue_intent("my account is locked after wrong passwords")
        assert result["is_account_locked"] is True

    def test_otp_issue_detected(self):
        result = detect_issue_intent("I'm not receiving the OTP")
        assert result["has_otp_mention"] is True

    def test_unhandled_message_detected(self):
        result = detect_issue_intent("I see an Unhandled Message error")
        assert result["has_unhandled_message"] is True
        assert result["has_error_message"] is True

    def test_generic_message_no_intent(self):
        result = detect_issue_intent("hello")
        assert result["intent"] == "other"
        assert result["is_login_issue"] is False


class TestEntityAndIntentCombined:
    """The combined pipeline must route Sixth Sense + login correctly."""

    def test_sixth_sense_login_scenario(self):
        """THE EXACT FAILURE CASE: 'I am unable to login to sixth senses'."""
        # Step 1: Entity normalization
        match = normalize_entity("I am unable to login to sixth senses")
        assert match is not None
        assert match.canonical_name == "sixth_sense"

        # Step 2: Intent detection
        intent = detect_issue_intent("I am unable to login to sixth senses")
        assert intent["is_login_issue"] is True

        # Combined: we now know it's a Sixth Sense login issue
        assert match.category == "access/permissions"

    def test_sixth_sense_locked_account(self):
        """User reports blocked account on Naukri."""
        match = normalize_entity("my naukri account is locked")
        intent = detect_issue_intent("my naukri account is locked")
        assert match is not None
        assert match.canonical_name == "sixth_sense"
        assert intent["is_account_locked"] is True

    def test_first_vague_then_specific(self):
        """Simulate multi-turn: first vague, then specific."""
        # Turn 1: "having issue with sixthsenses"
        match1 = normalize_entity("I am having issue with sixthsenses")
        assert match1 is not None
        assert match1.canonical_name == "sixth_sense"

        # Turn 2: "unable to login to sixth senses"
        match2 = normalize_entity("I am unable to login to sixth senses")
        intent2 = detect_issue_intent("I am unable to login to sixth senses")
        assert match2 is not None
        assert intent2["is_login_issue"] is True
