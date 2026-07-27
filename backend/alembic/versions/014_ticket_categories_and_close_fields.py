"""014 — ticket categories (3-level hierarchy) + ticket close/type fields.

Revision ID: 014
Revises: 013
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. ticket_categories — admin-managed 3-level hierarchy ─────────────
    op.create_table(
        "ticket_categories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("level", sa.Integer, nullable=False),  # 1=category 2=subcategory 3=item
        sa.Column(
            "parent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ticket_categories.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column("sort_order", sa.Integer, server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_ticket_categories_parent_id", "ticket_categories", ["parent_id"])
    op.create_index("ix_ticket_categories_level", "ticket_categories", ["level"])

    # ── 2. New columns on tickets table ────────────────────────────────────
    # ticket_type — simple type tag (Incident / Service Request / Problem / Change / Other)
    op.add_column(
        "tickets",
        sa.Column("ticket_type", sa.String(50), nullable=True),
    )
    # item — 3rd level of the category hierarchy
    op.add_column(
        "tickets",
        sa.Column("item", sa.String(255), nullable=True),
    )
    # close_notes — resolution notes captured at close time
    op.add_column(
        "tickets",
        sa.Column("close_notes", sa.Text, nullable=True),
    )
    # closed_by — who closed the ticket (IT staff only)
    op.add_column(
        "tickets",
        sa.Column("closed_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tickets", "closed_by")
    op.drop_column("tickets", "close_notes")
    op.drop_column("tickets", "item")
    op.drop_column("tickets", "ticket_type")
    op.drop_index("ix_ticket_categories_level", "ticket_categories")
    op.drop_index("ix_ticket_categories_parent_id", "ticket_categories")
    op.drop_table("ticket_categories")
