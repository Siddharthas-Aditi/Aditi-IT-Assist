"""Knowledge-related schemas."""

from pydantic import BaseModel, Field


class KnowledgeArticleSchema(BaseModel):
    """Knowledge article response schema."""

    id: str
    title: str
    category: str
    subcategory: str | None = None
    content: str
    steps: list[dict] = []
    tags: list[str] = []


class KnowledgeSearchRequest(BaseModel):
    """Search query for the knowledge base."""

    query: str = Field(..., min_length=3, max_length=1000)
    category: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


class KnowledgeSearchResponse(BaseModel):
    """Search results from the knowledge base."""

    results: list[KnowledgeArticleSchema]
    total: int
    query: str
