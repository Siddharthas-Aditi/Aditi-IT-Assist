"""Knowledge base models — enterprise knowledge management.

Implements a governed, retrieval-aware, versioned, and auditable knowledge
article model alongside the normalized tables that support it:

- ``KnowledgeArticle``        — rich, structured support article (the aggregate root)
- ``KnowledgeArticleVersion`` — immutable version snapshots for history/restore
- ``KnowledgeChunk``          — retrieval chunks prepared for the RAG pipeline
- ``KnowledgeTaxonomyTerm``   — admin-managed taxonomy (categories, products, …)
- ``KnowledgeOwnershipGroup`` — ownership/stewardship groups for governance
- ``KnowledgeFeedback``       — end-user / agent feedback on article usefulness
- ``KnowledgeReviewNote``     — review-queue decisions and reviewer notes

Several legacy columns (``content``, ``steps``, ``is_published`` …) are retained
for backwards compatibility with the original article model and the YAML-seeded
retrieval fallback; new authoring flows use the structured fields.
"""

from __future__ import annotations

# NOTE: ``uuid`` must be imported at runtime (not under TYPE_CHECKING) because
# SQLAlchemy resolves ``Mapped[uuid.UUID]`` annotations during mapper config.
import uuid  # noqa: TC003
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# ─────────────────────────────────────────────────────────────────────
# Enumerations (kept as module-level tuples, mirroring ticket.py style)
# ─────────────────────────────────────────────────────────────────────

ARTICLE_STATUSES = ("draft", "in_review", "approved", "published", "archived")
ARTICLE_TYPES = (
    "troubleshooting",
    "how_to",
    "faq",
    "known_error",
    "policy",
    "reference",
)
# Where, and to whom, an article may surface.
AUDIENCE_TYPES = ("employee", "it_staff", "admin")
VISIBILITY_SCOPES = ("public_internal", "it_only", "admin_only")
EMBEDDING_STATUSES = ("not_indexed", "pending", "indexed", "stale", "failed")
TAXONOMY_TYPES = (
    "category",
    "subcategory",
    "product",
    "platform",
    "issue_type",
    "audience",
    "tag",
)
REVIEW_DECISIONS = ("comment", "approved", "rejected", "changes_requested")


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ─────────────────────────────────────────────────────────────────────
# Ownership groups (governance / stewardship)
# ─────────────────────────────────────────────────────────────────────


class KnowledgeOwnershipGroup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A team that owns and maintains a set of knowledge articles."""

    __tablename__ = "knowledge_ownership_groups"

    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    default_reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    member_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    articles: Mapped[list[KnowledgeArticle]] = relationship(back_populates="ownership_group")


# ─────────────────────────────────────────────────────────────────────
# Taxonomy (admin-managed classification vocabulary)
# ─────────────────────────────────────────────────────────────────────


class KnowledgeTaxonomyTerm(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single admin-managed taxonomy value (category, product, tag, …)."""

    __tablename__ = "knowledge_taxonomy_terms"
    __table_args__ = (UniqueConstraint("term_type", "key", name="uq_taxonomy_type_key"),)

    term_type: Mapped[str] = mapped_column(
        Enum(*TAXONOMY_TYPES, name="knowledge_taxonomy_type"), index=True
    )
    key: Mapped[str] = mapped_column(String(120), index=True)
    label: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_taxonomy_terms.id"), nullable=True
    )
    # Aligns KB classification with the ticket taxonomy where practical.
    ticket_category_mapping: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# ─────────────────────────────────────────────────────────────────────
# Knowledge Article (aggregate root)
# ─────────────────────────────────────────────────────────────────────


