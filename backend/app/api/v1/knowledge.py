"""Knowledge base management endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


class KnowledgeArticleResponse(BaseModel):
    """Knowledge article response."""

    id: str
    title: str
    category: str
    subcategory: str | None = None
    content: str
    steps: list[dict] = []
    tags: list[str] = []


class KnowledgeSearchRequest(BaseModel):
    """Search request for knowledge base."""

    query: str = Field(..., min_length=3, max_length=1000)
    category: str | None = None
    limit: int = 5


class KnowledgeSearchResponse(BaseModel):
    """Search results from knowledge base."""

    results: list[KnowledgeArticleResponse]
    total: int
    query: str


@router.get("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    query: str,
    category: str | None = None,
    limit: int = 5,
) -> KnowledgeSearchResponse:
    """Search the knowledge base using semantic search.

    Uses pgvector for embedding similarity search with optional
    category filtering.
    """
    # TODO(team): Implement vector search via KnowledgeService
    return KnowledgeSearchResponse(
        results=[],
        total=0,
        query=query,
    )


@router.get("", response_model=list[KnowledgeArticleResponse])
async def list_articles(
    category: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[KnowledgeArticleResponse]:
    """List knowledge articles with optional filtering."""
    # TODO(team): Implement with database query
    return []


@router.get("/{article_id}", response_model=KnowledgeArticleResponse)
async def get_article(article_id: str) -> KnowledgeArticleResponse:
    """Get a specific knowledge article by ID."""
    # TODO(team): Implement with database query
    return KnowledgeArticleResponse(
        id=article_id,
        title="Placeholder",
        category="other",
        content="Article content not found",
    )
