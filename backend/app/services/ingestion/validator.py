"""Validation rules for ingestion candidates.

Produces:
- ``blocking_issues``  — errors that prevent saving the candidate as a KB article
- ``warnings``         — non-blocking quality concerns surfaced to the reviewer
- ``confidence``       — overall 0.0–1.0 quality signal

Validation is deterministic (no LLM) and mirrors the spirit of
``services/knowledge/lifecycle.py:validate_for_submit`` but is applied to raw
candidate payloads before they become articles.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────────────
# Result type
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    """Outcome of validating a single candidate payload."""

    blocking_issues: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    confidence: float = 0.0

    @property
    def is_valid(self) -> bool:
        """True when there are no blocking issues."""
        return len(self.blocking_issues) == 0

    def to_warning_dicts(self) -> list[dict]:
        """Merge blocking issues + warnings into a single list for persistence."""
        return self.blocking_issues + self.warnings


def _error(code: str, message: str) -> dict:
    return {"code": code, "message": message, "severity": "error"}


def _warn(code: str, message: str) -> dict:
    return {"code": code, "message": message, "severity": "warning"}


def _info(code: str, message: str) -> dict:
    return {"code": code, "message": message, "severity": "info"}


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def validate_candidate(candidate_dict: dict) -> ValidationResult:
    """Validate a candidate payload dict, returning a ``ValidationResult``.

    *candidate_dict* keys mirror ``CandidatePayload`` field names:
    ``title``, ``summary``, ``category``, ``symptoms``,
    ``troubleshooting_steps``, ``resolution_steps``, ``escalation_criteria``,
    ``tags``, ``keywords``, ``confidence``.
    """
    blockers: list[dict] = []
    warnings: list[dict] = []

    title: str | None = candidate_dict.get("title")
    summary: str | None = candidate_dict.get("summary")
    category: str | None = candidate_dict.get("category")
    symptoms: list = candidate_dict.get("symptoms") or []
    troubleshooting: list = candidate_dict.get("troubleshooting_steps") or []
    resolution: list = candidate_dict.get("resolution_steps") or []
    escalation: str | None = candidate_dict.get("escalation_criteria")
    tags: list = candidate_dict.get("tags") or []
    confidence: float = float(candidate_dict.get("confidence") or 0.0)

    # ── Blocking checks ──────────────────────────────────────────────────────

    if not title or len(title.strip()) < 5:
        blockers.append(_error(
            "MISSING_TITLE",
            "Title is required and must be at least 5 characters.",
        ))

    if not category:
        blockers.append(_error(
            "MISSING_CATEGORY",
            "Category could not be determined. Select one before saving.",
        ))

    has_body = bool(troubleshooting or resolution or symptoms)
    if not has_body:
        blockers.append(_error(
            "NO_ACTIONABLE_CONTENT",
            "The candidate has no symptoms, troubleshooting steps, or resolution steps.",
        ))

    # ── Quality warnings ─────────────────────────────────────────────────────

    if not summary or len(summary) < 30:
        warnings.append(_warn(
            "MISSING_SUMMARY",
            "A short summary (≥ 30 chars) improves discoverability.",
        ))

    if not escalation:
        warnings.append(_warn(
            "MISSING_ESCALATION",
            "No escalation criteria found. Consider adding when to contact IT support.",
        ))

    if len(tags) < 2:
        warnings.append(_warn(
            "WEAK_TAGS",
            "Fewer than 2 tags detected. Add tags to improve search ranking.",
        ))

    if len(troubleshooting) == 0 and len(resolution) > 0:
        warnings.append(_info(
            "NO_TROUBLESHOOTING_STEPS",
            "Only resolution steps found — no troubleshooting steps. This may be intentional.",
        ))

    if confidence < 0.4:
        warnings.append(_warn(
            "LOW_EXTRACTION_CONFIDENCE",
            f"Extraction confidence is {confidence:.0%}. Review all fields carefully.",
        ))

    if title and len(title) > 200:
        warnings.append(_warn(
            "LONG_TITLE",
            "Title is very long (> 200 chars). Consider shortening for display.",
        ))

    # ── Compute composite confidence ─────────────────────────────────────────
    computed_confidence = _compute_confidence(
        base=confidence,
        has_title=bool(title and len(title) >= 5),
        has_category=bool(category),
        has_summary=bool(summary and len(summary) >= 30),
        has_symptoms=bool(symptoms),
        has_steps=bool(troubleshooting or resolution),
        has_escalation=bool(escalation),
        blocker_count=len(blockers),
    )

    return ValidationResult(
        blocking_issues=blockers,
        warnings=warnings,
        confidence=computed_confidence,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Confidence formula
# ─────────────────────────────────────────────────────────────────────────────

def _compute_confidence(
    *,
    base: float,
    has_title: bool,
    has_category: bool,
    has_summary: bool,
    has_symptoms: bool,
    has_steps: bool,
    has_escalation: bool,
    blocker_count: int,
) -> float:
    """Derive a final confidence score from base + completeness bonuses."""
    score = base
    score += 0.10 if has_title else 0.0
    score += 0.10 if has_category else 0.0
    score += 0.05 if has_summary else 0.0
    score += 0.05 if has_symptoms else 0.0
    score += 0.10 if has_steps else 0.0
    score += 0.05 if has_escalation else 0.0
    # Penalise blockers
    score -= blocker_count * 0.20
    return round(max(0.0, min(score, 1.0)), 3)
