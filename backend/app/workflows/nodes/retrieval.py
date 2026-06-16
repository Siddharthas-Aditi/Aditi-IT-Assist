"""Knowledge Retrieval Agent Node — searches the governed knowledge base.

Uses KnowledgeRetrievalService (DB-backed, published-only) as the primary
source, automatically falling back to the YAML seed when the database has no
published articles (fresh dev environments).
"""

from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.services.knowledge.retrieval import KnowledgeRetrievalService
from app.workflows.state import WorkflowState

logger = get_logger(__name__)


def _scored_to_dict(scored_article) -> dict:
    """Convert a ScoredArticle into a plain dict for workflow state."""
    art = scored_article.article
    # Support both KnowledgeArticle ORM instances and _DictArticle adapters
    return {
        "id": str(getattr(art, "id", "unknown")),
        "title": getattr(art, "title", ""),
        "category": getattr(art, "category", ""),
        "citation_label": getattr(art, "citation_label", None) or getattr(art, "title", ""),
        # Prefer structured resolution_steps; fall back to legacy steps field
        "resolution_steps": getattr(art, "resolution_steps", None) or [],
        "steps": getattr(art, "steps", None) or getattr(art, "resolution_steps", None) or [],
        "content": (
            getattr(art, "retrieval_text", None)
            or getattr(art, "content", None)
            or scored_article.snippet
            or ""
        ),
        "short_summary": getattr(art, "short_summary", None),
        "snippet": scored_article.snippet,
        "score": scored_article.score,
        "troubleshooting_steps": getattr(art, "troubleshooting_steps", None) or [],
    }


def _build_citations(articles: list[dict]) -> list[dict]:
    """Project retrieved articles into citation-ready source attributions."""
    return [
        {
            "article_id": a.get("id", "unknown"),
            "title": a.get("title", "Knowledge Article"),
            "citation_label": a.get("citation_label") or a.get("title", ""),
            "category": a.get("category"),
        }
        for a in articles
    ]


async def retrieval_node(state: WorkflowState) -> dict:
    """Search the governed knowledge base for articles matching the classified issue.

    This node:
    1. Uses the issue category from triage as the retrieval signal
    2. Searches via KnowledgeRetrievalService (DB-backed, published-only)
    3. Falls back to YAML seed when DB has no published content
    4. Returns ranked articles, citations, and a composite confidence score
    """
    logger.info(
        "retrieval_node_start",
        session_id=state.get("session_id"),
        category=state.get("issue_category"),
    )

    category = state.get("issue_category") or "other"

    # Extract the original user message for better text-based ranking
    user_query = ""
    for msg in reversed(state.get("messages", [])):
        if hasattr(msg, "type") and msg.type == "human":
            user_query = msg.content
            break
    query = user_query or category

    async with async_session_factory() as db:
        svc = KnowledgeRetrievalService(db)
        result = await svc.search(
            query=query,
            category=category if category != "other" else None,
            is_employee_facing=True,
            limit=5,
        )

    articles = [_scored_to_dict(s) for s in result.items]
    citations = _build_citations(articles)

    audit_entry = {
        "event": "knowledge.searched",
        "category": category,
        "results_count": len(articles),
        "confidence": result.confidence,
        "source": result.source,
        "published_only": result.published_only,
        "fallback_used": result.fallback_used,
        "citations": [c["citation_label"] for c in citations],
    }

    logger.info(
        "retrieval_node_complete",
        results=len(articles),
        confidence=result.confidence,
        source=result.source,
    )

    return {
        "current_node": "retrieve",
        "knowledge_results": articles,
        "knowledge_confidence": result.confidence,
        "knowledge_citations": citations,
        "knowledge_published_only": result.published_only,
        "audit_trail": [audit_entry],
    }
