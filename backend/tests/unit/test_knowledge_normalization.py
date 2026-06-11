"""Unit tests for article → retrieval normalization and chunking."""

from app.services.knowledge import normalization


def _article() -> dict:
    return {
        "title": "Outlook Not Receiving Email",
        "slug": "outlook-not-receiving",
        "short_summary": "Fix Outlook sync issues.",
        "category": "email/outlook",
        "product_or_system": "microsoft_outlook",
        "platform": "windows",
        "audience": "employee",
        "tags": ["outlook", "sync"],
        "keywords": ["work offline"],
        "symptoms": ["No new mail", "App is slow"],
        "resolution_steps": [
            {
                "step_number": 1,
                "instruction": "Disable Work Offline",
                "details": "Send/Receive tab",
            },
            {"step_number": 2, "instruction": "Restart Outlook"},
        ],
        "escalation_criteria": "Steps do not work",
        "escalation_target_team": "Endpoint",
    }


class TestChunking:
    def test_builds_chunks_for_each_section(self):
        chunks = normalization.build_chunks(_article())
        sections = {c.section for c in chunks}
        assert "short_summary" in sections
        assert "symptoms" in sections
        assert "resolution_steps" in sections
        assert "escalation" in sections

    def test_chunk_indices_are_sequential(self):
        chunks = normalization.build_chunks(_article())
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    def test_contextual_header_includes_identity_and_metadata(self):
        chunks = normalization.build_chunks(_article())
        header = chunks[0].header
        assert "Outlook Not Receiving Email" in header
        assert "Category: email/outlook" in header
        assert "Platform: windows" in header

    def test_steps_rendered_with_numbers_and_details(self):
        chunks = normalization.build_chunks(_article())
        steps_chunk = next(c for c in chunks if c.section == "resolution_steps")
        assert "1. Disable Work Offline — Send/Receive tab" in steps_chunk.content
        assert "2. Restart Outlook" in steps_chunk.content

    def test_empty_sections_skipped(self):
        article = _article()
        article["symptoms"] = []
        sections = {c.section for c in normalization.build_chunks(article)}
        assert "symptoms" not in sections

    def test_token_estimate_positive(self):
        for chunk in normalization.build_chunks(_article()):
            assert chunk.token_estimate > 0


class TestRetrievalText:
    def test_includes_title_tags_and_sections(self):
        text = normalization.build_retrieval_text(_article())
        assert "Outlook Not Receiving Email" in text
        assert "Tags: outlook, sync" in text
        assert "Disable Work Offline" in text

    def test_citation_label_defaults_to_title_and_slug(self):
        article = _article()
        article["citation_label"] = None
        label = normalization.build_citation_label(article)
        assert "Outlook Not Receiving Email" in label
        assert "outlook-not-receiving" in label

    def test_explicit_citation_label_preserved(self):
        article = _article()
        article["citation_label"] = "KB-OUTLOOK-001"
        assert normalization.build_citation_label(article) == "KB-OUTLOOK-001"
