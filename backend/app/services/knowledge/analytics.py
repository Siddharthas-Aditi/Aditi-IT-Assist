"""Knowledge analytics — usage and effectiveness aggregation.

Powers the admin analytics page: corpus health, content effectiveness, and
identification of low-performing or stale articles that need attention.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.knowledge.serializers import is_stale

if TYPE_CHECKING:
    from app.models.knowledge import KnowledgeArticle


def _resolution_rate(article: KnowledgeArticle) -> float | None:
    if not article.usage_count:
        return None
    return round(article.successful_resolution_count / article.usage_count, 3)


def article_analytics(article: KnowledgeArticle) -> dict:
    return {
        "article_id": str(article.id),
        "title": article.title,
        "status": article.status,
        "view_count": article.view_count,
        "usage_count": article.usage_count,
        "successful_resolution_count": article.successful_resolution_count,
        "feedback_score": article.feedback_score,
        "negative_feedback_count": article.negative_feedback_count,
        "resolution_rate": _resolution_rate(article),
        "quality_score": article.quality_score,
        "is_stale": is_stale(article),
    }


class KnowledgeAnalyticsService:
    """Aggregates knowledge-base usage and effectiveness metrics."""

    def __init__(self, db) -> None:
        self.repo = KnowledgeRepository(db)

    async def summary(self) -> dict:
        by_status = await self.repo.count_by_status()
        # Pull a broad page to compute corpus-level rollups.
        articles, total = await self.repo.list(limit=1000, offset=0)
        published = [a for a in articles if a.status == "published"]
        stale = [a for a in published if is_stale(a)]

        quality_scores = [a.quality_score for a in articles if a.quality_score is not None]
        rates = [r for a in published if (r := _resolution_rate(a)) is not None]

        # Effectiveness ranking among published content.
        ranked = sorted(
            published,
            key=lambda a: ((a.usage_count or 0), (a.feedback_score or 0)),
            reverse=True,
        )
        top = [article_analytics(a) for a in ranked[:5]]
        low = [
            article_analytics(a)
            for a in published
            if (a.negative_feedback_count or 0) > 0
            or ((a.feedback_score is not None) and a.feedback_score < 0.5)
        ][:5]

        return {
            "total_articles": total,
            "by_status": by_status,
            "published_articles": len(published),
            "stale_articles": len(stale),
            "avg_quality_score": round(sum(quality_scores) / len(quality_scores), 3)
            if quality_scores
            else None,
            "total_views": sum(a.view_count or 0 for a in articles),
            "total_usage": sum(a.usage_count or 0 for a in articles),
            "avg_resolution_rate": round(sum(rates) / len(rates), 3) if rates else None,
            "top_articles": top,
            "low_performers": low,
        }

    async def article_detail(self, article_id) -> dict | None:
        article = await self.repo.get(article_id)
        return article_analytics(article) if article else None
