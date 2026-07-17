"""Composite confidence scorer for ExtractionCandidate.

Called as the final step before validation to:
  1. Compute a weighted composite score from per-field confidences.
  2. Classify that score into ConfidenceLevel (HIGH / MEDIUM / LOW / VERY_LOW).
  3. Set ``review_required`` and attach ``parser_warnings``.
  4. Populate ``extraction_metadata`` for JSONB storage.

Design:
- The weights come from the active ``ParserProfile.confidence_weights``, so
  tuning confidence balance requires only a profile change — no code change.
- Semantic signals from the segmenter provide a small completeness bonus.
- The function is pure (no I/O) and returns the mutated candidate in-place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.ingestion.schema import (
    MEDIUM_THRESHOLD,
    ExtractionCandidate,
    FieldExtraction,
    SemanticSignal,
    classify_confidence,
    review_required_for_score,
)

if TYPE_CHECKING:
    from app.services.ingestion.profiles.base import ConfidenceWeights, ParserProfile

# ── Fields included in composite scoring ─────────────────────────────────────
# Ordered by typical impact on article quality.
_SCOREABLE_FIELDS: list[str] = [
    "title",
    "category",
    "short_summary",
    "symptoms",
    "troubleshooting_steps",
    "resolution_steps",
    "escalation_criteria",
    "tags",
    "product_or_system",
]


# ── Public API ────────────────────────────────────────────────────────────────


def score_candidate(
    candidate: ExtractionCandidate,
    profile: ParserProfile,
) -> ExtractionCandidate:
    """Compute composite confidence and annotate *candidate* in-place.

    Mutates and returns *candidate* so the call can be chained:
        candidate = score_candidate(candidate, profile)
    """
    weights = profile.confidence_weights
    raw_score = _weighted_score(candidate, weights)
    completeness_bonus = _completeness_bonus(candidate)
    raw_score = min(raw_score + completeness_bonus, 1.0)

    candidate.extraction_confidence = round(raw_score, 4)
    candidate.confidence_level = classify_confidence(raw_score).value
    candidate.review_required = review_required_for_score(raw_score)
    candidate.parser_warnings = _build_warnings(candidate)
    candidate.extraction_metadata = candidate.build_metadata()
    return candidate


# ── Scoring helpers ────────────────────────────────────────────────────────────


def _weighted_score(candidate: ExtractionCandidate, weights: ConfidenceWeights) -> float:
    """Return sum of (field_weight × field_confidence) normalised to 0–1."""
    total_weight = weights.total()
    if total_weight <= 0:
        return 0.0

    accumulated = 0.0
    for field_name in _SCOREABLE_FIELDS:
        weight = getattr(weights, field_name, 0.0)
        if weight <= 0:
            continue
        fe = getattr(candidate, field_name, None)
        field_conf = fe.confidence if isinstance(fe, FieldExtraction) else 0.0
        accumulated += weight * field_conf

    return accumulated / total_weight


def _completeness_bonus(candidate: ExtractionCandidate) -> float:
    """Grant up to +0.08 for a semantically complete IT topic.

    Bonus structure:
    - +0.04 if BOTH symptoms and resolution_steps are present (complete topic)
    - +0.02 if escalation criteria are present
    - +0.02 if IS_COMPLETE_TOPIC flag is set by segmenter
    """
    bonus = 0.0
    symptoms_conf = candidate.field_confidence("symptoms")
    resolution_conf = candidate.field_confidence("resolution_steps")

    if symptoms_conf >= MEDIUM_THRESHOLD and resolution_conf >= MEDIUM_THRESHOLD:
        bonus += 0.04

    if candidate.field_confidence("escalation_criteria") >= MEDIUM_THRESHOLD:
        bonus += 0.02

    if SemanticSignal.IS_COMPLETE_TOPIC in candidate.semantic_signals:
        bonus += 0.02

    return bonus


def _build_warnings(candidate: ExtractionCandidate) -> list[str]:
    """Return a list of human-readable warnings for the review UI."""
    warnings: list[str] = []

    if not candidate.field_value("title"):
        warnings.append("No title could be extracted — reviewer must supply one.")

    if not candidate.field_value("category"):
        warnings.append("Category could not be determined — select from dropdown.")

    if not candidate.field_value("resolution_steps"):
        warnings.append("No resolution steps found — consider adding them before publishing.")

    if not candidate.field_value("symptoms"):
        warnings.append("No symptoms detected — article may be hard to find via search.")

    title_conf = candidate.field_confidence("title")
    if 0 < title_conf < MEDIUM_THRESHOLD:
        warnings.append(
            f"Title confidence is low ({title_conf:.0%}) — "
            "verify it describes the issue accurately."
        )

    res_conf = candidate.field_confidence("resolution_steps")
    if 0 < res_conf < MEDIUM_THRESHOLD:
        warnings.append(
            f"Resolution steps confidence is low ({res_conf:.0%}) — review each step carefully."
        )

    if candidate.extraction_confidence < MEDIUM_THRESHOLD:
        warnings.append(
            "Overall extraction confidence is below 50% — "
            "thorough review required before publishing."
        )

    return warnings
