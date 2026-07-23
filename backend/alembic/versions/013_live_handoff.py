"""live handoff: specialist_availability + live_handoff_offers

Revision ID: 013_live_handoff
Revises: 012_support_sessions
Create Date: 2026-07-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "013_live_handoff"
down_revision = "012_support_sessions"
branch_labels = None
depends_on = None

_AVAIL = postgresql.ENUM(
    "available", "away", name="specialist_availability_status", create_type=False
)
_OFFER = postgresql.ENUM(
    "offered",
    "accepted",
    "expired",
    "broadened",
    "fallback",
    name="live_handoff_offer_state",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    _AVAIL.create(bind, checkfirst=True)
    _OFFER.create(bind, checkfirst=True)

    op.create_table(
        "specialist_availability",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "status",
            _AVAIL,
            nullable=False,
            server_default="away",
        ),
        sa.Column(
            "last_heartbeat_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "live_handoff_offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("offered_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("offered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("round_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "state",
            _OFFER,
            nullable=False,
            server_default="offered",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offered_to"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_live_handoff_offers_ticket_id", "live_handoff_offers", ["ticket_id"])
    op.create_index("ix_live_handoff_offers_state", "live_handoff_offers", ["state"])
    # One active (non-terminal) offer per ticket.
    op.create_index(
        "ix_live_handoff_active_per_ticket",
        "live_handoff_offers",
        ["ticket_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('offered','broadened')"),
    )


def downgrade() -> None:
    op.drop_index("ix_live_handoff_active_per_ticket", table_name="live_handoff_offers")
    op.drop_index("ix_live_handoff_offers_state", table_name="live_handoff_offers")
    op.drop_index("ix_live_handoff_offers_ticket_id", table_name="live_handoff_offers")
    op.drop_table("live_handoff_offers")
    op.drop_table("specialist_availability")
    op.execute("DROP TYPE IF EXISTS live_handoff_offer_state")
    op.execute("DROP TYPE IF EXISTS specialist_availability_status")
