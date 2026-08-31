"""Persist retrieval trace with immutable escalation context.

Revision ID: 016_escalation_retrieval_trace
Revises: 015_ticket_number_sequence
Create Date: 2026-08-31
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "016_escalation_retrieval_trace"
down_revision = "015_ticket_number_sequence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "escalation_contexts",
        sa.Column(
            "retrieval_trace",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("escalation_contexts", "retrieval_trace")
