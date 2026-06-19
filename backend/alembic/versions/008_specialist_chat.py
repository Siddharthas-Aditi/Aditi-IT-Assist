"""Live specialist-chat tables — human-to-human conversation after AI handoff.

Revision ID: 008_specialist_chat
Revises: 007_knowledge_candidates
Create Date: 2026-06-19

Creates two tables + three enums + one unique partial index + one composite
index. Depends on 007 because ``specialist_chat_sessions.knowledge_candidate_id``
FK-references ``knowledge_candidates(id)``.

See: docs/architecture/live-specialist-chat.md
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "008_specialist_chat"
down_revision = "007_knowledge_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ENUM types ────────────────────────────────────────────────────────
    chat_status = postgresql.ENUM(
        "active",
        "idle_warning",
        "ended_by_user",
        "ended_by_specialist",
        "ended_by_timeout",
        "ended_by_system",
        name="specialist_chat_status",
        create_type=False,
    )
    chat_status.create(op.get_bind(), checkfirst=True)

    end_reason = postgresql.ENUM(
        "resolved",
        "user_left",
        "specialist_ended",
        "idle_timeout",
        "session_error",
        name="specialist_chat_end_reason",
        create_type=False,
    )
    end_reason.create(op.get_bind(), checkfirst=True)

    message_role = postgresql.ENUM(
        "user",
        "specialist",
        "system",
        name="specialist_message_role",
        create_type=False,
    )
    message_role.create(op.get_bind(), checkfirst=True)

    # ── specialist_chat_sessions ─────────────────────────────────────────
    op.create_table(
        "specialist_chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        # Foreign keys
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_email", sa.String(255), nullable=True),
        sa.Column("user_name", sa.String(255), nullable=True),
        sa.Column(
            "specialist_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("specialist_email", sa.String(255), nullable=True),
        sa.Column("specialist_name", sa.String(255), nullable=True),
        sa.Column(
            "ai_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("support_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),

        # Lifecycle
        sa.Column(
            "status",
            postgresql.ENUM(
                "active",
                "idle_warning",
                "ended_by_user",
                "ended_by_specialist",
                "ended_by_timeout",
                "ended_by_system",
                name="specialist_chat_status",
                create_type=False,
            ),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "idle_warning_at", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "end_reason",
            postgresql.ENUM(
                "resolved",
                "user_left",
                "specialist_ended",
                "idle_timeout",
                "session_error",
                name="specialist_chat_end_reason",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "ended_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),

        # Resolution metadata
        sa.Column("resolution_notes", sa.Text, nullable=True),
        sa.Column(
            "sent_to_knowledge_review",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "knowledge_candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_candidates.id", ondelete="SET NULL"),
            nullable=True,
        ),

        # Tunable thresholds
        sa.Column(
            "idle_warning_seconds",
            sa.Integer,
            nullable=False,
            server_default="120",
        ),
        sa.Column(
            "idle_end_seconds",
            sa.Integer,
            nullable=False,
            server_default="180",
        ),

        # Snapshot
        sa.Column("final_snapshot", postgresql.JSONB, nullable=True),

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

    op.create_index(
        "ix_specialist_chat_sessions_ticket_id",
        "specialist_chat_sessions",
        ["ticket_id"],
    )
    op.create_index(
        "ix_specialist_chat_sessions_user_id",
        "specialist_chat_sessions",
        ["user_id"],
    )
    op.create_index(
        "ix_specialist_chat_sessions_specialist_id",
        "specialist_chat_sessions",
        ["specialist_id"],
    )
    op.create_index(
        "ix_specialist_chat_sessions_status",
        "specialist_chat_sessions",
        ["status"],
    )
    op.create_index(
        "ix_specialist_chat_sessions_last_activity",
        "specialist_chat_sessions",
        ["last_activity_at"],
    )
    # Composite index used by "My Assigned" view.
    op.create_index(
        "ix_specialist_chat_specialist_active",
        "specialist_chat_sessions",
        ["specialist_id", "status"],
    )
    # Unique partial index: at most one active/idle_warning session per ticket.
    # This enforces the invariant that the service relies on (IntegrityError
    # on insert means "resume existing"). PostgreSQL-only feature; gated by
    # postgresql_where.
    op.create_index(
        "ix_specialist_chat_active_per_ticket",
        "specialist_chat_sessions",
        ["ticket_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('active', 'idle_warning')"
        ),
    )

    # ── specialist_chat_messages ─────────────────────────────────────────
    op.create_table(
        "specialist_chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "specialist_chat_sessions.id", ondelete="CASCADE"
            ),
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
            postgresql.ENUM(
                "user",
                "specialist",
                "system",
                name="specialist_message_role",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("system_event", sa.String(80), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_specialist_chat_messages_session_id",
        "specialist_chat_messages",
        ["session_id"],
    )
    op.create_index(
        "ix_specialist_chat_messages_created_at",
        "specialist_chat_messages",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_specialist_chat_messages_created_at",
        table_name="specialist_chat_messages",
    )
    op.drop_index(
        "ix_specialist_chat_messages_session_id",
        table_name="specialist_chat_messages",
    )
    op.drop_table("specialist_chat_messages")

    op.drop_index(
        "ix_specialist_chat_active_per_ticket",
        table_name="specialist_chat_sessions",
    )
    op.drop_index(
        "ix_specialist_chat_specialist_active",
        table_name="specialist_chat_sessions",
    )
    op.drop_index(
        "ix_specialist_chat_sessions_last_activity",
        table_name="specialist_chat_sessions",
    )
    op.drop_index(
        "ix_specialist_chat_sessions_status",
        table_name="specialist_chat_sessions",
    )
    op.drop_index(
        "ix_specialist_chat_sessions_specialist_id",
        table_name="specialist_chat_sessions",
    )
    op.drop_index(
        "ix_specialist_chat_sessions_user_id",
        table_name="specialist_chat_sessions",
    )
    op.drop_index(
        "ix_specialist_chat_sessions_ticket_id",
        table_name="specialist_chat_sessions",
    )
    op.drop_table("specialist_chat_sessions")

    bind = op.get_bind()
    postgresql.ENUM(name="specialist_message_role").drop(bind, checkfirst=True)
    postgresql.ENUM(name="specialist_chat_end_reason").drop(bind, checkfirst=True)
    postgresql.ENUM(name="specialist_chat_status").drop(bind, checkfirst=True)
