"""Integration-level tests for the extractor and pipeline helpers.

These tests exercise the real extraction code using in-memory content.
They do NOT require Docker / PostgreSQL — pipeline.py is tested at the
unit level here by mocking the DB repository.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.ingestion.extractor import ExtractionResult, extract_text
from app.services.ingestion.parser import parse_document
from app.services.ingestion.validator import validate_candidate

# ── Extractor tests ────────────────────────────────────────────────────────────


class TestExtractText:
    def test_txt_extraction(self, tmp_path: Path):
        content = "This is a test document.\nSecond line."
        p = tmp_path / "test.txt"
        p.write_text(content, encoding="utf-8")
        result = extract_text(p)
        assert isinstance(result, ExtractionResult)
        assert "This is a test document" in result.raw_text
        assert result.word_count > 0

    def test_md_extraction(self, tmp_path: Path):
        content = "# Heading\n\nSome markdown **content**."
        p = tmp_path / "test.md"
        p.write_text(content, encoding="utf-8")
        result = extract_text(p)
        assert "Heading" in result.raw_text

    def test_unsupported_extension_raises(self, tmp_path: Path):
        p = tmp_path / "file.xyz"
        p.write_text("data")
        with pytest.raises(ValueError, match="Unsupported file extension"):
            extract_text(p)

    def test_missing_file_raises(self):
        with pytest.raises(RuntimeError):
            extract_text(Path("/tmp/__nonexistent_file__.txt"))


# ── Parser + validator round-trip ─────────────────────────────────────────────


class TestParserValidatorRoundTrip:
    """Parse a realistic document snippet and validate each candidate."""

    SAMPLE_DOC = """
## Outlook Not Receiving Emails

Symptoms:
- User reports no new emails since Monday
- Outlook shows "connected" but inbox is empty

Troubleshooting
1. Check email rules and filters
2. Verify account sync settings
3. Check mailbox quota

Resolution
1. Remove and re-add Exchange account
2. Run Outlook in safe mode
3. Repair Office installation

Escalate to IT support if the issue persists after these steps.

## VPN Cannot Connect

Symptoms:
- VPN client shows "Authentication failed"
- User gets error code 800

Troubleshooting
1. Verify corporate credentials are correct
2. Check if certificate has expired

Resolution
1. Re-enroll device in Intune
2. Request new VPN certificate from IT

Contact IT helpdesk if certificate renewal is needed.
"""

    def test_two_candidates_parsed(self):
        candidates = parse_document(self.SAMPLE_DOC)
        assert len(candidates) >= 2

    def test_first_candidate_is_outlook(self):
        candidates = parse_document(self.SAMPLE_DOC)
        c = candidates[0]
        assert c.title is not None
        assert "Outlook" in c.title

    def test_second_candidate_is_vpn(self):
        candidates = parse_document(self.SAMPLE_DOC)
        c = candidates[1]
        assert c.title is not None
        assert "VPN" in c.title

    def test_resolution_steps_extracted(self):
        candidates = parse_document(self.SAMPLE_DOC)
        c = candidates[0]
        assert len(c.resolution_steps) >= 1

    def test_symptoms_extracted(self):
        candidates = parse_document(self.SAMPLE_DOC)
        c = candidates[0]
        assert len(c.symptoms) >= 1

    def test_all_candidates_validate_successfully(self):
        candidates = parse_document(self.SAMPLE_DOC)
        for c in candidates:
            result = validate_candidate(
                {
                    "title": c.title,
                    "summary": c.summary,
                    "category": c.category,
                    "symptoms": c.symptoms,
                    "troubleshooting_steps": c.troubleshooting_steps,
                    "resolution_steps": c.resolution_steps,
                    "escalation_criteria": c.escalation_criteria,
                    "tags": c.tags,
                    "confidence": c.confidence,
                }
            )
            # Every candidate from this realistic doc should have no blockers
            assert result.is_valid, (
                f"Candidate '{c.title}' failed validation: {result.blocking_issues}"
            )

    def test_confidence_scores_positive(self):
        candidates = parse_document(self.SAMPLE_DOC)
        for c in candidates:
            assert c.confidence > 0.0, f"Candidate '{c.title}' has zero confidence"


# ── Mapper test ────────────────────────────────────────────────────────────────


class TestMapper:
    def test_maps_to_article_create(self):
        from app.services.ingestion.mapper import map_candidate_to_article_create

        fields = {
            "extracted_title": "Outlook Sync Issue",
            "extracted_summary": "User cannot sync email on Outlook.",
            "extracted_category": "email/outlook",
            "extracted_subcategory": None,
            "extracted_product_or_system": "Outlook",
            "extracted_platform": "Windows",
            "extracted_symptoms": ["Email not syncing"],
            "extracted_troubleshooting_steps": [
                {"step_number": 1, "instruction": "Check connection", "details": ""}
            ],
            "extracted_resolution_steps": [
                {"step_number": 1, "instruction": "Restart Outlook", "details": ""}
            ],
            "extracted_escalation_criteria": "Contact IT if not resolved.",
            "extracted_tags": ["email", "outlook"],
            "extracted_keywords": ["Outlook", "sync"],
            "extracted_owner_group": None,
        }
        article = map_candidate_to_article_create(fields, job_id="test-job-id", candidate_index=0)
        assert article.title == "Outlook Sync Issue"
        assert article.category == "email/outlook"
        assert article.source_type == "document_ingestion"
        assert "test-job-id" in article.source_reference
        assert len(article.resolution_steps) == 1
