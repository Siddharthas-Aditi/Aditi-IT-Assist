"""Chat-escalation artifacts — immutable transcript snapshot + structured context.

Revision ID: 009_chat_escalation_artifacts
Revises: 008_specialist_chat
Create Date: 2026-06-27

Creates two linked tables that preserve enough context for an IT specialist to
continue an escalated AI conversation without asking the employee to repeat
themselves:

* ``transcript_snapshots`` — immutable, ordered Employee ↔ AI message history
  captured at escalation time.
* ``escalation_contexts``  — structured handoff payload (one per ticket) +
  post-resolution AI-vs-specialist comparison fields.

See: docs/architecture/chat-escalation-artifacts.md,
     docs/architecture/transcript-snapshot-and-context-model.md
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "009_chat_escalation_artifacts"
down_revision = "008_specialist_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── transcript_snapshots ─────────────────────────────────────────────
    op.create_table(
        "transcript_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("chat_session_id", sa.String(128), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("message_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "messages",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "context_version",
            sa.String(16),
            nullable=False,
            server_default="1.0",
        ),
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
    op.create_index(
        "ix_transcript_snapshots_ticket_id",
        "transcript_snapshots",
        ["ticket_id"],
    )
    op.create_index(
        "ix_transcript_snapshots_chat_session_id",
        "transcript_snapshots",
        ["chat_session_id"],
    )

    # ── escalation_contexts ──────────────────────────────────────────────
    op.create_table(
        "escalation_contexts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Links
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "transcript_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transcript_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("chat_session_id", sa.String(128), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "escalation_created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # Issue understanding
        sa.Column("issue_summary", sa.Text, nullable=True),
        sa.Column("user_problem_statement", sa.Text, nullable=True),
        sa.Column("detected_intent", sa.String(80), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("subcategory", sa.String(100), nullable=True),
        sa.Column("affected_system", sa.String(120), nullable=True),
        sa.Column("urgency", sa.String(20), nullable=True),
        sa.Column("sentiment", sa.String(40), nullable=True),
        # AI attempts
        sa.Column("ai_attempted_steps", postgresql.JSONB, nullable=True),
        sa.Column("user_feedback_on_steps", postgresql.JSONB, nullable=True),
        sa.Column("kb_articles_referenced", postgresql.JSONB, nullable=True),
        sa.Column("kb_gap_tags", postgresql.JSONB, nullable=True),
        sa.Column("ai_confidence", sa.Float, nullable=True),
        sa.Column(
            "ai_resolution_status",
            sa.String(40),
            nullable=False,
            server_default="unresolved",
        ),
        # Escalation + routing
        sa.Column("escalation_reason", sa.Text, nullable=True),
        sa.Column(
            "live_support_required",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("specialist_queue_target", sa.String(80), nullable=True),
        sa.Column("handoff_triggered_by", sa.String(40), nullable=True),
        sa.Column("supervisor_decision_trace", postgresql.JSONB, nullable=True),
        sa.Column("diagnostic_slots", postgresql.JSONB, nullable=True),
        sa.Column(
            "context_version",
            sa.String(16),
            nullable=False,
            server_default="1.0",
        ),
        # Resolution comparison (filled post-resolution)
        sa.Column("specialist_resolution_summary", sa.Text, nullable=True),
        sa.Column("specialist_resolution_steps", postgresql.JSONB, nullable=True),
        sa.Column("final_resolution_category", sa.String(100), nullable=True),
        sa.Column("ai_vs_specialist_resolution_gap", sa.Text, nullable=True),
        sa.Column(
            "kb_candidate_flag",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("resolution_compared_at", sa.DateTime(timezone=True), nullable=True),
        # Timestamps
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
    # One escalation context per ticket.
    op.create_index(
        "ix_escalation_contexts_ticket_id",
        "escalation_contexts",
        ["ticket_id"],
        unique=True,
    )
    op.create_index(
        "ix_escalation_contexts_chat_session_id",
        "escalation_contexts",
        ["chat_session_id"],
    )
    op.create_index(
        "ix_escalation_contexts_category",
        "escalation_contexts",
        ["category"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_escalation_contexts_category",
        table_name="escalation_contexts",
    )
    op.drop_index(
        "ix_escalation_contexts_chat_session_id",
        table_name="escalation_contexts",
    )
    op.drop_index(
        "ix_escalation_contexts_ticket_id",
        table_name="escalation_contexts",
    )
    op.drop_table("escalation_contexts")

    op.drop_index(
        "ix_transcript_snapshots_chat_session_id",
        table_name="transcript_snapshots",
    )
    op.drop_index(
        "ix_transcript_snapshots_ticket_id",
        table_name="transcript_snapshots",
    )
    op.drop_table("transcript_snapshots")
