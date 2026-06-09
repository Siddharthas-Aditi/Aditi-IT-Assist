"""Knowledge Retrieval Agent Node — searches knowledge base for relevant articles."""

from app.core.logging import get_logger
from app.services.knowledge_service import get_knowledge_service
from app.workflows.state import WorkflowState

logger = get_logger(__name__)


async def retrieval_node(state: WorkflowState) -> dict:
    """Search knowledge base for articles matching the classified issue.

    This node:
    1. Uses the issue category from triage
    2. Delegates to KnowledgeService for semantic/category search
    3. Returns ranked articles with a composite confidence score
    """
    logger.info(
        "retrieval_node_start",
        session_id=state.get("session_id"),
        category=state.get("issue_category"),
    )

    category = state.get("issue_category") or "other"

    knowledge_svc = get_knowledge_service()
    result = await knowledge_svc.retrieve_for_category(category)

    audit_entry = {
        "event": "knowledge.searched",
        "category": category,
        "results_count": len(result.articles),
        "confidence": result.confidence,
        "source": result.source,
    }

    return {
        "current_node": "retrieve",
        "knowledge_results": result.articles,
        "knowledge_confidence": result.confidence,
        "audit_trail": [audit_entry],
    }
