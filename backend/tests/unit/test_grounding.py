"""Tests for the retrieval grounding guardrails (rerank + cross-domain reject)."""

from app.services.agents.diagnostic_state import DiagnosticContext
from app.services.agents.grounding import ground_results


def _mailbox_ctx() -> DiagnosticContext:
    return DiagnosticContext(
        issue_category="email/outlook",
        issue_subtype="mailbox-full",
        symptom="mailbox-full",
        exact_problem_statement="my inbox is full",
        normalized_system="outlook",
    )


CANDIDATES = [
    {
        "id": "outlook-mailbox-full", "title": "Outlook Mailbox Full",
        "category": "email/outlook", "subcategory": "mailbox-full",
        "tags": ["mailbox", "full", "storage"], "content": "clear deleted items junk",
        "score": 0.5,
    },
    {
        "id": "pw", "title": "Reset your password", "category": "access/permissions",
        "subcategory": "password-expired", "tags": ["password"],
        "content": "reset password wait", "score": 0.95,
    },
    {
        "id": "win", "title": "Windows Update", "category": "device-management/intune",
        "subcategory": "update", "tags": ["update"], "content": "windows update", "score": 0.9,
    },
    {
        "id": "outlook-general", "title": "General Outlook", "category": "email/outlook",
        "subcategory": "other", "tags": ["outlook"], "content": "restart outlook", "score": 0.4,
    },
]


class TestGrounding:
    def test_subtype_article_ranked_first(self):
        g = ground_results(CANDIDATES, _mailbox_ctx())
        kept = [a["id"] for a in g.kept_articles()]
        assert kept[0] == "outlook-mailbox-full"
        assert g.has_subtype_match is True

    def test_cross_domain_articles_rejected(self):
        g = ground_results(CANDIDATES, _mailbox_ctx())
        rejected = {r["id"] for r in g.rejected}
        # Password (access) and Windows Update (device-management) must be removed
        # even though their raw retriever scores were the highest.
        assert "pw" in rejected
        assert "win" in rejected
        kept = {a["id"] for a in g.kept_articles()}
        assert "pw" not in kept and "win" not in kept

    def test_only_same_family_kept(self):
        g = ground_results(CANDIDATES, _mailbox_ctx())
        for a in g.kept_articles():
            assert a["category"].startswith("email/")

    def test_trace_is_serializable(self):
        g = ground_results(CANDIDATES, _mailbox_ctx())
        trace = g.trace()
        assert "kept" in trace and "rejected" in trace
        assert trace["has_subtype_match"] is True
