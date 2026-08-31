"""Initial support-platform schema.

Revision ID: 001_initial
Revises: None
Create Date: 2026-08-31

The original application created core identity, conversation, ticket, and
audit tables with ``Base.metadata.create_all`` but never committed the matching
Alembic revision. Revision 002 upgrades those tables, so a clean database
could not previously reach ``head`` using Alembic alone. Knowledge articles are
deliberately excluded: revision 003 establishes their governed schema.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("employee_id", sa.String(50), nullable=True),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column(
            "role",
            sa.Enum("employee", "it_agent", "admin", name="user_role"),
            nullable=False,
            server_default="employee",
        ),
        sa.Column("hashed_password", sa.String(255), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "support_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "active", "awaiting_user", "resolved", "escalated", "closed", name="session_status"
            ),
            nullable=False,
            server_default="active",
        ),
        sa.Column("issue_category", sa.String(100), nullable=True),
        sa.Column("issue_subcategory", sa.String(100), nullable=True),
        sa.Column("severity", sa.String(20), nullable=True),
        sa.Column("urgency", sa.String(20), nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("resolution_summary", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("support_sessions.id"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Enum("user", "assistant", "system", name="message_role"),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("support_sessions.id"),
            nullable=False,
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column(
            "priority",
            sa.Enum("low", "medium", "high", "critical", name="ticket_priority"),
            nullable=False,
            server_default="medium",
        ),
        sa.Column(
            "status",
            sa.Enum("draft", "open", "in_progress", "resolved", "closed", name="ticket_status"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "assigned_to",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("external_ticket_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("support_sessions.id"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("tickets")
    op.drop_table("messages")
    op.drop_table("support_sessions")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
