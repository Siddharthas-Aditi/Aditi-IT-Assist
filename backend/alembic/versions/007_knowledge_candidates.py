"""Knowledge improvement candidates — review-gated drafts.

Revision ID: 007_knowledge_candidates
Revises: 006_add_knowledge_chunks_embedding
Create Date: 2026-06-19

Creates the ``knowledge_candidates`` table + two enums (state, source) used
by the Knowledge Improvement loop. Candidates are draft KB articles
generated from real signals (specialist resolutions, unresolved sessions,
negative feedback, web fallback hits). They NEVER auto-publish — SMEs
review and explicitly promote.

See: docs/architecture/knowledge-improvement-loop.md
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "007_knowledge_candidates"
down_revision = "006_add_knowledge_chunks_embedding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ENUM types ────────────────────────────────────────────────────────
    candidate_state = postgresql.ENUM(
        "proposed",
        "triaged",
        "approved",
        "promoted",
        "rejected",
        "duplicate",
        name="knowledge_candidate_state",
        create_type=False,
    )
    candidate_state.create(op.get_bind(), checkfirst=True)

    candidate_source = postgresql.ENUM(
        "specialist_resolution",
        "unresolved_session",
        "negative_feedback",
        "web_fallback",
        "missing_subtype",
        "manual",
        name="knowledge_candidate_source",
        create_type=False,
    )
    candidate_source.create(op.get_bind(), checkfirst=True)

    # ── knowledge_candidates ─────────────────────────────────────────────
    op.create_table(
        "knowledge_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        # ── Provenance ────────────────────────────────────────────────
        sa.Column(
            "source",
            postgresql.ENUM(
                "specialist_resolution",
                "unresolved_session",
                "negative_feedback",
                "web_fallback",
                "missing_subtype",
                "manual",
                name="knowledge_candidate_source",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "source_session_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "source_ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_feedback_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("proposed_by_agent", sa.String(80), nullable=False),
        sa.Column(
            "proposed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),

        # ── Content (draft) ───────────────────────────────────────────
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column(
            "resolution_steps", postgresql.JSONB, nullable=True,
        ),

        # ── Classification ────────────────────────────────────────────
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("subcategory", sa.String(100), nullable=True),
        sa.Column("issue_subtype", sa.String(100), nullable=True),
        sa.Column("affected_system", sa.String(100), nullable=True),
        sa.Column("tags", postgresql.JSONB, nullable=True),

        # ── Review state ──────────────────────────────────────────────
        sa.Column(
            "state",
            postgresql.ENUM(
                "proposed",
                "triaged",
                "approved",
                "promoted",
                "rejected",
                "duplicate",
                name="knowledge_candidate_state",
                create_type=False,
            ),
            nullable=False,
            server_default="proposed",
        ),
        sa.Column(
            "triaged_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "triaged_at", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reviewed_at", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column("review_notes", postgresql.JSONB, nullable=True),
        sa.Column("rejected_reason", sa.String(500), nullable=True),
        sa.Column(
            "duplicate_of",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_articles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "promoted_article_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_articles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "promoted_at", sa.DateTime(timezone=True), nullable=True,
        ),

        # ── Quality signals ──────────────────────────────────────────
        sa.Column(
            "confidence", sa.Float, nullable=False, server_default="0.5",
        ),
        sa.Column(
            "times_seen", sa.Integer, nullable=False, server_default="1",
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), nullable=True,
        ),

        # ── TimestampMixin ───────────────────────────────────────────
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Indexes (mirroring model `index=True` columns + analytics queries).
    op.create_index(
        "ix_knowledge_candidates_source",
        "knowledge_candidates",
        ["source"],
    )
    op.create_index(
        "ix_knowledge_candidates_state",
        "knowledge_candidates",
        ["state"],
    )
    op.create_index(
        "ix_knowledge_candidates_source_session",
        "knowledge_candidates",
        ["source_session_id"],
    )
    op.create_index(
        "ix_knowledge_candidates_source_ticket",
        "knowledge_candidates",
        ["source_ticket_id"],
    )
    op.create_index(
        "ix_knowledge_candidates_proposed_by_agent",
        "knowledge_candidates",
        ["proposed_by_agent"],
    )
    op.create_index(
        "ix_knowledge_candidates_category",
        "knowledge_candidates",
        ["category"],
    )
    op.create_index(
        "ix_knowledge_candidates_issue_subtype",
        "knowledge_candidates",
        ["issue_subtype"],
    )
    # The SME review queue sorts by (confidence desc, times_seen desc,
    # created_at desc) within a single state — back this with a composite
    # index for fast paging.
    op.create_index(
        "ix_knowledge_candidates_review_queue",
        "knowledge_candidates",
        [
            "state",
            sa.text("confidence DESC"),
            sa.text("times_seen DESC"),
            sa.text("created_at DESC"),
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_candidates_review_queue", table_name="knowledge_candidates"
    )
    op.drop_index(
        "ix_knowledge_candidates_issue_subtype",
        table_name="knowledge_candidates",
    )
    op.drop_index(
        "ix_knowledge_candidates_category", table_name="knowledge_candidates"
    )
    op.drop_index(
        "ix_knowledge_candidates_proposed_by_agent",
        table_name="knowledge_candidates",
    )
    op.drop_index(
        "ix_knowledge_candidates_source_ticket",
        table_name="knowledge_candidates",
    )
    op.drop_index(
        "ix_knowledge_candidates_source_session",
        table_name="knowledge_candidates",
    )
    op.drop_index(
        "ix_knowledge_candidates_state", table_name="knowledge_candidates"
    )
    op.drop_index(
        "ix_knowledge_candidates_source", table_name="knowledge_candidates"
    )
    op.drop_table("knowledge_candidates")

    # Drop the enums LAST — nothing should reference them at this point.
    bind = op.get_bind()
    postgresql.ENUM(name="knowledge_candidate_state").drop(bind, checkfirst=True)
    postgresql.ENUM(name="knowledge_candidate_source").drop(bind, checkfirst=True)
