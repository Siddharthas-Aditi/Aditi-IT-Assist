"""Enterprise knowledge management schema.

Revision ID: 003_knowledge_management
Revises: 002_enterprise_upgrade
Create Date: 2026-06-11

Adds the governed, retrieval-aware knowledge model:
- ownership groups + taxonomy (admin-managed classification)
- the structured knowledge article (rich fields, governance, retrieval, analytics)
- version snapshots, retrieval chunks, feedback, and review notes

Note: in development the app auto-creates tables from SQLAlchemy metadata
(see ``app/main.py`` lifespan). This migration keeps production/CI consistent.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "003_knowledge_management"
down_revision = "002_enterprise_upgrade"
branch_labels = None
depends_on = None


ARTICLE_STATUSES = ("draft", "in_review", "approved", "published", "archived")
ARTICLE_TYPES = ("troubleshooting", "how_to", "faq", "known_error", "policy", "reference")
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


def _uuid():
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    # ── Ownership groups ─────────────────────────────────────────
    op.create_table(
        "knowledge_ownership_groups",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, index=True, nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("owner_id", _uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("default_reviewer_id", _uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("member_ids", postgresql.JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── Taxonomy ─────────────────────────────────────────────────
    op.create_table(
        "knowledge_taxonomy_terms",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "term_type",
            sa.Enum(*TAXONOMY_TYPES, name="knowledge_taxonomy_type"),
            index=True,
            nullable=False,
        ),
        sa.Column("key", sa.String(120), index=True, nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "parent_id", _uuid(), sa.ForeignKey("knowledge_taxonomy_terms.id"), nullable=True
        ),
        sa.Column("ticket_category_mapping", sa.String(100), nullable=True),
        sa.Column("sort_order", sa.Integer, server_default="0"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("term_type", "key", name="uq_taxonomy_type_key"),
    )

    # ── Articles ─────────────────────────────────────────────────
    op.create_table(
        "knowledge_articles",
        sa.Column("id", _uuid(), primary_key=True),
        # Core
        sa.Column("slug", sa.String(255), unique=True, index=True, nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("short_summary", sa.String(1000), nullable=True),
        sa.Column(
            "article_type",
            sa.Enum(*ARTICLE_TYPES, name="knowledge_article_type"),
            server_default="troubleshooting",
        ),
        sa.Column(
            "status",
            sa.Enum(*ARTICLE_STATUSES, name="knowledge_article_status"),
            server_default="draft",
            index=True,
        ),
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("language", sa.String(10), server_default="en"),
        sa.Column(
            "audience",
            sa.Enum(*AUDIENCE_TYPES, name="knowledge_audience"),
            server_default="employee",
        ),
        sa.Column(
            "visibility_scope",
            sa.Enum(*VISIBILITY_SCOPES, name="knowledge_visibility_scope"),
            server_default="public_internal",
        ),
        # Domain
        sa.Column("category", sa.String(100), index=True, nullable=False),
        sa.Column("subcategory", sa.String(100), index=True, nullable=True),
        sa.Column("product_or_system", sa.String(120), index=True, nullable=True),
        sa.Column("platform", sa.String(120), index=True, nullable=True),
        sa.Column("issue_type", sa.String(120), nullable=True),
        sa.Column("severity_hint", sa.String(20), nullable=True),
        sa.Column("tags", postgresql.JSONB, nullable=True),
        sa.Column("keywords", postgresql.JSONB, nullable=True),
        sa.Column(
            "ownership_group_id",
            _uuid(),
            sa.ForeignKey("knowledge_ownership_groups.id"),
            index=True,
            nullable=True,
        ),
        # Structure
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("symptoms", postgresql.JSONB, nullable=True),
        sa.Column("probable_causes", postgresql.JSONB, nullable=True),
        sa.Column("prerequisites", postgresql.JSONB, nullable=True),
        sa.Column("troubleshooting_steps", postgresql.JSONB, nullable=True),
        sa.Column("resolution_steps", postgresql.JSONB, nullable=True),
        sa.Column("validation_steps", postgresql.JSONB, nullable=True),
        sa.Column("escalation_criteria", sa.Text, nullable=True),
        sa.Column("escalation_target_team", sa.String(120), nullable=True),
        sa.Column("references", postgresql.JSONB, nullable=True),
        sa.Column("attachments", postgresql.JSONB, nullable=True),
        sa.Column("related_articles", postgresql.JSONB, nullable=True),
        sa.Column("steps", postgresql.JSONB, nullable=True),
        # Governance
        sa.Column("author_id", _uuid(), sa.ForeignKey("users.id"), index=True, nullable=True),
        sa.Column("reviewer_id", _uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approver_id", _uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("is_published", sa.Boolean, server_default="false"),
        sa.Column("is_approved", sa.Boolean, server_default="false"),
        sa.Column("approved_by", _uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_review_due_at", sa.DateTime(timezone=True), index=True, nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_type", sa.String(50), nullable=True),
        sa.Column("source_reference", sa.String(500), nullable=True),
        sa.Column("confidence_level", sa.Float, nullable=True),
        sa.Column("quality_score", sa.Float, nullable=True),
        # Retrieval
        sa.Column("retrieval_text", sa.Text, nullable=True),
        sa.Column("chunking_strategy", sa.String(40), server_default="semantic_sections"),
        sa.Column("citation_label", sa.String(255), nullable=True),
        sa.Column(
            "embedding_status",
            sa.Enum(*EMBEDDING_STATUSES, name="knowledge_embedding_status"),
            server_default="not_indexed",
            index=True,
        ),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("index_version", sa.Integer, server_default="0"),
        # Analytics
        sa.Column("view_count", sa.Integer, server_default="0"),
        sa.Column("usage_count", sa.Integer, server_default="0"),
        sa.Column("successful_resolution_count", sa.Integer, server_default="0"),
        sa.Column("feedback_score", sa.Float, nullable=True),
        sa.Column("negative_feedback_count", sa.Integer, server_default="0"),
        sa.Column("helpfulness_score", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── Version snapshots ────────────────────────────────────────
    op.create_table(
        "knowledge_article_versions",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "article_id",
            _uuid(),
            sa.ForeignKey("knowledge_articles.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("change_summary", sa.Text, nullable=True),
        sa.Column("snapshot", postgresql.JSONB, nullable=False),
        sa.Column("author_id", _uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("article_id", "version", name="uq_article_version"),
    )

    # ── Retrieval chunks ─────────────────────────────────────────
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "article_id",
            _uuid(),
            sa.ForeignKey("knowledge_articles.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("section", sa.String(80), nullable=False),
        sa.Column("header", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("token_estimate", sa.Integer, server_default="0"),
        sa.Column(
            "embedding_status",
            sa.Enum(*EMBEDDING_STATUSES, name="knowledge_chunk_embedding_status"),
            server_default="not_indexed",
        ),
        sa.Column("index_version", sa.Integer, server_default="0"),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("article_id", "chunk_index", name="uq_article_chunk_index"),
    )

    # ── Feedback ─────────────────────────────────────────────────
    op.create_table(
        "knowledge_feedback",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "article_id",
            _uuid(),
            sa.ForeignKey("knowledge_articles.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("user_id", _uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("rating", sa.Integer, nullable=True),
        sa.Column("was_helpful", sa.Boolean, nullable=True),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("source", sa.String(30), server_default="portal"),
        sa.Column("session_id", _uuid(), nullable=True),
        sa.Column("resolved_issue", sa.Boolean, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), index=True, nullable=False),
    )

    # ── Review notes ─────────────────────────────────────────────
    op.create_table(
        "knowledge_review_notes",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "article_id",
            _uuid(),
            sa.ForeignKey("knowledge_articles.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("reviewer_id", _uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "decision",
            sa.Enum(*REVIEW_DECISIONS, name="knowledge_review_decision"),
            server_default="comment",
        ),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("knowledge_review_notes")
    op.drop_table("knowledge_feedback")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_article_versions")
    op.drop_table("knowledge_articles")
    op.drop_table("knowledge_taxonomy_terms")
    op.drop_table("knowledge_ownership_groups")

    bind = op.get_bind()
    for enum_name in (
        "knowledge_review_decision",
        "knowledge_chunk_embedding_status",
        "knowledge_embedding_status",
        "knowledge_visibility_scope",
        "knowledge_audience",
        "knowledge_article_status",
        "knowledge_article_type",
        "knowledge_taxonomy_type",
    ):
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
