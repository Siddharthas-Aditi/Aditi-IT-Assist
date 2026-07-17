"""Feedback analytics service — aggregations for dashboards and improvement loops.

Responsibilities:
- Aggregate CSAT, helpful rate, resolved rate over a time window
- Compare AI-only vs live-agent session quality
- Compute per-article feedback health (for knowledge improvement loop)
- Compute per-agent feedback summaries
- Flag knowledge articles that breach negative-feedback threshold
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog

from app.repositories.feedback_repository import FeedbackRepository
from app.schemas.feedback import (
    AgentFeedbackSummary,
    ArticleFeedbackSummary,
    FeedbackAnalyticsSummary,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# Articles with this many negative sessions get flagged automatically
ARTICLE_NEGATIVE_FLAG_THRESHOLD = 3


def _safe_rate(numerator: int, denominator: int) -> float | None:
    """Return numerator / denominator, or None if denominator is zero."""
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _safe_avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


class FeedbackAnalyticsService:
    """Aggregates feedback data for dashboards and the knowledge improvement loop."""

    def __init__(self, db: AsyncSession) -> None:  # type: ignore[name-defined]
        self.db = db
        self.repo = FeedbackRepository(db)

    # ──────────────────────────────────────────────────────────────
    # Global summary
    # ──────────────────────────────────────────────────────────────

    async def get_summary(
        self,
        *,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        category: str | None = None,
        support_mode: str | None = None,
    ) -> FeedbackAnalyticsSummary:
        """Compute aggregate feedback metrics for the given window."""
        if not to_dt:
            to_dt = datetime.now(UTC)
        if not from_dt:
            from_dt = to_dt - timedelta(days=30)

        rows = await self.repo.get_analytics_rows(
            from_dt=from_dt,
            to_dt=to_dt,
            category=category,
            support_mode=support_mode,
        )

        total = len(rows)
        helpful_values = [r.helpful for r in rows if r.helpful is not None]
        resolved_values = [r.resolved for r in rows if r.resolved is not None]
        rating_values = [r.rating for r in rows if r.rating is not None]

        helpful_rate = _safe_rate(sum(helpful_values), len(helpful_values))
        resolved_rate = _safe_rate(sum(resolved_values), len(resolved_values))
        csat_avg = _safe_avg([float(v) for v in rating_values])

        # Mode counts
        ai_rows = [r for r in rows if r.support_mode == "ai_only"]
        live_rows = [r for r in rows if r.support_mode == "live_agent_only"]
        hybrid_rows = [r for r in rows if r.support_mode == "ai_plus_live_agent"]

        # AI-only sub-metrics
        ai_helpful = [r.helpful for r in ai_rows if r.helpful is not None]
        ai_resolved = [r.resolved for r in ai_rows if r.resolved is not None]
        ai_ratings = [r.rating for r in ai_rows if r.rating is not None]

        # Live-agent sub-metrics
        live_helpful = [r.helpful for r in live_rows if r.helpful is not None]
        live_resolved = [r.resolved for r in live_rows if r.resolved is not None]
        live_ratings = [r.rating for r in live_rows if r.rating is not None]

        # Quality buckets
        positive_count = sum(1 for r in rows if r.quality_bucket == "positive")
        neutral_count = sum(1 for r in rows if r.quality_bucket == "neutral")
        negative_count = sum(1 for r in rows if r.quality_bucket == "negative")

        # Escalation
        escalated_rows = [r for r in rows if r.escalation_occurred]
        escalated_resolved = [r for r in escalated_rows if r.resolved is True]

        # Category breakdown
        cat_counts: dict[str, int] = {}
        for r in rows:
            if r.category:
                cat_counts[r.category] = cat_counts.get(r.category, 0) + 1
        top_cats = dict(sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:10])

        flagged_count = await self.repo.count_flagged(category=category)

        return FeedbackAnalyticsSummary(
            period_start=from_dt,
            period_end=to_dt,
            total_submissions=total,
            helpful_rate=helpful_rate,
            resolved_rate=resolved_rate,
            csat_avg=csat_avg,
            ai_only_count=len(ai_rows),
            ai_plus_live_agent_count=len(hybrid_rows),
            live_agent_only_count=len(live_rows),
            ai_only_helpful_rate=_safe_rate(sum(ai_helpful), len(ai_helpful)),
            ai_only_resolved_rate=_safe_rate(sum(ai_resolved), len(ai_resolved)),
            ai_only_csat_avg=_safe_avg([float(v) for v in ai_ratings]),
            live_agent_helpful_rate=_safe_rate(sum(live_helpful), len(live_helpful)),
            live_agent_resolved_rate=_safe_rate(sum(live_resolved), len(live_resolved)),
            live_agent_csat_avg=_safe_avg([float(v) for v in live_ratings]),
            positive_count=positive_count,
            neutral_count=neutral_count,
            negative_count=negative_count,
            escalation_rate=_safe_rate(len(escalated_rows), total),
            escalated_resolved_rate=_safe_rate(len(escalated_resolved), len(escalated_rows)),
            category_breakdown=top_cats,
            flagged_count=flagged_count,
        )

    # ──────────────────────────────────────────────────────────────
    # Article health
    # ──────────────────────────────────────────────────────────────

    async def get_article_health(
        self,
        article_ids: list[str],
        *,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> dict[str, ArticleFeedbackSummary]:
        """Return feedback health summary for each of the given article IDs."""
        summaries: dict[str, ArticleFeedbackSummary] = {}
        for article_id in article_ids:
            rows = await self.repo.get_rows_for_article(article_id, from_dt=from_dt, to_dt=to_dt)
            total = len(rows)
            positive = sum(1 for r in rows if r.quality_bucket == "positive")
            negative = sum(1 for r in rows if r.quality_bucket == "negative")
            ratings = [r.rating for r in rows if r.rating is not None]
            helpful_vals = [r.helpful for r in rows if r.helpful is not None]
            resolved_vals = [r.resolved for r in rows if r.resolved is not None]
            flag_count = sum(1 for r in rows if r.review_flag)

            summaries[article_id] = ArticleFeedbackSummary(
                article_id=article_id,
                total_sessions_used=total,
                positive_sessions=positive,
                negative_sessions=negative,
                avg_rating=_safe_avg([float(v) for v in ratings]),
                helpful_rate=_safe_rate(sum(helpful_vals), len(helpful_vals)),
                resolved_rate=_safe_rate(sum(resolved_vals), len(resolved_vals)),
                flag_count=flag_count,
                flag_threshold_breached=(negative >= ARTICLE_NEGATIVE_FLAG_THRESHOLD),
            )
        return summaries

    async def flag_articles_for_review(
        self,
        article_ids: list[str],
        *,
        threshold: int = ARTICLE_NEGATIVE_FLAG_THRESHOLD,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> list[str]:
        """Return article IDs that have breached the negative-feedback threshold.

        The caller (admin task / learning agent) is responsible for
        writing the flag to the KnowledgeArticle record — this service
        only identifies candidates.
        """
        health = await self.get_article_health(article_ids, from_dt=from_dt, to_dt=to_dt)
        flagged = [aid for aid, summary in health.items() if summary.negative_sessions >= threshold]
        if flagged:
            logger.warning(
                "feedback.articles_flagged",
                count=len(flagged),
                threshold=threshold,
                article_ids=flagged,
            )
        return flagged

    # ──────────────────────────────────────────────────────────────
    # Agent summaries
    # ──────────────────────────────────────────────────────────────

    async def get_agent_summary(
        self,
        agent_user_id: uuid.UUID,
        *,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> AgentFeedbackSummary:
        """Compute feedback metrics for a specific live IT agent."""
        if not to_dt:
            to_dt = datetime.now(UTC)
        if not from_dt:
            from_dt = to_dt - timedelta(days=30)

        rows = await self.repo.get_rows_for_agent(agent_user_id, from_dt=from_dt, to_dt=to_dt)
        total = len(rows)
        helpful_vals = [r.helpful for r in rows if r.helpful is not None]
        resolved_vals = [r.resolved for r in rows if r.resolved is not None]
        rating_vals = [r.rating for r in rows if r.rating is not None]
        positive = sum(1 for r in rows if r.quality_bucket == "positive")
        negative = sum(1 for r in rows if r.quality_bucket == "negative")

        return AgentFeedbackSummary(
            agent_user_id=agent_user_id,
            total_sessions=total,
            sessions_with_feedback=total,
            helpful_rate=_safe_rate(sum(helpful_vals), len(helpful_vals)),
            resolved_rate=_safe_rate(sum(resolved_vals), len(resolved_vals)),
            csat_avg=_safe_avg([float(v) for v in rating_vals]),
            positive_count=positive,
            negative_count=negative,
            period_start=from_dt,
            period_end=to_dt,
        )


# ─── DI factory ───────────────────────────────────────────────────────────────


def get_feedback_analytics_service(
    db: AsyncSession,  # type: ignore[name-defined]
) -> FeedbackAnalyticsService:
    return FeedbackAnalyticsService(db)
