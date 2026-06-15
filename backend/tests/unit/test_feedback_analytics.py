"""Unit tests for FeedbackAnalyticsService.

Tests cover:
- helpful_rate and resolved_rate calculation
- csat_avg excludes None ratings
- article health: negative_count is accurate
- empty dataset returns None rates
- mode split counts
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.feedback_analytics_service import (
    FeedbackAnalyticsService,
    _safe_avg,
    _safe_rate,
)


def make_row(
    helpful: bool | None = None,
    resolved: bool | None = None,
    rating: int | None = None,
    support_mode: str = "ai_only",
    quality_bucket: str | None = None,
    review_flag: bool = False,
    escalation_occurred: bool = False,
    category: str | None = None,
    knowledge_article_ids: list | None = None,
) -> MagicMock:
    row = MagicMock()
    row.helpful = helpful
    row.resolved = resolved
    row.rating = rating
    row.support_mode = support_mode
    row.quality_bucket = quality_bucket
    row.review_flag = review_flag
    row.escalation_occurred = escalation_occurred
    row.category = category
    row.knowledge_article_ids = knowledge_article_ids
    return row


class TestSafeHelpers:
    def test_safe_rate_normal(self):
        assert _safe_rate(3, 4) == pytest.approx(0.75)

    def test_safe_rate_zero_denominator(self):
        assert _safe_rate(0, 0) is None

    def test_safe_avg_normal(self):
        assert _safe_avg([4.0, 5.0]) == pytest.approx(4.5)

    def test_safe_avg_empty(self):
        assert _safe_avg([]) is None


class TestFeedbackAnalyticsService:
    def _make_service(self, rows: list) -> FeedbackAnalyticsService:
        db = AsyncMock()
        service = FeedbackAnalyticsService(db)
        service.repo = AsyncMock()
        service.repo.get_analytics_rows = AsyncMock(return_value=rows)
        service.repo.count_flagged = AsyncMock(return_value=0)
        return service

    @pytest.mark.asyncio
    async def test_helpful_rate_calculation(self):
        rows = [
            make_row(helpful=True),
            make_row(helpful=True),
            make_row(helpful=False),
            make_row(helpful=None),  # excluded from rate
        ]
        service = self._make_service(rows)
        summary = await service.get_summary(
            from_dt=datetime(2024, 1, 1, tzinfo=timezone.utc),
            to_dt=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        # 2 True out of 3 with non-None values
        assert summary.helpful_rate == pytest.approx(2 / 3, abs=0.001)

    @pytest.mark.asyncio
    async def test_csat_average_excludes_null_ratings(self):
        rows = [
            make_row(rating=5),
            make_row(rating=3),
            make_row(rating=None),  # excluded
        ]
        service = self._make_service(rows)
        summary = await service.get_summary(
            from_dt=datetime(2024, 1, 1, tzinfo=timezone.utc),
            to_dt=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        assert summary.csat_avg == pytest.approx(4.0)

    @pytest.mark.asyncio
    async def test_empty_dataset_returns_none_rates(self):
        service = self._make_service([])
        summary = await service.get_summary(
            from_dt=datetime(2024, 1, 1, tzinfo=timezone.utc),
            to_dt=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        assert summary.helpful_rate is None
        assert summary.csat_avg is None
        assert summary.total_submissions == 0

    @pytest.mark.asyncio
    async def test_mode_split_counts(self):
        rows = [
            make_row(support_mode="ai_only"),
            make_row(support_mode="ai_only"),
            make_row(support_mode="live_agent_only"),
            make_row(support_mode="ai_plus_live_agent"),
        ]
        service = self._make_service(rows)
        summary = await service.get_summary(
            from_dt=datetime(2024, 1, 1, tzinfo=timezone.utc),
            to_dt=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        assert summary.ai_only_count == 2
        assert summary.live_agent_only_count == 1
        assert summary.ai_plus_live_agent_count == 1

    @pytest.mark.asyncio
    async def test_article_health_negative_count(self):
        article_id = "article-abc"
        rows = [
            make_row(quality_bucket="negative", review_flag=True),
            make_row(quality_bucket="negative", review_flag=True),
            make_row(quality_bucket="positive", review_flag=False),
        ]
        db = AsyncMock()
        service = FeedbackAnalyticsService(db)
        service.repo = AsyncMock()
        service.repo.get_rows_for_article = AsyncMock(return_value=rows)

        health = await service.get_article_health([article_id])
        summary = health[article_id]

        assert summary.negative_sessions == 2
        assert summary.positive_sessions == 1
        assert summary.flag_count == 2
        # 2 negative < threshold (3), so threshold NOT breached
        assert summary.flag_threshold_breached is False

    @pytest.mark.asyncio
    async def test_flag_articles_returns_threshold_breached(self):
        article_id = "article-xyz"
        # 4 negative rows — above default threshold (3)
        rows = [make_row(quality_bucket="negative") for _ in range(4)]
        db = AsyncMock()
        service = FeedbackAnalyticsService(db)
        service.repo = AsyncMock()
        service.repo.get_rows_for_article = AsyncMock(return_value=rows)

        flagged = await service.flag_articles_for_review([article_id])
        assert article_id in flagged

    @pytest.mark.asyncio
    async def test_agent_summary_computes_correctly(self):
        agent_id = uuid.uuid4()
        rows = [
            make_row(helpful=True, resolved=True, rating=5, quality_bucket="positive"),
            make_row(helpful=False, resolved=False, rating=1, quality_bucket="negative"),
        ]
        db = AsyncMock()
        service = FeedbackAnalyticsService(db)
        service.repo = AsyncMock()
        service.repo.get_rows_for_agent = AsyncMock(return_value=rows)

        summary = await service.get_agent_summary(
            agent_id,
            from_dt=datetime(2024, 1, 1, tzinfo=timezone.utc),
            to_dt=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        assert summary.total_sessions == 2
        assert summary.csat_avg == pytest.approx(3.0)
        assert summary.positive_count == 1
        assert summary.negative_count == 1
