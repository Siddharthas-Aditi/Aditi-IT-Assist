"""Unit tests for the ingestion validator (pure logic — no DB)."""

import pytest

from app.services.ingestion.validator import ValidationResult, validate_candidate


def _make(
    title: str | None = "Outlook Email Sync Issue",
    category: str | None = "email/outlook",
    symptoms: list | None = None,
    troubleshooting: list | None = None,
    resolution: list | None = None,
    summary: str | None = "Short helpful summary for this issue.",
    escalation: str | None = "Contact IT support if unresolved.",
    tags: list | None = None,
    confidence: float = 0.6,
) -> dict:
    return {
        "title": title,
        "summary": summary,
        "category": category,
        "symptoms": symptoms or ["User cannot sync email"],
        "troubleshooting_steps": troubleshooting or [{"step_number": 1, "instruction": "Check network", "details": ""}],
        "resolution_steps": resolution or [{"step_number": 1, "instruction": "Restart Outlook", "details": ""}],
        "escalation_criteria": escalation,
        "tags": tags or ["email", "outlook"],
        "confidence": confidence,
    }


class TestBlockingIssues:
    def test_missing_title_is_blocker(self):
        result = validate_candidate(_make(title=None))
        assert not result.is_valid
        assert any(w["code"] == "MISSING_TITLE" for w in result.blocking_issues)

    def test_short_title_is_blocker(self):
        result = validate_candidate(_make(title="ok"))
        assert not result.is_valid

    def test_missing_category_is_blocker(self):
        result = validate_candidate(_make(category=None))
        assert not result.is_valid
        assert any(w["code"] == "MISSING_CATEGORY" for w in result.blocking_issues)

    def test_no_actionable_content_is_blocker(self):
        result = validate_candidate(_make(symptoms=[], troubleshooting=[], resolution=[]))
        assert not result.is_valid
        assert any(w["code"] == "NO_ACTIONABLE_CONTENT" for w in result.blocking_issues)

    def test_fully_populated_candidate_is_valid(self):
        result = validate_candidate(_make())
        assert result.is_valid


class TestWarnings:
    def test_missing_summary_triggers_warning(self):
        result = validate_candidate(_make(summary=None))
        assert any(w["code"] == "MISSING_SUMMARY" for w in result.warnings)

    def test_short_summary_triggers_warning(self):
        result = validate_candidate(_make(summary="Too short"))
        assert any(w["code"] == "MISSING_SUMMARY" for w in result.warnings)

    def test_missing_escalation_triggers_warning(self):
        result = validate_candidate(_make(escalation=None))
        assert any(w["code"] == "MISSING_ESCALATION" for w in result.warnings)

    def test_weak_tags_triggers_warning(self):
        result = validate_candidate(_make(tags=["only-one"]))
        assert any(w["code"] == "WEAK_TAGS" for w in result.warnings)

    def test_low_confidence_triggers_warning(self):
        result = validate_candidate(_make(confidence=0.2))
        assert any(w["code"] == "LOW_EXTRACTION_CONFIDENCE" for w in result.warnings)


class TestConfidenceComputation:
    def test_blocker_reduces_confidence(self):
        no_title = validate_candidate(_make(title=None))
        with_title = validate_candidate(_make())
        assert no_title.confidence < with_title.confidence

    def test_confidence_never_negative(self):
        result = validate_candidate(
            _make(title=None, category=None, symptoms=[], troubleshooting=[], resolution=[])
        )
        assert result.confidence >= 0.0

    def test_confidence_never_above_one(self):
        result = validate_candidate(_make(confidence=1.0))
        assert result.confidence <= 1.0


class TestToWarningDicts:
    def test_merge_blockers_and_warnings(self):
        result = validate_candidate(_make(title=None, summary=None))
        all_warnings = result.to_warning_dicts()
        severities = {w["severity"] for w in all_warnings}
        # Should have both errors and warnings
        assert "error" in severities
        assert "warning" in severities
