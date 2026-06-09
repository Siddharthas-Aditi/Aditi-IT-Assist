"""Knowledge service — manages retrieval and search of knowledge base articles.

Abstracts over the knowledge base storage layer (YAML files in dev, pgvector in prod).
All knowledge queries from workflow nodes should go through this service.
"""

from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.knowledge_base.loader import get_articles_by_category, load_all_knowledge, search_articles

logger = get_logger(__name__)


@dataclass
class RetrievalResult:
    """Result from a knowledge retrieval operation."""

    articles: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    source: str = "keyword"  # "keyword" | "vector" | "hybrid"


class KnowledgeService:
    """Service for knowledge base operations.

    Provides:
    - Category-based article lookup
    - Keyword search (dev fallback)
    - Semantic vector search (production via pgvector)
    - Confidence scoring based on result quality
    """

    def __init__(self) -> None:
        # Eagerly load knowledge on instantiation to validate YAML files
        self._knowledge = load_all_knowledge()

    @property
    def categories(self) -> list[str]:
        """List all available knowledge categories."""
        return list(self._knowledge.keys())

    @property
    def article_count(self) -> int:
        """Total number of loaded articles."""
        return sum(len(articles) for articles in self._knowledge.values())

    async def retrieve_for_category(self, category: str) -> RetrievalResult:
        """Retrieve knowledge articles for a classified issue category.

        Args:
            category: The issue category from triage (e.g., "email/outlook")

        Returns:
            RetrievalResult with articles and confidence score
        """
        articles = get_articles_by_category(category)

        if not articles:
            logger.info("knowledge_no_results", category=category)
            return RetrievalResult(articles=[], confidence=0.0)

        # Score confidence based on match quality
        confidence = self._score_confidence(articles, category)

        logger.info(
            "knowledge_retrieved",
            category=category,
            count=len(articles),
            confidence=confidence,
        )

        return RetrievalResult(
            articles=articles,
            confidence=confidence,
            source="keyword",
        )

    async def search(self, query: str, category: str | None = None, limit: int = 5) -> RetrievalResult:
        """Search knowledge base by query text.

        In development: keyword matching.
        In production: pgvector semantic similarity search.

        Args:
            query: Search query text
            category: Optional category filter
            limit: Maximum results to return

        Returns:
            RetrievalResult with matched articles
        """
        if category:
            articles = get_articles_by_category(category)
        else:
            articles = search_articles(query, limit=limit)

        confidence = self._score_confidence(articles, query) if articles else 0.0

        return RetrievalResult(
            articles=articles[:limit],
            confidence=confidence,
            source="keyword",
        )

    def _score_confidence(self, articles: list[dict], context: str) -> float:
        """Calculate confidence score based on retrieval quality.

        Factors:
        - Number of matching articles (more = higher ceiling)
        - Presence of structured steps (indicates actionable content)
        - Resolution rate metadata from the article
        """
        if not articles:
            return 0.0

        base_confidence = 0.5
        best_article = articles[0]

        # Boost for structured steps
        if best_article.get("steps"):
            base_confidence += 0.2

        # Boost from historical resolution rate
        resolution_rate = best_article.get("resolution_rate", 0)
        if resolution_rate > 0:
            base_confidence += resolution_rate * 0.2

        # Small boost for multiple results (corroborating evidence)
        if len(articles) > 1:
            base_confidence += 0.05

        return min(0.95, base_confidence)


# Singleton
_knowledge_service: KnowledgeService | None = None


def get_knowledge_service() -> KnowledgeService:
    """Get or create the knowledge service singleton."""
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service
