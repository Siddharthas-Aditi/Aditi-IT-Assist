"""Detect user sentiment: urgency, frustration, and confusion."""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)


class Urgency(str, Enum):
    """User's time sensitivity."""
    LOW = "low"            # "When you get a chance..."
    MEDIUM = "medium"      # "I need this soon"
    HIGH = "high"          # "ASAP", "Critical", "Important"
    CRITICAL = "critical"  # "System DOWN", "Can't work", "URGENT!!!"


class Frustration(str, Enum):
    """User's emotional state."""
    CALM = "calm"          # Matter-of-fact tone
    MILD = "mild"          # Some frustration ("This is annoying")
    HIGH = "high"          # Very frustrated ("I can't BELIEVE this!", ALL CAPS)


class Confusion(str, Enum):
    """User's clarity on problem."""
    CLEAR = "clear"        # Knows exactly what's wrong
    CONFUSED = "confused"  # "Not sure what's happening", "I don't know", "?"


@dataclass
class SentimentAnalysis:
    """Result of sentiment analysis on user message."""
    urgency: Urgency
    frustration: Frustration
    confusion: Confusion
    confidence: float  # 0.0-1.0: how confident are we in this analysis?
    raw_analysis: dict  # For debugging


class SentimentAnalyzerService:
    """Detect tone from user messages using patterns + optional LLM."""

    def __init__(self, llm_service: LLMService):
        self.llm = llm_service

    async def analyze(self, message: str) -> SentimentAnalysis:
        """
        Detect user sentiment: urgency, frustration, confusion.

        Uses pattern-based fast detection first. If confidence < 0.8, falls back
        to LLM-based analysis for nuanced cases.

        Args:
            message: User's chat message

        Returns:
            SentimentAnalysis with tone indicators
        """
        # First: pattern-based detection (fast, deterministic)
        pattern_result = self._analyze_patterns(message)

        # If pattern confidence high (>0.75), use it
        if pattern_result.confidence >= 0.75:
            return pattern_result

        # Otherwise: LLM-based detection (more nuanced)
        try:
            llm_result = await self._analyze_with_llm(message)
            logger.info(
                "sentiment_analysis_via_llm",
                urgency=llm_result.urgency.value,
                frustration=llm_result.frustration.value,
                confidence=llm_result.confidence,
            )
            return llm_result
        except Exception as e:
            logger.warning(f"LLM sentiment analysis failed, using pattern fallback: {e}")
            return pattern_result

    def _analyze_patterns(self, message: str) -> SentimentAnalysis:
        """Fast pattern-based sentiment detection (no LLM calls)."""
        msg_lower = message.lower()

        # ──── URGENCY DETECTION ────
        urgency_keywords = {
            "critical": Urgency.CRITICAL,
            "down": Urgency.CRITICAL,
            "can't work": Urgency.CRITICAL,
            "cannot work": Urgency.CRITICAL,
            "broken": Urgency.HIGH,
            "urgent": Urgency.HIGH,
            "asap": Urgency.HIGH,
            "immediately": Urgency.HIGH,
            "right now": Urgency.HIGH,
            "now": Urgency.MEDIUM,
            "soon": Urgency.MEDIUM,
            "minutes": Urgency.MEDIUM,
        }

        detected_urgency = Urgency.LOW
        for keyword, level in urgency_keywords.items():
            if keyword in msg_lower:
                detected_urgency = level
                break

        # ──── FRUSTRATION DETECTION ────
        frustration_patterns = {
            # Caps lock + exclamation = high frustration
            r"[A-Z]{5,}!": 0.9,  # "EMAIL!!!" → high
            r"[A-Z]{5,}\?": 0.85,  # "WHAT??" → high
            # Multiple exclamation marks = high frustration
            r"!{2,}": 0.8,
            r"\?\?": 0.75,
            # Swearing / negative expressions = high
            r"\b(damn|frustrated|angry|furious|hate|terrible|horrible)\b": 0.8,
            # Can't/won't/doesn't = some frustration
            r"\b(can't|cannot|won't|doesn't|doesn't|broken)\b": 0.5,
            # Please / politeness = calm
            r"\bplease\b": -0.2,
        }

        frustration_score = 0.0
        for pattern, score in frustration_patterns.items():
            if re.search(pattern, message, re.IGNORECASE):
                frustration_score = max(frustration_score, score)

        frustration = (
            Frustration.HIGH if frustration_score > 0.7
            else Frustration.MILD if frustration_score > 0.3
            else Frustration.CALM
        )

        # ──── CONFUSION DETECTION ────
        confusion_keywords = ["?", "not sure", "confused", "how do i", "what's", "what do i", "don't know"]
        has_confusion = any(kw in msg_lower for kw in confusion_keywords)
        confusion = Confusion.CONFUSED if has_confusion else Confusion.CLEAR

        # ──── CONFIDENCE SCORE ────
        # High confidence if we detected strong signals
        has_strong_signal = (
            detected_urgency != Urgency.LOW or
            frustration != Frustration.CALM or
            has_confusion
        )
        confidence = 0.8 if has_strong_signal else 0.5

        return SentimentAnalysis(
            urgency=detected_urgency,
            frustration=frustration,
            confusion=confusion,
            confidence=confidence,
            raw_analysis={
                "urgency_keyword": next(
                    (k for k in urgency_keywords if k in msg_lower), None
                ),
                "frustration_score": frustration_score,
                "has_confusion_keywords": has_confusion,
                "method": "pattern",
            },
        )

    async def _analyze_with_llm(self, message: str) -> SentimentAnalysis:
        """LLM-based sentiment detection for nuanced cases."""
        analysis_prompt = f"""
Analyze this IT support message for tone.

Message: "{message}"

Detect:
1. Urgency: low (casual, "when you get a chance") / medium (soon, "I need this soon") / high (ASAP) / critical (system down)
2. Frustration: calm (neutral, professional) / mild (some frustration) / high (very frustrated, angry)
3. Confusion: clear (knows the issue) / confused (unsure what's happening)

Return JSON with keys: urgency, frustration, confusion, reasoning (brief explanation).
All values must be lowercase.
        """

        try:
            result = await self.llm.complete_json(
                prompt=analysis_prompt,
                system_prompt="You are analyzing customer support message tone. Be precise and consistent.",
            )

            return SentimentAnalysis(
                urgency=Urgency(result["urgency"]),
                frustration=Frustration(result["frustration"]),
                confusion=Confusion(result["confusion"]),
                confidence=0.85,  # LLM analysis = high confidence
                raw_analysis={
                    **result,
                    "method": "llm",
                },
            )
        except (KeyError, ValueError) as e:
            logger.error(f"LLM sentiment result parse error: {e}. Falling back.")
            raise
