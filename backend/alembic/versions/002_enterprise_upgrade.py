"""Enterprise RBAC, ticketing, remote support, and analytics schema.

Revision ID: 002_enterprise_upgrade
Revises: 001_initial (or None if first migration)
Create Date: 2026-06-10

This migration adds:
- Enhanced user model with roles/permissions
- Role-based access control tables
- Enhanced ticket lifecycle
- Remote support sessions and consent
- Analytics snapshots
- Audit events (enhanced)
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "002_enterprise_upgrade"
down_revision = None  # Adjust to actual previous revision
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Permissions ──────────────────────────────────────────────
    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(100), unique=True, index=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("resource", sa.String(100), index=True, nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── Roles ────────────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(50), unique=True, index=True, nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_system", sa.Boolean, default=False),
        sa.Column("priority", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── Role Permissions ─────────────────────────────────────────
    op.create_table(
        "role_permissions",
        sa.Column(
            "role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id"), primary_key=True
        ),
        sa.Column(
            "permission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("permissions.id"),
            primary_key=True,
        ),
    )

    # ── Groups ───────────────────────────────────────────────────
    op.create_table(
        "groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, index=True, nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column(
            "default_role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── Users (enhanced) ─────────────────────────────────────────
    # Add new columns to existing users table
    op.add_column("users", sa.Column("job_title", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("phone", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("avatar_url", sa.String(500), nullable=True))
    op.add_column("users", sa.Column("is_verified", sa.Boolean, server_default="false"))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))

    # ── User Role Assignments ────────────────────────────────────
    op.create_table(
        "user_role_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            index=True,
            nullable=False,
        ),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id"),
            index=True,
            nullable=False,
        ),
        sa.Column(
            "assigned_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_role"),
    )

    # ── User Groups ──────────────────────────────────────────────
    op.create_table(
        "user_groups",
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True
        ),
        sa.Column(
            "group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("groups.id"), primary_key=True
        ),
    )

    # ── Auth Identities ──────────────────────────────────────────
    op.create_table(
        "auth_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.Column("provider_email", sa.String(255), nullable=True),
        sa.Column("provider_metadata", postgresql.JSONB, nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_provider_identity"),
    )

    # ── Login Sessions ───────────────────────────────────────────
    op.create_table(
        "login_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("token_jti", sa.String(255), unique=True, index=True, nullable=False),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("provider", sa.String(50), default="local"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, default=True),
    )

    # ── Tickets (enhanced) ───────────────────────────────────────
    op.add_column("tickets", sa.Column("ticket_number", sa.String(20), unique=True, index=True))
    op.add_column(
        "tickets",
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
    )
    op.add_column("tickets", sa.Column("category", sa.String(100), index=True))
    op.add_column("tickets", sa.Column("subcategory", sa.String(100), nullable=True))
    op.add_column("tickets", sa.Column("severity", sa.String(20), nullable=True))
    op.add_column("tickets", sa.Column("impact", sa.String(20), nullable=True))
    op.add_column("tickets", sa.Column("urgency", sa.String(20), nullable=True))
    op.add_column("tickets", sa.Column("source", sa.String(20), nullable=True))
    op.add_column(
        "tickets", sa.Column("escalated_to", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "tickets", sa.Column("remote_session_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "tickets", sa.Column("sla_response_target", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "tickets", sa.Column("sla_resolution_target", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "tickets", sa.Column("first_response_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("tickets", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tickets", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tickets", sa.Column("ai_confidence", sa.Float, nullable=True))
    op.add_column("tickets", sa.Column("ai_summary", sa.Text, nullable=True))
    op.add_column("tickets", sa.Column("suggested_articles", postgresql.JSONB, nullable=True))
    op.add_column("tickets", sa.Column("tags", postgresql.JSONB, nullable=True))
    op.add_column("tickets", sa.Column("custom_fields", postgresql.JSONB, nullable=True))
    op.add_column("tickets", sa.Column("resolution_notes", sa.Text, nullable=True))

    # ── Ticket Comments ──────────────────────────────────────────
    op.create_table(
        "ticket_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id"),
            index=True,
            nullable=False,
        ),
        sa.Column(
            "author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("is_internal", sa.Boolean, default=False),
        sa.Column("comment_type", sa.String(20), default="note"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── Ticket Events ────────────────────────────────────────────
    op.create_table(
        "ticket_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id"),
            index=True,
            nullable=False,
        ),
        sa.Column(
            "actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("event_type", sa.String(50), index=True, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("old_value", sa.Text, nullable=True),
        sa.Column("new_value", sa.Text, nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── Remote Support Sessions ──────────────────────────────────
    op.create_table(
        "remote_support_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            index=True,
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            index=True,
            nullable=False,
        ),
        sa.Column(
            "ticket_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tickets.id"), nullable=True
        ),
        sa.Column(
            "support_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("support_sessions.id"),
            nullable=True,
        ),
        sa.Column("session_type", sa.String(20), default="screen_view"),
        sa.Column("status", sa.String(30), default="requested", index=True),
        sa.Column("provider", sa.String(100), default="microsoft_remote_help"),
        sa.Column("provider_session_id", sa.String(255), nullable=True),
        sa.Column("join_url_agent", sa.String(1000), nullable=True),
        sa.Column("join_url_employee", sa.String(1000), nullable=True),
        sa.Column("join_code", sa.String(50), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consent_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_duration_minutes", sa.Integer, default=30),
        sa.Column("justification", sa.Text, nullable=True),
        sa.Column("policy_check_passed", sa.Boolean, default=False),
        sa.Column("termination_reason", sa.String(30), nullable=True),
        sa.Column("resolution_notes", sa.Text, nullable=True),
        sa.Column("actions_taken", postgresql.JSONB, nullable=True),
        sa.Column("provider_metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── Remote Support Consents ──────────────────────────────────
    op.create_table(
        "remote_support_consents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("remote_support_sessions.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        ),
        sa.Column(
            "employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("consent_type", sa.String(20), nullable=False),
        sa.Column("granted", sa.Boolean, nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consent_text_shown", sa.Text, nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(500), nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("denial_reason", sa.String(500), nullable=True),
    )

    # ── Remote Session Events ────────────────────────────────────
    op.create_table(
        "remote_session_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("remote_support_sessions.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        ),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column(
            "actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("event_metadata", postgresql.JSONB, nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
    )

    # ── Analytics Snapshots ──────────────────────────────────────
    op.create_table(
        "analytics_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("period_start", sa.DateTime(timezone=True), index=True, nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_type", sa.String(20), index=True, nullable=False),
        sa.Column("tickets_created", sa.Integer, default=0),
        sa.Column("tickets_resolved", sa.Integer, default=0),
        sa.Column("tickets_escalated", sa.Integer, default=0),
        sa.Column("tickets_breached_sla", sa.Integer, default=0),
        sa.Column("ai_resolutions", sa.Integer, default=0),
        sa.Column("ai_avg_confidence", sa.Float, nullable=True),
        sa.Column("live_handoffs", sa.Integer, default=0),
        sa.Column("avg_response_time_minutes", sa.Float, nullable=True),
        sa.Column("avg_resolution_time_minutes", sa.Float, nullable=True),
        sa.Column("remote_sessions_initiated", sa.Integer, default=0),
        sa.Column("remote_sessions_completed", sa.Integer, default=0),
        sa.Column("category_breakdown", postgresql.JSONB, nullable=True),
        sa.Column("priority_breakdown", postgresql.JSONB, nullable=True),
        sa.Column("agent_workload", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── Enhanced Audit Events ────────────────────────────────────
    op.add_column("audit_events", sa.Column("actor_email", sa.String(255), nullable=True))
    op.add_column("audit_events", sa.Column("actor_role", sa.String(50), nullable=True))
    op.add_column("audit_events", sa.Column("ip_address", sa.String(50), nullable=True))
    op.add_column("audit_events", sa.Column("user_agent", sa.String(500), nullable=True))
    op.add_column("audit_events", sa.Column("old_value", postgresql.JSONB, nullable=True))
    op.add_column("audit_events", sa.Column("new_value", postgresql.JSONB, nullable=True))
    op.add_column("audit_events", sa.Column("severity", sa.String(20), index=True))


def downgrade() -> None:
    op.drop_table("analytics_snapshots")
    op.drop_table("remote_session_events")
    op.drop_table("remote_support_consents")
    op.drop_table("remote_support_sessions")
    op.drop_table("ticket_events")
    op.drop_table("ticket_comments")
    op.drop_table("login_sessions")
    op.drop_table("auth_identities")
    op.drop_table("user_groups")
    op.drop_table("user_role_assignments")
    op.drop_table("groups")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("permissions")

    # Remove added columns
    op.drop_column("users", "job_title")
    op.drop_column("users", "phone")
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "is_verified")
    op.drop_column("users", "last_login_at")

    op.drop_column("audit_events", "actor_email")
    op.drop_column("audit_events", "actor_role")
    op.drop_column("audit_events", "ip_address")
    op.drop_column("audit_events", "user_agent")
    op.drop_column("audit_events", "old_value")
    op.drop_column("audit_events", "new_value")
    op.drop_column("audit_events", "severity")
