"""Knowledge Retrieval Agent Node — searches knowledge base for relevant articles."""

from app.core.logging import get_logger
from app.workflows.state import WorkflowState

logger = get_logger(__name__)


async def retrieval_node(state: WorkflowState) -> dict:
    """Search knowledge base for articles matching the classified issue.

    This node:
    1. Uses the issue category from triage
    2. Performs semantic search (pgvector) for relevant articles
    3. Ranks results by relevance
    4. Returns top matching articles with confidence
    """
    logger.info(
        "retrieval_node_start",
        session_id=state.get("session_id"),
        category=state.get("issue_category"),
    )

    category = state.get("issue_category", "other")

    # TODO(team): Replace with actual vector search via KnowledgeService
    # For now, use in-memory knowledge base lookup
    knowledge_results = await _search_knowledge(category)

    # Calculate confidence based on result quality
    confidence = 0.0
    if knowledge_results:
        confidence = min(0.95, 0.6 + (len(knowledge_results) * 0.1))

    audit_entry = {
        "event": "knowledge.searched",
        "category": category,
        "results_count": len(knowledge_results),
        "confidence": confidence,
    }

    return {
        "current_node": "retrieve",
        "knowledge_results": knowledge_results,
        "knowledge_confidence": confidence,
        "audit_trail": [audit_entry],
    }


async def _search_knowledge(category: str) -> list[dict]:
    """Search knowledge base by category.

    Production: uses pgvector semantic search.
    Fallback: category-based lookup from seeded knowledge.
    """
    # In-memory knowledge lookup for development
    from app.knowledge_base.loader import get_articles_by_category

    articles = get_articles_by_category(category)
    return [
        {
            "id": article.get("id", "unknown"),
            "title": article.get("title", ""),
            "content": article.get("content", ""),
            "steps": article.get("steps", []),
            "relevance_score": 0.85,
        }
        for article in articles
    ]
