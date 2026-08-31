"""Add pending_approval_records table — durable human-approval queue.

Revision ID: 018_pending_approval_queue
Revises: 017_agent_action_ledger
Create Date: 2026-08-31
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "018_pending_approval_queue"
down_revision = "017_agent_action_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_approval_records",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column(
            "raw_args",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("proposer_id", sa.String(255), nullable=False),
        sa.Column("reason", sa.Text, nullable=False, server_default=""),
        sa.Column("side_effect", sa.String(32), nullable=False, server_default="write"),
        sa.Column("mcp_server", sa.String(128), nullable=True),
        sa.Column("args_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(255), nullable=True),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_pending_approval_records_status",
        "pending_approval_records",
        ["status"],
    )
    op.create_index(
        "ix_pending_approval_records_created_at",
        "pending_approval_records",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_pending_approval_records_created_at", "pending_approval_records")
    op.drop_index("ix_pending_approval_records_status", "pending_approval_records")
    op.drop_table("pending_approval_records")
