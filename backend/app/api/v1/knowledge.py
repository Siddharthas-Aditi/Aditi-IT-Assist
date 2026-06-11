"""Public / user-facing knowledge endpoints.

These endpoints serve *consumers* of the knowledge base:
- the legacy keyword search/list/get (unauthenticated public contract, retained),
- governed retrieval for the chat agent (authenticated, **published-only**),
- article feedback submission.

Admin authoring & governance lives in ``knowledge_admin.py``.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import P
from app.models.auth import User
from app.schemas.knowledge import (
    CitationSchema,
    FeedbackCreate,
    FeedbackSchema,
    KnowledgeArticleSchema,
    KnowledgeSearchResponse,
    RetrievalResponse,
    RetrievalResultItem,
)
from app.services.auth.dependencies import CurrentUser, require_permissions
from app.services.knowledge.management import KnowledgeManagementError, KnowledgeManagementService
from app.services.knowledge.retrieval import KnowledgeRetrievalService
from app.services.knowledge.serializers import feedback_to_dict
from app.services.knowledge_service import KnowledgeService, get_knowledge_service

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# Legacy public read endpoints (unauthenticated; backed by YAML fallback)
# ─────────────────────────────────────────────────────────────────────


@router.get("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    query: str,
    category: str | None = None,
    limit: int = 5,
    service: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> KnowledgeSearchResponse:
    """Search the knowledge base (keyword/semantic).

    Public, lightweight lookup used by tooling and the help portal. The
    governed, published-only retrieval used by the AI agent is ``/retrieve``.
    """
    result = await service.search(query, category=category, limit=limit)
    articles = [
        KnowledgeArticleSchema(
            id=a.get("id", "unknown"),
            title=a.get("title", ""),
            category=a.get("category", category or "other"),
            content=a.get("content", ""),
            steps=a.get("steps", []),
            tags=a.get("tags", []),
        )
        for a in result.articles
    ]
    return KnowledgeSearchResponse(results=articles, total=len(articles), query=query)


@router.get("", response_model=list[KnowledgeArticleSchema])
async def list_articles(
    category: str | None = None,
    limit: int = 20,
    offset: int = 0,
    service: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> list[KnowledgeArticleSchema]:
    """List knowledge articles with optional filtering (public read)."""
    if category:
        result = await service.retrieve_for_category(category)
        articles = result.articles
    else:
        articles = []
        for cat in service.categories:
            result = await service.retrieve_for_category(cat)
            articles.extend(result.articles)

    sliced = articles[offset : offset + limit]
    return [
        KnowledgeArticleSchema(
            id=a.get("id", "unknown"),
            title=a.get("title", ""),
            category=a.get("category", category or "other"),
            content=a.get("content", ""),
            steps=a.get("steps", []),
            tags=a.get("tags", []),
        )
        for a in sliced
    ]


# ─────────────────────────────────────────────────────────────────────
# Governed retrieval for the chat agent (authenticated, published-only)
# ─────────────────────────────────────────────────────────────────────


@router.get("/retrieve", response_model=RetrievalResponse)
async def retrieve_knowledge(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    query: str,
    category: str | None = None,
    product_or_system: str | None = None,
    platform: str | None = None,
    limit: int = 5,
) -> RetrievalResponse:
    """Governed retrieval for grounded answers.

    Employees retrieve **only published** content. IT staff with the
    ``knowledge:view_internal`` permission can opt into a broader scope. The
    response carries citation-ready snippets and a ``low_confidence`` flag the
    orchestrator may use to escalate.
    """
    from app.services.auth.service import AuthService

    permissions = await AuthService(db).get_user_permissions(current_user)
    is_employee = "employee" in set(current_user.role_names) and not any(
        r in {"it_agent", "it_lead", "it_admin"} for r in current_user.role_names
    )
    can_view_internal = P.KNOWLEDGE_VIEW_INTERNAL in permissions

    service = KnowledgeRetrievalService(db)
    result = await service.search(
        query,
        category=category,
        product_or_system=product_or_system,
        platform=platform,
        is_employee_facing=is_employee,
        can_view_internal=can_view_internal,
        limit=limit,
    )

    items = [
        RetrievalResultItem(
            article_id=str(s.article.id),
            title=s.article.title,
            category=getattr(s.article, "category", "") or "",
            citation_label=getattr(s.article, "citation_label", None) or s.article.title,
            snippet=s.snippet,
            score=s.score,
        )
        for s in result.items
    ]
    citations = [
        CitationSchema(
            article_id=str(s.article.id),
            title=s.article.title,
            citation_label=getattr(s.article, "citation_label", None) or s.article.title,
            slug=getattr(s.article, "slug", None),
            category=getattr(s.article, "category", None),
            snippet=s.snippet,
            score=s.score,
        )
        for s in result.items
    ]
    return RetrievalResponse(
        results=items,
        citations=citations,
        confidence=result.confidence,
        source=result.source,
        published_only=result.published_only,
        low_confidence=result.low_confidence,
    )


# ─────────────────────────────────────────────────────────────────────
# Feedback (authenticated)
# ─────────────────────────────────────────────────────────────────────


@router.post("/{article_id}/feedback", response_model=FeedbackSchema, status_code=201)
async def submit_feedback(
    article_id: str,
    data: FeedbackCreate,
    current_user: Annotated[User, Depends(require_permissions(P.KNOWLEDGE_SUBMIT_FEEDBACK))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FeedbackSchema:
    """Submit feedback on a published knowledge article."""
    service = KnowledgeManagementService(db)
    try:
        feedback = await service.submit_feedback(
            uuid.UUID(article_id),
            current_user,
            rating=data.rating,
            was_helpful=data.was_helpful,
            comment=data.comment,
            source=data.source,
            resolved_issue=data.resolved_issue,
            session_id=uuid.UUID(data.session_id) if data.session_id else None,
        )
    except KnowledgeManagementError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return FeedbackSchema(**feedback_to_dict(feedback))
