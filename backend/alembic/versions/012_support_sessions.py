"""Support sessions + messages — durable AI chat persistence.

Revision ID: 012_support_sessions
Revises: 011_scheduled_report_runs
Create Date: 2026-07-22

The ``support_sessions`` and ``messages`` models existed in code and were
referenced by feedback (005), specialist chat (008), and remote support (002)
FKs, but the tables were never created. This migration adds them so chat
turns, feedback, analytics, and ticket linkage can share one durable record.

See: docs/architecture/transcript-snapshot-and-context-model.md
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "012_support_sessions"
down_revision = "011_scheduled_report_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    session_status = postgresql.ENUM(
        "active",
        "awaiting_user",
        "awaiting_agent",
        "live_support",
        "resolved",
        "escalated",
        "closed",
        name="session_status",
        create_type=False,
    )
    session_status.create(op.get_bind(), checkfirst=True)

    session_type = postgresql.ENUM(
        "ai_chat",
        "live_support",
        "hybrid",
        name="session_type",
        create_type=False,
    )
    session_type.create(op.get_bind(), checkfirst=True)

    message_role = postgresql.ENUM(
        "user",
        "assistant",
        "system",
        "agent",
        name="message_role",
        create_type=False,
    )
    message_role.create(op.get_bind(), checkfirst=True)

    message_type = postgresql.ENUM(
        "text",
        "system_event",
        "handoff",
        "resolution",
        name="message_type",
        create_type=False,
    )
    message_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "support_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assigned_agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "awaiting_user",
                "awaiting_agent",
                "live_support",
                "resolved",
                "escalated",
                "closed",
                name="session_status",
                create_type=False,
            ),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "session_type",
            sa.Enum(
                "ai_chat",
                "live_support",
                "hybrid",
                name="session_type",
                create_type=False,
            ),
            nullable=False,
            server_default="ai_chat",
        ),
        sa.Column("issue_category", sa.String(100), nullable=True),
        sa.Column("issue_subcategory", sa.String(100), nullable=True),
        sa.Column("severity", sa.String(20), nullable=True),
        sa.Column("urgency", sa.String(20), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("resolution_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_support_sessions_user_id", "support_sessions", ["user_id"])
    op.create_index("ix_support_sessions_status", "support_sessions", ["status"])
    op.create_index("ix_support_sessions_created_at", "support_sessions", ["created_at"])

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("support_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sender_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "role",
            sa.Enum(
                "user",
                "assistant",
                "system",
                "agent",
                name="message_role",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "message_type",
            sa.Enum(
                "text",
                "system_event",
                "handoff",
                "resolution",
                name="message_type",
                create_type=False,
            ),
            nullable=False,
            server_default="text",
        ),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])
    op.create_index("ix_messages_created_at", "messages", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_messages_created_at", table_name="messages")
    op.drop_index("ix_messages_session_id", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_support_sessions_created_at", table_name="support_sessions")
    op.drop_index("ix_support_sessions_status", table_name="support_sessions")
    op.drop_index("ix_support_sessions_user_id", table_name="support_sessions")
    op.drop_table("support_sessions")

    op.execute("DROP TYPE IF EXISTS message_type")
    op.execute("DROP TYPE IF EXISTS message_role")
    op.execute("DROP TYPE IF EXISTS session_type")
    op.execute("DROP TYPE IF EXISTS session_status")
