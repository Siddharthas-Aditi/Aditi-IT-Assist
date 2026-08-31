"""Add agent_action_ledger table — immutable record of every agentic dispatch.

Revision ID: 017_agent_action_ledger
Revises: 016_escalation_retrieval_trace
Create Date: 2026-08-31
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "017_agent_action_ledger"
down_revision = "016_escalation_retrieval_trace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_action_ledger",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Session context
        sa.Column("session_id", sa.String(255), nullable=False),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Who triggered it
        sa.Column("triggered_by", sa.String(255), nullable=False),
        # What ran
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("specialist_name", sa.String(128), nullable=False),
        sa.Column("sub_agent_name", sa.String(128), nullable=True),
        sa.Column(
            "inputs_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        # Approval
        sa.Column("approval_status", sa.String(32), nullable=False, server_default="auto"),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("approval_decision_at", sa.DateTime(timezone=True), nullable=True),
        # Result
        sa.Column(
            "result_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("escalation_signal", sa.String(128), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_action_ledger_session_id", "agent_action_ledger", ["session_id"])
    op.create_index("ix_agent_action_ledger_ticket_id", "agent_action_ledger", ["ticket_id"])
    op.create_index(
        "ix_agent_action_ledger_specialist_name", "agent_action_ledger", ["specialist_name"]
    )


def downgrade() -> None:
    op.drop_index("ix_agent_action_ledger_specialist_name", "agent_action_ledger")
    op.drop_index("ix_agent_action_ledger_ticket_id", "agent_action_ledger")
    op.drop_index("ix_agent_action_ledger_session_id", "agent_action_ledger")
    op.drop_table("agent_action_ledger")
