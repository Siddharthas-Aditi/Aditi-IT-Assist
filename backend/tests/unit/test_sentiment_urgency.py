"""Regression tests for pattern-based urgency detection (word-boundary fix).

Substring matching used to mis-classify benign words ("download"→"down"→
CRITICAL, "know"→"now"→MEDIUM) and picked the first dict hit rather than the
highest severity.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.agents.sentiment_analyzer import SentimentAnalyzerService, Urgency


def _analyzer() -> SentimentAnalyzerService:
    return SentimentAnalyzerService(MagicMock())


class TestUrgencyWordBoundaries:
    def test_download_does_not_trigger_critical(self):
        result = _analyzer()._analyze_patterns("How do I download the VPN client?")
        assert result.urgency != Urgency.CRITICAL

    def test_know_does_not_trigger_medium(self):
        result = _analyzer()._analyze_patterns("I don't know my password")
        assert result.urgency == Urgency.LOW

    def test_real_down_still_critical(self):
        result = _analyzer()._analyze_patterns("The email server is down")
        assert result.urgency == Urgency.CRITICAL

    def test_highest_severity_wins_over_word_order(self):
        # "soon" (MEDIUM) appears before "down" (CRITICAL) in the sentence;
        # severity, not position, must decide.
        result = _analyzer()._analyze_patterns("I need this soon, the whole system is down")
        assert result.urgency == Urgency.CRITICAL

    def test_urgent_is_high(self):
        result = _analyzer()._analyze_patterns("This is urgent, please help")
        assert result.urgency == Urgency.HIGH
