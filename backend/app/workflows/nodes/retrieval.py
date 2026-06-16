"""Knowledge Retrieval Agent Node — context-aware targeted search.

Uses diagnostic context from triage to build focused retrieval queries
instead of broad category-based searches. Falls back to YAML seed when
the database has no published articles.
"""

from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.services.agents.diagnostic_state import DiagnosticContext
from app.services.agents.playbooks import get_playbook
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
    """Search knowledge base using focused queries from diagnostic context.

    This node:
    1. Builds a targeted query from diagnostic context (symptom + category)
    2. Applies category filters from the playbook
    3. Limits results to the most relevant (top-3 instead of top-5)
    4. Returns confidence scoring that reflects query specificity
    """
    logger.info(
        "retrieval_node_start",
        session_id=state.get("session_id"),
        category=state.get("issue_category"),
    )

    # Restore diagnostic context for targeted retrieval
    diag_ctx = DiagnosticContext.from_dict(state.get("diagnostic_context") or {})
    category = state.get("issue_category") or diag_ctx.issue_category or "other"

    # Build targeted query from accumulated diagnostic context
    query = _build_focused_query(diag_ctx, state)
    playbook = get_playbook(category)

    # Narrow the search: use playbook's max results (default 3)
    limit = playbook.max_retrieval_results if playbook else 3

    async with async_session_factory() as db:
        svc = KnowledgeRetrievalService(db)
        result = await svc.search(
            query=query,
            category=category if category != "other" else None,
            is_employee_facing=True,
            limit=limit,
        )

    articles = [_scored_to_dict(s) for s in result.items]
    citations = _build_citations(articles)

    # Adjust confidence based on query specificity
    confidence = result.confidence
    if diag_ctx.symptom or diag_ctx.exact_problem_statement:
        # Specific query → trust retrieval confidence more
        confidence = min(1.0, confidence * 1.1)
    else:
        # Broad query → penalize confidence
        confidence = confidence * 0.7

    audit_entry = {
        "event": "knowledge.searched",
        "category": category,
        "query": query[:200],
        "results_count": len(articles),
        "confidence": confidence,
        "source": result.source,
        "published_only": result.published_only,
        "fallback_used": result.fallback_used,
        "diagnostic_slots": list(diag_ctx.get_filled_slots().keys()),
    }

    logger.info(
        "retrieval_node_complete",
        results=len(articles),
        confidence=confidence,
        query_length=len(query),
    )

    return {
        "current_node": "retrieve",
        "knowledge_results": articles,
        "knowledge_confidence": confidence,
        "knowledge_citations": _build_citations(articles),
        "knowledge_published_only": result.published_only,
        "audit_trail": [audit_entry],
    }


def _build_focused_query(diag_ctx: DiagnosticContext, state: WorkflowState) -> str:
    """Build a focused retrieval query from diagnostic context.

    Priority order:
    1. Entity-specific: use normalized system + symptom for targeted search
    2. Exact problem statement (most specific)
    3. Symptom + category combination
    4. Subcategory + any error message
    5. Fall back to latest user message
    """
    # Best case: entity-specific query (e.g. "sixth sense login locked account")
    if diag_ctx.normalized_system:
        parts = [diag_ctx.normalized_system.replace("_", " ")]
        if diag_ctx.symptom:
            parts.append(diag_ctx.symptom.replace("-", " "))
        if diag_ctx.login_issue_flag:
            parts.append("login")
        if diag_ctx.blocked_account_flag == "yes":
            parts.append("account locked blocked")
        if diag_ctx.otp_issue_flag:
            parts.append("otp")
        if diag_ctx.unhandled_message_flag:
            parts.append("unhandled message")
        if diag_ctx.error_message and "unhandled" not in parts[-1]:
            parts.append(diag_ctx.error_message)
        if diag_ctx.exact_problem_statement:
            parts.append(diag_ctx.exact_problem_statement)
        return " ".join(parts)

    # Good case: specific problem statement
    if diag_ctx.exact_problem_statement:
        parts = [diag_ctx.exact_problem_statement]
        if diag_ctx.error_message:
            parts.append(diag_ctx.error_message)
        return " ".join(parts)

    # Okay case: categorized symptom
    if diag_ctx.symptom:
        parts = []
        if diag_ctx.issue_category:
            parts.append(diag_ctx.issue_category.replace("/", " "))
        parts.append(diag_ctx.symptom.replace("-", " "))
        if diag_ctx.error_message:
            parts.append(diag_ctx.error_message)
        if diag_ctx.affected_system:
            parts.append(diag_ctx.affected_system)
        return " ".join(parts)

    # Fallback: use the last user message with category prefix
    user_query = ""
    for msg in reversed(state.get("messages", [])):
        if hasattr(msg, "type") and msg.type == "human":
            user_query = msg.content
            break

    category = diag_ctx.issue_category or ""
    return f"{category} {user_query}".strip() or "IT support issue"
