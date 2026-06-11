"""Governed knowledge retrieval for the AI chat agent.

This is the read-side boundary between the knowledge base and agent
orchestration. It guarantees the central safety property of the platform:

    The employee-facing chat agent retrieves **only published** articles.

Internal IT/admin assist can opt into a broader scope when the caller holds the
``knowledge:view_internal`` permission. Results are returned with
citation-ready snippets and source attribution, and a low-confidence flag the
orchestrator can use to trigger escalation.

When the database has no published articles (fresh dev environments), retrieval
transparently falls back to the legacy YAML keyword service so the chat flow is
never empty during local development.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.knowledge_service import get_knowledge_service

if TYPE_CHECKING:
    import uuid

    from app.models.knowledge import KnowledgeArticle

logger = get_logger(__name__)

#: Below this composite score, the orchestrator should consider escalation.
LOW_CONFIDENCE_THRESHOLD = 0.45

# Which article audiences each viewer scope may retrieve.
EMPLOYEE_AUDIENCES = ("employee",)
IT_AUDIENCES = ("employee", "it_staff")
ADMIN_AUDIENCES = ("employee", "it_staff", "admin")


@dataclass
class ScoredArticle:
    article: KnowledgeArticle
    score: float
    snippet: str


@dataclass
class GovernedRetrievalResult:
    """Result of a governed retrieval, ready for citation + orchestration."""

    items: list[ScoredArticle] = field(default_factory=list)
    confidence: float = 0.0
    source: str = "db_keyword"
    published_only: bool = True
    fallback_used: bool = False

    @property
    def low_confidence(self) -> bool:
        return self.confidence < LOW_CONFIDENCE_THRESHOLD


class KnowledgeRetrievalService:
    """Read-only retrieval over governed (published) knowledge content."""

    def __init__(self, db) -> None:
        self.db = db
        self.repo = KnowledgeRepository(db)

    # ── Scope resolution ────────────────────────────────────────

    @staticmethod
    def audiences_for(*, is_employee_facing: bool, can_view_internal: bool) -> tuple[str, ...]:
        if is_employee_facing:
            return EMPLOYEE_AUDIENCES
        return ADMIN_AUDIENCES if can_view_internal else IT_AUDIENCES

    # ── Search ──────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        *,
        category: str | None = None,
        product_or_system: str | None = None,
        platform: str | None = None,
        is_employee_facing: bool = True,
        can_view_internal: bool = False,
        limit: int = 5,
    ) -> GovernedRetrievalResult:
        """Search published knowledge, returning scored, citation-ready hits."""
        audiences = self.audiences_for(
            is_employee_facing=is_employee_facing, can_view_internal=can_view_internal
        )
        candidates = await self.repo.list_published(
            category=category,
            product_or_system=product_or_system,
            platform=platform,
            audiences=list(audiences),
            limit=200,
        )

        if not candidates:
            return await self._yaml_fallback(query, category, limit)

        scored = self._rank(query, candidates)[:limit]
        confidence = self._confidence(scored)
        logger.info(
            "knowledge_db_retrieved",
            query=query,
            count=len(scored),
            confidence=confidence,
            audiences=audiences,
        )
        return GovernedRetrievalResult(
            items=scored,
            confidence=confidence,
            source="db_keyword",
            published_only=is_employee_facing or not can_view_internal,
        )

    async def retrieve_for_category(
        self,
        category: str,
        *,
        is_employee_facing: bool = True,
        can_view_internal: bool = False,
        limit: int = 5,
    ) -> GovernedRetrievalResult:
        return await self.search(
            category,
            category=category,
            is_employee_facing=is_employee_facing,
            can_view_internal=can_view_internal,
            limit=limit,
        )

    # ── Scoring ─────────────────────────────────────────────────

    def _rank(self, query: str, articles: list[KnowledgeArticle]) -> list[ScoredArticle]:
        terms = {t for t in query.lower().split() if len(t) > 2}
        scored: list[ScoredArticle] = []
        for art in articles:
            haystack = (art.retrieval_text or art.title or "").lower()
            tag_text = " ".join(str(t) for t in (art.tags or [])).lower()
            overlap = sum(1 for t in terms if t in haystack or t in tag_text)
            base = overlap / len(terms) if terms else 0.3
            # Boost well-performing, frequently-used content.
            usage_boost = min(0.15, (art.usage_count or 0) / 200)
            quality_boost = 0.15 * (art.quality_score or 0.0)
            score = min(1.0, base + usage_boost + quality_boost)
            if score <= 0 and terms:
                continue
            scored.append(
                ScoredArticle(article=art, score=round(score, 3), snippet=self._snippet(art))
            )
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored

    @staticmethod
    def _snippet(article: KnowledgeArticle) -> str:
        if article.short_summary:
            return article.short_summary
        text = (article.retrieval_text or article.content or "").strip()
        return (text[:240] + "…") if len(text) > 240 else text

    @staticmethod
    def _confidence(scored: list[ScoredArticle]) -> float:
        if not scored:
            return 0.0
        top = scored[0].score
        corroboration = 0.05 if len(scored) > 1 else 0.0
        return round(min(0.95, top + corroboration), 3)

    # ── Usage tracking ──────────────────────────────────────────

    async def record_usage(self, article_id: uuid.UUID, *, resolved: bool = False) -> None:
        article = await self.repo.get(article_id)
        if not article:
            return
        article.usage_count += 1
        if resolved:
            article.successful_resolution_count += 1

    async def record_view(self, article_id: uuid.UUID) -> None:
        article = await self.repo.get(article_id)
        if article:
            article.view_count += 1

    # ── Fallback ────────────────────────────────────────────────

    async def _yaml_fallback(
        self, query: str, category: str | None, limit: int
    ) -> GovernedRetrievalResult:
        """Dev fallback to YAML keyword search when DB has no published content."""
        legacy = get_knowledge_service()
        result = await legacy.search(query, category=category, limit=limit)
        items = [
            ScoredArticle(
                article=_DictArticle(a),
                score=result.confidence,
                snippet=a.get("content", "")[:240],
            )
            for a in result.articles
        ]
        logger.info("knowledge_yaml_fallback", query=query, count=len(items))
        return GovernedRetrievalResult(
            items=items,
            confidence=result.confidence,
            source="yaml_fallback",
            published_only=True,
            fallback_used=True,
        )


class _DictArticle:
    """Adapter exposing a YAML article dict via the attributes citations expect."""

    def __init__(self, data: dict) -> None:
        self.id = data.get("id", "yaml")
        self.title = data.get("title", "")
        self.category = data.get("category", "")
        self.slug = data.get("id")
        self.citation_label = data.get("title", "")
        self.retrieval_text = data.get("content", "")
        self.short_summary = None
