"""Feedback tables — conversation_feedback + message_feedback.

Revision ID: 005_feedback
Revises: 004_document_ingestion
Create Date: 2026-06-15
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = "005_feedback"
down_revision = "004_document_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ENUM types ────────────────────────────────────────────────────────────
    support_mode_enum = postgresql.ENUM(
        "ai_only",
        "ai_plus_live_agent",
        "live_agent_only",
        name="support_mode_enum",
        create_type=False,
    )
    support_mode_enum.create(op.get_bind(), checkfirst=True)

    feedback_source_enum = postgresql.ENUM(
        "inline_chat",
        "ticket_page",
        "followup",
        name="feedback_source_enum",
        create_type=False,
    )
    feedback_source_enum.create(op.get_bind(), checkfirst=True)

    quality_bucket_enum = postgresql.ENUM(
        "positive",
        "neutral",
        "negative",
        name="quality_bucket_enum",
        create_type=False,
    )
    quality_bucket_enum.create(op.get_bind(), checkfirst=True)

    # ── conversation_feedback ─────────────────────────────────────────────────
    op.create_table(
        "conversation_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Core linkage
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("support_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "submitted_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Survey answers
        sa.Column("helpful", sa.Boolean(), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        # Submission metadata
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("channel", sa.String(50), nullable=False, server_default="web_chat"),
        sa.Column(
            "feedback_source",
            sa.Enum(
                "inline_chat",
                "ticket_page",
                "followup",
                name="feedback_source_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="inline_chat",
        ),
        # Session context
        sa.Column(
            "support_mode",
            sa.Enum(
                "ai_only",
                "ai_plus_live_agent",
                "live_agent_only",
                name="support_mode_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="ai_only",
        ),
        sa.Column(
            "agent_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "escalation_occurred",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("subcategory", sa.String(100), nullable=True),
        sa.Column("knowledge_article_ids", postgresql.JSONB(), nullable=True),
        # Timing
        sa.Column("session_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("first_response_time_seconds", sa.Integer(), nullable=True),
        # Derived / analytics columns
        sa.Column("sentiment_label", sa.String(20), nullable=True),
        sa.Column(
            "quality_bucket",
            sa.Enum(
                "positive",
                "neutral",
                "negative",
                name="quality_bucket_enum",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "review_flag",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("review_flag_reason", sa.String(255), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.create_index(
        "ix_conv_feedback_conversation_id", "conversation_feedback", ["conversation_id"]
    )
    op.create_index("ix_conv_feedback_ticket_id", "conversation_feedback", ["ticket_id"])
    op.create_index(
        "ix_conv_feedback_submitted_by", "conversation_feedback", ["submitted_by_user_id"]
    )
    op.create_index("ix_conv_feedback_agent_id", "conversation_feedback", ["agent_user_id"])
    op.create_index("ix_conv_feedback_review_flag", "conversation_feedback", ["review_flag"])
    op.create_unique_constraint(
        "uq_feedback_conversation_user",
        "conversation_feedback",
        ["conversation_id", "submitted_by_user_id"],
    )

    # ── message_feedback ──────────────────────────────────────────────────────
    op.create_table(
        "message_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("support_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "submitted_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("helpful", sa.Boolean(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("knowledge_article_ids", postgresql.JSONB(), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.create_index("ix_msg_feedback_message_id", "message_feedback", ["message_id"])
    op.create_index("ix_msg_feedback_session_id", "message_feedback", ["session_id"])
    op.create_index("ix_msg_feedback_submitted_by", "message_feedback", ["submitted_by_user_id"])
    op.create_unique_constraint(
        "uq_msg_feedback_message_user",
        "message_feedback",
        ["message_id", "submitted_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("message_feedback")
    op.drop_table("conversation_feedback")

    for enum_name in ("quality_bucket_enum", "feedback_source_enum", "support_mode_enum"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
