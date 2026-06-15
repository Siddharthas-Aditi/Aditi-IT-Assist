"""Document ingestion tables.

Revision ID: 004_document_ingestion
Revises: 003_knowledge_management
Create Date: 2026-06-15

Adds two tables that support the document-upload → knowledge-article pipeline:
- ``ingestion_jobs``       — one per uploaded document
- ``ingestion_candidates`` — one per extracted topic segment
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "004_document_ingestion"
down_revision = "003_knowledge_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ENUM types ────────────────────────────────────────────────────────────
    parse_status_enum = postgresql.ENUM(
        "pending", "extracting", "parsing", "completed", "failed",
        name="ingestion_parse_status",
        create_type=False,
    )
    extraction_status_enum = postgresql.ENUM(
        "pending", "completed", "failed",
        name="ingestion_extraction_status",
        create_type=False,
    )
    review_status_enum = postgresql.ENUM(
        "pending", "approved", "rejected", "saved",
        name="ingestion_candidate_review_status",
        create_type=False,
    )

    # Create ENUMs first
    op.execute("CREATE TYPE ingestion_parse_status AS ENUM ('pending','extracting','parsing','completed','failed')")
    op.execute("CREATE TYPE ingestion_extraction_status AS ENUM ('pending','completed','failed')")
    op.execute("CREATE TYPE ingestion_candidate_review_status AS ENUM ('pending','approved','rejected','saved')")

    # ── ingestion_jobs ────────────────────────────────────────────────────────
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_filename", sa.String(512), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("source_size", sa.Integer(), nullable=True),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "parse_status",
            sa.Enum(name="ingestion_parse_status", create_constraint=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "extraction_status",
            sa.Enum(name="ingestion_extraction_status", create_constraint=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processing_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_text_ref", sa.Text(), nullable=True),
        sa.Column("parser_version", sa.String(32), nullable=True),
        sa.Column("error_details", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ── ingestion_candidates ──────────────────────────────────────────────────
    op.create_table(
        "ingestion_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "ingestion_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_jobs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("candidate_index", sa.Integer(), nullable=False),
        sa.Column("extracted_title", sa.String(512), nullable=True),
        sa.Column("extracted_summary", sa.Text(), nullable=True),
        sa.Column("extracted_category", sa.String(128), nullable=True),
        sa.Column("extracted_subcategory", sa.String(128), nullable=True),
        sa.Column("extracted_product_or_system", sa.String(256), nullable=True),
        sa.Column("extracted_platform", sa.String(256), nullable=True),
        sa.Column("extracted_symptoms", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extracted_troubleshooting_steps", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extracted_resolution_steps", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extracted_escalation_criteria", sa.Text(), nullable=True),
        sa.Column("extracted_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extracted_keywords", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extracted_owner_group", sa.String(256), nullable=True),
        sa.Column("extracted_confidence", sa.Float(), nullable=True),
        sa.Column("validation_warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "review_status",
            sa.Enum(name="ingestion_candidate_review_status", create_constraint=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "mapped_article_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_articles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("raw_segment_text", sa.Text(), nullable=True),
        sa.Column("normalized_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ── Indexes ───────────────────────────────────────────────────────────────
    op.create_index(
        "ix_ingestion_candidates_job_id",
        "ingestion_candidates",
        ["ingestion_job_id"],
    )
    op.create_index(
        "ix_ingestion_candidates_review_status",
        "ingestion_candidates",
        ["review_status"],
    )
    op.create_index(
        "ix_ingestion_jobs_uploaded_by",
        "ingestion_jobs",
        ["uploaded_by"],
    )
    op.create_index(
        "ix_ingestion_jobs_parse_status",
        "ingestion_jobs",
        ["parse_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_parse_status", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_uploaded_by", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_candidates_review_status", table_name="ingestion_candidates")
    op.drop_index("ix_ingestion_candidates_job_id", table_name="ingestion_candidates")
    op.drop_table("ingestion_candidates")
    op.drop_table("ingestion_jobs")
    op.execute("DROP TYPE IF EXISTS ingestion_candidate_review_status")
    op.execute("DROP TYPE IF EXISTS ingestion_extraction_status")
    op.execute("DROP TYPE IF EXISTS ingestion_parse_status")
