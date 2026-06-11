"""Unit tests for governed retrieval scoring and audience scoping (pure parts)."""

from types import SimpleNamespace

from app.services.knowledge.retrieval import (
    ADMIN_AUDIENCES,
    EMPLOYEE_AUDIENCES,
    IT_AUDIENCES,
    LOW_CONFIDENCE_THRESHOLD,
    KnowledgeRetrievalService,
)


def _article(**kw):
    base = dict(
        id="a1",
        title="Outlook sync fix",
        retrieval_text="outlook email sync work offline send receive",
        tags=["outlook", "email"],
        usage_count=0,
        quality_score=0.5,
        short_summary="Fix Outlook sync.",
        content=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestAudienceScoping:
    def test_employee_facing_is_published_employee_only(self):
        assert (
            KnowledgeRetrievalService.audiences_for(is_employee_facing=True, can_view_internal=True)
            == EMPLOYEE_AUDIENCES
        )

    def test_it_staff_without_internal_sees_it_scope(self):
        assert (
            KnowledgeRetrievalService.audiences_for(
                is_employee_facing=False, can_view_internal=False
            )
            == IT_AUDIENCES
        )

    def test_internal_permission_widens_to_admin_scope(self):
        assert (
            KnowledgeRetrievalService.audiences_for(
                is_employee_facing=False, can_view_internal=True
            )
            == ADMIN_AUDIENCES
        )


class TestRanking:
    def setup_method(self):
        self.svc = KnowledgeRetrievalService(db=None)

    def test_keyword_overlap_ranks_relevant_first(self):
        relevant = _article(id="rel", retrieval_text="outlook email not receiving sync")
        irrelevant = _article(
            id="irr", title="Zoom audio", retrieval_text="zoom audio video", tags=["zoom"]
        )
        ranked = self.svc._rank("outlook email sync", [irrelevant, relevant])
        assert ranked[0].article.id == "rel"

    def test_usage_and_quality_boost(self):
        # Partial keyword match (1 of 3 terms) so usage/quality boosts decide ties.
        low = _article(
            id="low", retrieval_text="outlook", tags=[], usage_count=0, quality_score=0.0
        )
        high = _article(
            id="high", retrieval_text="outlook", tags=[], usage_count=200, quality_score=1.0
        )
        ranked = self.svc._rank("outlook missing definitely", [low, high])
        assert ranked[0].article.id == "high"

    def test_confidence_zero_when_empty(self):
        assert self.svc._confidence([]) == 0.0

    def test_low_confidence_flag(self):
        result_terms = self.svc._rank("totally unrelated xyz", [_article()])
        conf = self.svc._confidence(result_terms)
        # Unrelated query → below threshold
        assert (conf < LOW_CONFIDENCE_THRESHOLD) or conf == 0.0

    def test_snippet_prefers_summary(self):
        assert self.svc._snippet(_article(short_summary="Short.")) == "Short."
