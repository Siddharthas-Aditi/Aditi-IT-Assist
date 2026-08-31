"""Upgrade legacy support sessions and messages to durable AI chat records.

Revision ID: 012_support_sessions
Revises: 011_scheduled_report_runs
Create Date: 2026-07-22

The bootstrap schema includes the original ``support_sessions`` and
``messages`` tables because earlier revisions already reference them. This
revision upgrades those tables to the durable chat contract instead of trying
to recreate them.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "012_support_sessions"
down_revision = "011_scheduled_report_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # These two enum types originate in 001. PostgreSQL enum labels are
    # additive, so extend them without replacing existing values or data.
    op.execute("ALTER TYPE session_status ADD VALUE IF NOT EXISTS 'awaiting_agent'")
    op.execute("ALTER TYPE session_status ADD VALUE IF NOT EXISTS 'live_support'")
    op.execute("ALTER TYPE message_role ADD VALUE IF NOT EXISTS 'agent'")

    session_type = postgresql.ENUM(
        "ai_chat",
        "live_support",
        "hybrid",
        name="session_type",
        create_type=False,
    )
    session_type.create(bind, checkfirst=True)

    message_type = postgresql.ENUM(
        "text",
        "system_event",
        "handoff",
        "resolution",
        name="message_type",
        create_type=False,
    )
    message_type.create(bind, checkfirst=True)

    op.add_column(
        "support_sessions",
        sa.Column(
            "assigned_agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "support_sessions",
        sa.Column(
            "session_type",
            session_type,
            nullable=False,
            server_default="ai_chat",
        ),
    )
    op.add_column(
        "support_sessions",
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_support_sessions_user_id", "support_sessions", ["user_id"])
    op.create_index("ix_support_sessions_status", "support_sessions", ["status"])
    op.create_index("ix_support_sessions_created_at", "support_sessions", ["created_at"])

    op.add_column(
        "messages",
        sa.Column(
            "sender_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "messages",
        sa.Column(
            "message_type",
            message_type,
            nullable=False,
            server_default="text",
        ),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])
    op.create_index("ix_messages_created_at", "messages", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_messages_created_at", table_name="messages")
    op.drop_index("ix_messages_session_id", table_name="messages")
    op.drop_column("messages", "message_type")
    op.drop_column("messages", "sender_id")

    op.drop_index("ix_support_sessions_created_at", table_name="support_sessions")
    op.drop_index("ix_support_sessions_status", table_name="support_sessions")
    op.drop_index("ix_support_sessions_user_id", table_name="support_sessions")
    op.drop_column("support_sessions", "metadata_json")
    op.drop_column("support_sessions", "session_type")
    op.drop_column("support_sessions", "assigned_agent_id")

    bind = op.get_bind()
    postgresql.ENUM(name="message_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="session_type").drop(bind, checkfirst=True)
