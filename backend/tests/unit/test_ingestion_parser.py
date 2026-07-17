"""Unit tests for the ingestion parser (pure logic — no DB, no LLM)."""

import pytest

from app.services.ingestion.parser import (
    CandidatePayload,
    _classify_category,
    _extract_product,
    _extract_steps,
    _extract_symptoms,
    _extract_title,
    _is_heading,
    _score_confidence,
    _segment_into_topics,
    parse_document,
)


class TestHeadingDetection:
    def test_markdown_heading(self):
        assert _is_heading("## Outlook Not Receiving Email")

    def test_all_caps_heading(self):
        assert _is_heading("VPN CONNECTIVITY ISSUES")

    def test_numbered_heading(self):
        assert _is_heading("1. Camera Not Working")

    def test_labelled_heading(self):
        assert _is_heading("Issue: Zoom Audio Not Working")

    def test_plain_sentence_not_heading(self):
        assert not _is_heading("The user cannot connect to the VPN.")

    def test_empty_not_heading(self):
        assert not _is_heading("")


class TestSegmentation:
    def test_single_topic_no_headings(self):
        text = "User cannot connect to VPN.\nTry restarting the network adapter."
        segments = _segment_into_topics(text)
        assert len(segments) == 1

    def test_multiple_headings_split(self):
        text = (
            "## Outlook Issue\n"
            "User cannot receive email.\n\n"
            "## Zoom Issue\n"
            "User cannot join meetings.\n"
        )
        segments = _segment_into_topics(text)
        assert len(segments) == 2
        assert "Outlook" in segments[0]
        assert "Zoom" in segments[1]

    def test_tiny_segments_merged(self):
        text = "## Big Section\n" + "A" * 300 + "\n## Tiny\nok"
        segments = _segment_into_topics(text)
        # Tiny segment (< 60 chars) should be merged into previous
        assert len(segments) == 1


class TestTitleExtraction:
    def test_extracts_markdown_heading(self):
        lines = ["## Outlook Not Receiving Email", "User reports email is missing."]
        title = _extract_title(lines)
        assert title == "Outlook Not Receiving Email"

    def test_strips_issue_prefix(self):
        lines = ["Issue: Camera black screen", "Check drivers."]
        title = _extract_title(lines)
        assert "Issue:" not in title

    def test_fallback_to_first_line(self):
        lines = ["Camera troubleshooting guide", "If the camera shows black screen..."]
        title = _extract_title(lines)
        assert title == "Camera troubleshooting guide"


class TestSymptomExtraction:
    def test_bullet_symptoms(self):
        lines = [
            "Symptoms:",
            "- User sees black screen",
            "- Camera not detected in device manager",
        ]
        symptoms = _extract_symptoms(lines)
        assert len(symptoms) == 2
        assert "User sees black screen" in symptoms

    def test_inline_symptom_lead(self):
        lines = ["- User cannot send email after recent update"]
        symptoms = _extract_symptoms(lines)
        assert len(symptoms) == 1

    def test_caps_at_10(self):
        lines = ["Symptoms:"] + [f"- Symptom {i}" for i in range(15)]
        symptoms = _extract_symptoms(lines)
        assert len(symptoms) == 10


class TestStepExtraction:
    def test_resolution_steps(self):
        lines = [
            "Resolution",
            "1. Open Outlook settings",
            "2. Click Account Settings",
            "3. Remove and re-add account",
        ]
        ts, rs = _extract_steps(lines)
        assert len(rs) == 3
        assert rs[0]["instruction"] == "Open Outlook settings"

    def test_troubleshooting_steps(self):
        lines = [
            "Troubleshooting",
            "1. Check internet connection",
            "2. Ping 8.8.8.8",
        ]
        ts, rs = _extract_steps(lines)
        assert len(ts) == 2

    def test_both_sections(self):
        lines = [
            "Troubleshooting",
            "1. Restart router",
            "Resolution",
            "1. Factory reset modem",
            "2. Reconfigure WiFi",
        ]
        ts, rs = _extract_steps(lines)
        assert len(ts) == 1
        assert len(rs) == 2


class TestCategoryClassification:
    @pytest.mark.parametrize(
        "text,expected_cat",
        [
            ("User cannot open Outlook email", "email/outlook"),
            ("Zoom meeting audio issues", "video-conferencing/zoom"),
            ("Intune device compliance failure", "device-management/intune"),
            ("Camera shows black screen", "hardware/camera"),
            ("VPN connection refused", "network/connectivity"),
            ("Access denied to SharePoint resource", "access/permissions"),
        ],
    )
    def test_known_categories(self, text: str, expected_cat: str):
        cat, _ = _classify_category(text)
        assert cat == expected_cat

    def test_unknown_returns_none(self):
        cat, _ = _classify_category("Random unrelated content about cooking recipes.")
        assert cat is None


class TestProductExtraction:
    def test_outlook_detected(self):
        product = _extract_product("The user cannot open Outlook on Windows.")
        assert product == "Outlook"

    def test_zoom_detected(self):
        product = _extract_product("Zoom fails to connect during meetings.")
        assert product == "Zoom"

    def test_unknown_product_returns_none(self):
        product = _extract_product("Generic IT issue with no product name.")
        assert product is None


class TestConfidenceScoring:
    def test_full_confidence_below_1(self):
        score = _score_confidence(
            title="Outlook email issue",
            symptoms=["email missing", "sync failed"],
            troubleshooting=[{"step_number": 1, "instruction": "Check connection", "details": ""}],
            resolution=[{"step_number": 1, "instruction": "Reinstall", "details": ""}],
        )
        assert 0.0 < score <= 0.9

    def test_empty_gives_zero(self):
        score = _score_confidence(title=None, symptoms=[], troubleshooting=[], resolution=[])
        assert score == 0.0


class TestParseDocument:
    def test_empty_text_returns_empty(self):
        candidates = parse_document("")
        assert candidates == []

    def test_whitespace_only_returns_empty(self):
        candidates = parse_document("   \n  \n  ")
        assert candidates == []

    def test_single_topic_returns_one_candidate(self):
        text = (
            "## Outlook Not Receiving Email\n"
            "Symptoms:\n"
            "- User reports missing emails\n"
            "Resolution\n"
            "1. Check spam folder\n"
            "2. Re-sync account\n"
        )
        candidates = parse_document(text)
        assert len(candidates) == 1
        c = candidates[0]
        assert isinstance(c, CandidatePayload)
        assert c.title is not None
        assert "Outlook" in c.title

    def test_multi_topic_returns_multiple(self):
        text = (
            "## Issue 1: VPN Failure\n"
            "Symptoms:\n- Cannot connect to VPN\n"
            "Resolution\n1. Restart VPN client\n\n"
            "## Issue 2: Camera Problem\n"
            "Symptoms:\n- Black screen on camera\n"
            "Resolution\n1. Update driver\n"
        )
        candidates = parse_document(text)
        assert len(candidates) >= 2

    def test_indices_are_sequential(self):
        text = "\n".join(f"## Issue {i}\nSome content about issue {i}\n" for i in range(5))
        candidates = parse_document(text)
        for i, c in enumerate(candidates):
            assert c.candidate_index == i
