"""Knowledge base management endpoints."""

from fastapi import APIRouter, Depends

from app.schemas.knowledge import (
    KnowledgeArticleSchema,
    KnowledgeSearchResponse,
)
from app.services.knowledge_service import KnowledgeService, get_knowledge_service

router = APIRouter()


@router.get("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    query: str,
    category: str | None = None,
    limit: int = 5,
    service: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> KnowledgeSearchResponse:
    """Search the knowledge base using semantic search.

    Uses pgvector for embedding similarity search with optional
    category filtering.
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

    return KnowledgeSearchResponse(
        results=articles,
        total=len(articles),
        query=query,
    )


@router.get("", response_model=list[KnowledgeArticleSchema])
async def list_articles(
    category: str | None = None,
    limit: int = 20,
    offset: int = 0,
    service: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> list[KnowledgeArticleSchema]:
    """List knowledge articles with optional filtering."""
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


@router.get("/{article_id}", response_model=KnowledgeArticleSchema)
async def get_article(article_id: str) -> KnowledgeArticleSchema:
    """Get a specific knowledge article by ID."""
    # TODO(team): Implement with database query by ID
    return KnowledgeArticleSchema(
        id=article_id,
        title="Placeholder",
        category="other",
        content="Article content not found",
    )
