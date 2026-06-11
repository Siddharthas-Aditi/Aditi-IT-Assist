"""Knowledge Retrieval Agent Node — searches knowledge base for relevant articles.

Retrieval is **governed**: the employee-facing chat agent is only ever grounded
in published, approved knowledge content. In this dev/runtime path the node uses
the keyword ``KnowledgeService`` (YAML-seeded); the production database path is
served by ``app.services.knowledge.retrieval.KnowledgeRetrievalService`` which
enforces published-only access at the query level and shares the same citation
shape produced here.
"""

from app.core.logging import get_logger
from app.services.knowledge_service import get_knowledge_service
from app.workflows.state import WorkflowState

logger = get_logger(__name__)


def _build_citations(articles: list[dict]) -> list[dict]:
    """Project retrieved articles into citation-ready source attributions."""
    citations: list[dict] = []
    for article in articles:
        title = article.get("title", "Knowledge Article")
        citations.append(
            {
                "article_id": article.get("id", "unknown"),
                "title": title,
                "citation_label": article.get("citation_label") or title,
                "category": article.get("category"),
            }
        )
    return citations


async def retrieval_node(state: WorkflowState) -> dict:
    """Search knowledge base for articles matching the classified issue.

    This node:
    1. Uses the issue category from triage
    2. Delegates to KnowledgeService for semantic/category search
    3. Returns ranked articles, citations, and a composite confidence score
    """
    logger.info(
        "retrieval_node_start",
        session_id=state.get("session_id"),
        category=state.get("issue_category"),
    )

    category = state.get("issue_category") or "other"

    knowledge_svc = get_knowledge_service()
    result = await knowledge_svc.retrieve_for_category(category)

    citations = _build_citations(result.articles)

    audit_entry = {
        "event": "knowledge.searched",
        "category": category,
        "results_count": len(result.articles),
        "confidence": result.confidence,
        "source": result.source,
        "published_only": True,
        "citations": [c["citation_label"] for c in citations],
    }

    return {
        "current_node": "retrieve",
        "knowledge_results": result.articles,
        "knowledge_confidence": result.confidence,
        "knowledge_citations": citations,
        "knowledge_published_only": True,
        "audit_trail": [audit_entry],
    }