class KnowledgeArticle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Structured, governed knowledge article optimized for AI retrieval."""

    __tablename__ = "knowledge_articles"

    # ── Core ────────────────────────────────────────────────────
    slug: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    short_summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    article_type: Mapped[str] = mapped_column(
        Enum(*ARTICLE_TYPES, name="knowledge_article_type"), default="troubleshooting"
    )
    status: Mapped[str] = mapped_column(
        Enum(*ARTICLE_STATUSES, name="knowledge_article_status"),
        default="draft",
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    language: Mapped[str] = mapped_column(String(10), default="en")
    audience: Mapped[str] = mapped_column(
        Enum(*AUDIENCE_TYPES, name="knowledge_audience"), default="employee"
    )
    visibility_scope: Mapped[str] = mapped_column(
        Enum(*VISIBILITY_SCOPES, name="knowledge_visibility_scope"),
        default="public_internal",
    )

    # ── Domain / classification ─────────────────────────────────
    category: Mapped[str] = mapped_column(String(100), index=True)
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    product_or_system: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    platform: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    issue_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    severity_hint: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    keywords: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    ownership_group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_ownership_groups.id"),
        nullable=True,
        index=True,
    )

    # ── Support-specific structure ──────────────────────────────
    # Long-form body retained for legacy/compat and free-text context.
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    symptoms: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    probable_causes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    prerequisites: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    troubleshooting_steps: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    resolution_steps: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    validation_steps: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    escalation_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_target_team: Mapped[str | None] = mapped_column(String(120), nullable=True)
    references: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    attachments: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    related_articles: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Legacy alias retained so old seed data / callers keep working.
    steps: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # ── Governance ──────────────────────────────────────────────
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approver_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # Legacy approval flags (derived from status; kept for compat).
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_review_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    confidence_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── AI / retrieval ──────────────────────────────────────────
    retrieval_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunking_strategy: Mapped[str] = mapped_column(String(40), default="semantic_sections")
    citation_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    embedding_status: Mapped[str] = mapped_column(
        Enum(*EMBEDDING_STATUSES, name="knowledge_embedding_status"),
        default="not_indexed",
        index=True,
    )
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    index_version: Mapped[int] = mapped_column(Integer, default=0)

    # ── Analytics ───────────────────────────────────────────────
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    successful_resolution_count: Mapped[int] = mapped_column(Integer, default=0)
    feedback_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    negative_feedback_count: Mapped[int] = mapped_column(Integer, default=0)
    helpfulness_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Relationships ───────────────────────────────────────────
    ownership_group: Mapped[KnowledgeOwnershipGroup | None] = relationship(
        back_populates="articles", lazy="selectin"
    )
    versions: Mapped[list[KnowledgeArticleVersion]] = relationship(
        back_populates="article",
        order_by="KnowledgeArticleVersion.version.desc()",
        cascade="all, delete-orphan",
    )
    chunks: Mapped[list[KnowledgeChunk]] = relationship(
        back_populates="article",
        order_by="KnowledgeChunk.chunk_index",
        cascade="all, delete-orphan",
    )
    feedback: Mapped[list[KnowledgeFeedback]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )
    review_notes: Mapped[list[KnowledgeReviewNote]] = relationship(
        back_populates="article",
        order_by="KnowledgeReviewNote.created_at",
        cascade="all, delete-orphan",
    )


# ─────────────────────────────────────────────────────────────────────
# Version snapshots
# ─────────────────────────────────────────────────────────────────────


class KnowledgeArticleVersion(UUIDPrimaryKeyMixin, Base):
    """Immutable snapshot of an article at a point in its lifecycle."""

    __tablename__ = "knowledge_article_versions"
    __table_args__ = (UniqueConstraint("article_id", "version", name="uq_article_version"),)

    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_articles.id"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20))
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot: Mapped[dict] = mapped_column(JSONB)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    article: Mapped[KnowledgeArticle] = relationship(back_populates="versions")


# ─────────────────────────────────────────────────────────────────────
# Retrieval chunks
# ─────────────────────────────────────────────────────────────────────


class KnowledgeChunk(UUIDPrimaryKeyMixin, Base):
    """A retrieval-ready chunk derived from an article's semantic sections."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (UniqueConstraint("article_id", "chunk_index", name="uq_article_chunk_index"),)

    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_articles.id"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(80))
    # Contextual header prepended to the chunk to improve retrieval grounding.
    header: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    embedding_status: Mapped[str] = mapped_column(
        Enum(*EMBEDDING_STATUSES, name="knowledge_chunk_embedding_status"),
        default="not_indexed",
    )
    index_version: Mapped[int] = mapped_column(Integer, default=0)
    # Actual embedding vector stored in pgvector (nullable until indexed).
    embedding: Mapped[list[float] | None] = mapped_column(Vector(3072), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    article: Mapped[KnowledgeArticle] = relationship(back_populates="chunks")


# ─────────────────────────────────────────────────────────────────────
# Feedback
# ─────────────────────────────────────────────────────────────────────


class KnowledgeFeedback(UUIDPrimaryKeyMixin, Base):
    """Feedback on an article's usefulness, from chat, the portal, or tickets."""

    __tablename__ = "knowledge_feedback"

    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_articles.id"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    was_helpful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="portal")
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    resolved_issue: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )

    article: Mapped[KnowledgeArticle] = relationship(back_populates="feedback")


# ─────────────────────────────────────────────────────────────────────
# Review notes (review queue / approval workflow)
# ─────────────────────────────────────────────────────────────────────


class KnowledgeReviewNote(UUIDPrimaryKeyMixin, Base):
    """A reviewer decision/comment captured during the review workflow."""

    __tablename__ = "knowledge_review_notes"

    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_articles.id"), index=True
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    decision: Mapped[str] = mapped_column(
        Enum(*REVIEW_DECISIONS, name="knowledge_review_decision"), default="comment"
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    article: Mapped[KnowledgeArticle] = relationship(back_populates="review_notes")
