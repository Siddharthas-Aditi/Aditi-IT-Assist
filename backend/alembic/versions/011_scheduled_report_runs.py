"""Scheduled report runs — replica-safe once-per-month email claim (C2).

Revision ID: 011_scheduled_report_runs
Revises: 010_web_research_findings
Create Date: 2026-07-17

Creates ``scheduled_report_runs``, the idempotency record a scheduled job
writes before sending the monthly IT-leadership report. ``period`` (the
``"YYYY-MM"`` report month) carries a unique index so that concurrent
replicas racing the same scheduled tick can only claim a given month once —
every loser's insert fails with a unique-violation.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "011_scheduled_report_runs"
down_revision = "010_web_research_findings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_report_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="sending"),
        sa.Column("recipient_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
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
        "ix_scheduled_report_runs_period",
        "scheduled_report_runs",
        ["period"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scheduled_report_runs_period",
        table_name="scheduled_report_runs",
    )
    op.drop_table("scheduled_report_runs")
