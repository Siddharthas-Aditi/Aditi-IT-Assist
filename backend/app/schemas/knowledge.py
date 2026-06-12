"""Knowledge-management schemas (Pydantic v2).

Grouped into:
- Legacy retrieval schemas (kept for the existing public search/list endpoints)
- Authoring schemas (create/update/detail)
- Lifecycle / review / feedback
- Taxonomy & ownership
- Versions, indexing, retrieval preview, analytics, citations
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ─────────────────────────────────────────────────────────────────────
# Legacy retrieval schemas (unchanged public contract)
# ─────────────────────────────────────────────────────────────────────


class KnowledgeArticleSchema(BaseModel):
    """Knowledge article response schema (legacy/public shape)."""

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


# ─────────────────────────────────────────────────────────────────────
# Structured authoring schemas
# ─────────────────────────────────────────────────────────────────────

ArticleStatus = Literal["draft", "in_review", "approved", "published", "archived"]
ArticleType = Literal["troubleshooting", "how_to", "faq", "known_error", "policy", "reference"]
Audience = Literal["employee", "it_staff", "admin"]
VisibilityScope = Literal["public_internal", "it_only", "admin_only"]


class StepSchema(BaseModel):
    """A single ordered troubleshooting/resolution step."""

    step_number: int = Field(..., ge=1)
    instruction: str = Field(..., min_length=1)
    details: str | None = None


class ArticleWriteBase(BaseModel):
    """Shared authoring fields for create/update."""

    title: str = Field(..., min_length=3, max_length=500)
    short_summary: str | None = Field(None, max_length=1000)
    article_type: ArticleType = "troubleshooting"
    language: str = "en"
    audience: Audience = "employee"
    visibility_scope: VisibilityScope = "public_internal"

    category: str = Field(..., min_length=1, max_length=100)
    subcategory: str | None = None
    product_or_system: str | None = None
    platform: str | None = None
    issue_type: str | None = None
    severity_hint: str | None = None
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    ownership_group_id: str | None = None

    content: str | None = None
    symptoms: list[str] = Field(default_factory=list)
    probable_causes: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    troubleshooting_steps: list[StepSchema] = Field(default_factory=list)
    resolution_steps: list[StepSchema] = Field(default_factory=list)
    validation_steps: list[StepSchema] = Field(default_factory=list)
    escalation_criteria: str | None = None
    escalation_target_team: str | None = None
    references: list[dict[str, Any]] = Field(default_factory=list)
    related_articles: list[str] = Field(default_factory=list)

    citation_label: str | None = None
    source_type: str | None = None
    source_reference: str | None = None
    review_interval_days: int | None = Field(default=180, ge=1, le=1095)


class ArticleCreate(ArticleWriteBase):
    """Payload to create a draft article."""


class ArticleUpdate(BaseModel):
    """Partial update payload — all fields optional."""

    title: str | None = Field(None, min_length=3, max_length=500)
    short_summary: str | None = None
    article_type: ArticleType | None = None
    language: str | None = None
    audience: Audience | None = None
    visibility_scope: VisibilityScope | None = None
    category: str | None = None
    subcategory: str | None = None
    product_or_system: str | None = None
    platform: str | None = None
    issue_type: str | None = None
    severity_hint: str | None = None
    tags: list[str] | None = None
    keywords: list[str] | None = None
    ownership_group_id: str | None = None
    content: str | None = None
    symptoms: list[str] | None = None
    probable_causes: list[str] | None = None
    prerequisites: list[str] | None = None
    troubleshooting_steps: list[StepSchema] | None = None
    resolution_steps: list[StepSchema] | None = None
    validation_steps: list[StepSchema] | None = None
    escalation_criteria: str | None = None
    escalation_target_team: str | None = None
    references: list[dict[str, Any]] | None = None
    related_articles: list[str] | None = None
    citation_label: str | None = None
    source_type: str | None = None
    source_reference: str | None = None
    change_summary: str | None = None


class ArticleSummary(BaseModel):
    """Lightweight article representation for list views."""

    id: str
    slug: str | None = None
    title: str
    short_summary: str | None = None
    status: ArticleStatus
    article_type: ArticleType
    category: str
    subcategory: str | None = None
    product_or_system: str | None = None
    platform: str | None = None
    audience: Audience
    version: int
    tags: list[str] = []
    ownership_group_id: str | None = None
    embedding_status: str
    quality_score: float | None = None
    view_count: int = 0
    usage_count: int = 0
    feedback_score: float | None = None
    next_review_due_at: str | None = None
    is_stale: bool = False
    updated_at: str | None = None


class ArticleDetail(ArticleSummary):
    """Full article representation for detail / editor views."""

    content: str | None = None
    keywords: list[str] = []
    issue_type: str | None = None
    severity_hint: str | None = None
    visibility_scope: VisibilityScope
    symptoms: list[str] = []
    probable_causes: list[str] = []
    prerequisites: list[str] = []
    troubleshooting_steps: list[dict[str, Any]] = []
    resolution_steps: list[dict[str, Any]] = []
    validation_steps: list[dict[str, Any]] = []
    escalation_criteria: str | None = None
    escalation_target_team: str | None = None
    references: list[dict[str, Any]] = []
    related_articles: list[str] = []
    citation_label: str | None = None
    source_type: str | None = None
    source_reference: str | None = None
    author_id: str | None = None
    reviewer_id: str | None = None
    approver_id: str | None = None
    confidence_level: float | None = None
    last_reviewed_at: str | None = None
    published_at: str | None = None
    archived_at: str | None = None
    indexed_at: str | None = None
    index_version: int = 0
    successful_resolution_count: int = 0
    negative_feedback_count: int = 0
    available_actions: list[str] = []
    created_at: str | None = None


class ArticleListResponse(BaseModel):
    articles: list[ArticleSummary]
    total: int
    limit: int
    offset: int


# ─────────────────────────────────────────────────────────────────────
# Lifecycle / review / feedback
# ─────────────────────────────────────────────────────────────────────


class LifecycleTransitionRequest(BaseModel):
    """Request to move an article through its lifecycle."""

    action: Literal[
        "submit_for_review",
        "approve",
        "request_changes",
        "reject",
        "publish",
        "archive",
        "restore",
        "create_revision",
    ]
    note: str | None = None
    change_summary: str | None = None


class ReviewNoteCreate(BaseModel):
    decision: Literal["comment", "approved", "rejected", "changes_requested"] = "comment"
    note: str = Field(..., min_length=1, max_length=5000)


class ReviewNoteSchema(BaseModel):
    id: str
    reviewer_id: str | None = None
    decision: str
    note: str | None = None
    from_status: str | None = None
    to_status: str | None = None
    created_at: str


class FeedbackCreate(BaseModel):
    rating: int | None = Field(None, ge=1, le=5)
    was_helpful: bool | None = None
    comment: str | None = Field(None, max_length=2000)
    source: Literal["portal", "chat", "ticket"] = "portal"
    resolved_issue: bool | None = None
    session_id: str | None = None


class FeedbackSchema(BaseModel):
    id: str
    article_id: str
    rating: int | None = None
    was_helpful: bool | None = None
    comment: str | None = None
    source: str
    created_at: str


# ─────────────────────────────────────────────────────────────────────
# Taxonomy & ownership
# ─────────────────────────────────────────────────────────────────────

TaxonomyType = Literal[
    "category", "subcategory", "product", "platform", "issue_type", "audience", "tag"
]


class TaxonomyTermCreate(BaseModel):
    term_type: TaxonomyType
    key: str = Field(..., min_length=1, max_length=120)
    label: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    parent_id: str | None = None
    ticket_category_mapping: str | None = None
    sort_order: int = 0


class TaxonomyTermUpdate(BaseModel):
    label: str | None = None
    description: str | None = None
    parent_id: str | None = None
    ticket_category_mapping: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class TaxonomyTermSchema(BaseModel):
    id: str
    term_type: str
    key: str
    label: str
    description: str | None = None
    parent_id: str | None = None
    ticket_category_mapping: str | None = None
    sort_order: int = 0
    is_active: bool = True


class OwnershipGroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    owner_id: str | None = None
    default_reviewer_id: str | None = None
    member_ids: list[str] = Field(default_factory=list)


class OwnershipGroupSchema(BaseModel):
    id: str
    name: str
    display_name: str
    description: str | None = None
    owner_id: str | None = None
    default_reviewer_id: str | None = None
    member_ids: list[str] = []
    is_active: bool = True


# ─────────────────────────────────────────────────────────────────────
# Versions, indexing, retrieval preview, analytics, citations
# ─────────────────────────────────────────────────────────────────────


class VersionSchema(BaseModel):
    id: str
    version: int
    title: str
    status: str
    change_summary: str | None = None
    author_id: str | None = None
    created_at: str


class VersionDetailSchema(VersionSchema):
    snapshot: dict[str, Any]


class ChunkSchema(BaseModel):
    chunk_index: int
    section: str
    header: str
    content: str
    token_estimate: int
    embedding_status: str


class RetrievalPreviewResponse(BaseModel):
    """How an article will be presented to the retrieval pipeline."""

    article_id: str
    citation_label: str
    chunking_strategy: str
    retrieval_text: str
    chunks: list[ChunkSchema]
    total_tokens: int
    warnings: list[str] = []


class ReindexRequest(BaseModel):
    article_ids: list[str] | None = None
    only_stale: bool = False


class IndexingStatusResponse(BaseModel):
    total_articles: int
    published_articles: int
    indexed_articles: int
    pending_articles: int
    stale_articles: int
    failed_articles: int
    total_chunks: int
    index_version: int
    last_indexed_at: str | None = None
    vector_store: str


class ReindexResult(BaseModel):
    requested: int
    reindexed: int
    chunks_written: int
    skipped: int
    errors: list[str] = []


class ArticleAnalyticsSchema(BaseModel):
    article_id: str
    title: str
    status: str
    view_count: int
    usage_count: int
    successful_resolution_count: int
    feedback_score: float | None = None
    negative_feedback_count: int
    resolution_rate: float | None = None
    quality_score: float | None = None
    is_stale: bool = False


class KnowledgeAnalyticsSummary(BaseModel):
    total_articles: int
    by_status: dict[str, int]
    published_articles: int
    stale_articles: int
    avg_quality_score: float | None = None
    total_views: int
    total_usage: int
    avg_resolution_rate: float | None = None
    top_articles: list[ArticleAnalyticsSchema]
    low_performers: list[ArticleAnalyticsSchema]


class CitationSchema(BaseModel):
    """A source attribution returned with grounded AI answers."""

    article_id: str
    title: str
    citation_label: str
    slug: str | None = None
    category: str | None = None
    snippet: str | None = None
    score: float | None = None


class RetrievalResultItem(BaseModel):
    article_id: str
    title: str
    category: str
    citation_label: str
    snippet: str
    score: float


class RetrievalResponse(BaseModel):
    results: list[RetrievalResultItem]
    citations: list[CitationSchema]
    confidence: float
    source: str
    published_only: bool
    low_confidence: bool


# ─────────────────────────────────────────────────────────────────────
# Quality, completeness, staleness, templates
# ─────────────────────────────────────────────────────────────────────


class DimensionScoreSchema(BaseModel):
    name: str
    label: str
    score: float
    earned: list[str] = []
    missing: list[str] = []


class CompletenessReportSchema(BaseModel):
    """Multi-dimension completeness report for the article editor."""

    score: float                    # 0 – 100
    grade: str                      # A / B / C / D / F
    dimensions: list[DimensionScoreSchema]
    ready_for_review: bool
    ready_for_publish: bool
    blocking_issues: list[str]      # hard blockers preventing publication
    suggestions: list[str]          # non-blocking improvements


class AuthorWarningSchema(BaseModel):
    """Inline warning item shown in the article editor."""

    severity: str           # "error" | "warning" | "info"
    field: str | None = None
    message: str
    guidance: str | None = None


class StaleAnalysisSchema(BaseModel):
    """Detailed staleness analysis for an article."""

    is_stale: bool
    staleness_score: float          # 0.0 (fresh) – 1.0 (very stale)
    days_since_update: int | None = None
    days_overdue: int | None = None
    reasons: list[str]
    recommendations: list[str]


class ArticleTemplateSchema(BaseModel):
    """A pre-filled article scaffold shown in the template picker."""

    key: str
    label: str
    category: str
    subcategory: str
    product_or_system: str
    description: str
    icon: str


class DuplicateHintSchema(BaseModel):
    """A lightweight hint returned when a similar article title is detected."""

    id: str
    title: str
    status: str

