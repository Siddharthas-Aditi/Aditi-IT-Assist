"""Web-research findings on escalation context (B2).

Adds a JSONB column holding trust-filtered external findings captured at
escalation for the specialist handoff. Employees never see this content.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "010_web_research_findings"
down_revision = "009_chat_escalation_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "escalation_contexts",
        sa.Column("web_research_findings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("escalation_contexts", "web_research_findings")
