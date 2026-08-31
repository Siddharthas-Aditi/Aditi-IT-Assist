"""Add Changes and Assets domain tables.

Revision ID: 020_changes_and_assets
Revises: 019_analytics_team_groups
Create Date: 2026-09-01

Entities added:
- changes + change_type_enum, change_status_enum
- change_approvals + approval_decision_enum
- change_tasks
- change_events
- change_asset_links (M2M)
- ticket_asset_links (backend-persisted)
- assets + asset_status_enum, asset_hardware_type_enum, asset_usage_type_enum,
  asset_condition_enum
- asset_events
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "020_changes_and_assets"
down_revision = "019_analytics_team_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ──────────────────────────────────────────────────────────────
    change_type = postgresql.ENUM(
        "standard", "normal", "emergency", name="change_type_enum", create_type=False
    )
    change_type.create(op.get_bind(), checkfirst=True)

    change_status = postgresql.ENUM(
        "draft",
        "submitted",
        "planning",
        "pending_approval",
        "scheduled",
        "in_progress",
        "implemented",
        "rolled_back",
        "rejected",
        "cancelled",
        "closed",
        name="change_status_enum",
        create_type=False,
    )
    change_status.create(op.get_bind(), checkfirst=True)

    approval_decision = postgresql.ENUM(
        "pending", "approved", "rejected", name="approval_decision_enum", create_type=False
    )
    approval_decision.create(op.get_bind(), checkfirst=True)

    asset_status = postgresql.ENUM(
        "in_stock",
        "assigned",
        "in_use",
        "under_repair",
        "reserved",
        "lost",
        "retired",
        "disposed",
        name="asset_status_enum",
        create_type=False,
    )
    asset_status.create(op.get_bind(), checkfirst=True)

    asset_hw = postgresql.ENUM(
        "physical", "virtual", name="asset_hardware_type_enum", create_type=False
    )
    asset_hw.create(op.get_bind(), checkfirst=True)

    asset_usage = postgresql.ENUM(
        "permanent",
        "loaner",
        "temporary",
        "shared",
        name="asset_usage_type_enum",
        create_type=False,
    )
    asset_usage.create(op.get_bind(), checkfirst=True)

    asset_cond = postgresql.ENUM(
        "new",
        "good",
        "fair",
        "minor_damage",
        "damaged",
        "faulty",
        name="asset_condition_enum",
        create_type=False,
    )
    asset_cond.create(op.get_bind(), checkfirst=True)

    # ── Asset (before changes; changes FK → assets) ─────────────────────
    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_tag", sa.String(64), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("asset_type", sa.String(128), nullable=False, server_default=""),
        sa.Column("impact", sa.String(16), nullable=False, server_default="low"),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "status", sa.Enum(name="asset_status_enum"), nullable=False, server_default="in_stock"
        ),
        sa.Column(
            "hardware_type",
            sa.Enum(name="asset_hardware_type_enum"),
            nullable=False,
            server_default="physical",
        ),
        sa.Column(
            "usage_type",
            sa.Enum(name="asset_usage_type_enum"),
            nullable=False,
            server_default="permanent",
        ),
        sa.Column(
            "condition", sa.Enum(name="asset_condition_enum"), nullable=False, server_default="good"
        ),
        sa.Column("physical_subtype", sa.String(128), nullable=True),
        sa.Column("virtual_subtype", sa.String(128), nullable=True),
        sa.Column("product", sa.String(255), nullable=True),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("vendor", sa.String(255), nullable=True),
        sa.Column("serial_number", sa.String(255), nullable=True),
        sa.Column("classification", sa.String(128), nullable=True),
        sa.Column("cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("warranty_info", sa.String(255), nullable=True),
        sa.Column("acquisition_date", sa.Date, nullable=True),
        sa.Column("warranty_expiry", sa.Date, nullable=True),
        sa.Column("invoice_number", sa.String(128), nullable=True),
        sa.Column("po_number", sa.String(128), nullable=True),
        sa.Column("contract", sa.String(255), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("mac_address", sa.String(32), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("department", sa.String(128), nullable=True),
        sa.Column("managed_by_group", sa.String(128), nullable=True),
        sa.Column(
            "assigned_to_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("assigned_date", sa.Date, nullable=True),
        sa.Column("end_of_life", sa.Date, nullable=True),
        sa.Column("retirement_reason", sa.Text, nullable=True),
        sa.Column("retirement_date", sa.Date, nullable=True),
        sa.Column("source", sa.String(128), nullable=True),
        sa.Column(
            "parent_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_assets_asset_tag", "assets", ["asset_tag"])
    op.create_index("ix_assets_status", "assets", ["status"])
    op.create_index("ix_assets_serial_number", "assets", ["serial_number"])
    op.create_index("ix_assets_assigned_to_id", "assets", ["assigned_to_id"])

    # ── Changes ─────────────────────────────────────────────────────────
    op.create_table(
        "changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("change_number", sa.String(32), unique=True, nullable=False),
        sa.Column(
            "source_ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "requested_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "assigned_to_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "change_type", sa.Enum(name="change_type_enum"), nullable=False, server_default="normal"
        ),
        sa.Column(
            "status", sa.Enum(name="change_status_enum"), nullable=False, server_default="draft"
        ),
        sa.Column("priority", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("impact", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("risk", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("department", sa.String(128), nullable=True),
        sa.Column("category", sa.String(128), nullable=True),
        sa.Column("maintenance_window", sa.String(256), nullable=True),
        sa.Column("planned_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closure_notes", sa.Text, nullable=False, server_default=""),
        sa.Column("emergency_justification", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "planning_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_changes_change_number", "changes", ["change_number"])
    op.create_index("ix_changes_status", "changes", ["status"])
    op.create_index("ix_changes_requested_by_id", "changes", ["requested_by_id"])

    # ── ChangeApprovals ─────────────────────────────────────────────────
    op.create_table(
        "change_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "change_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("changes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "approver_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "decision",
            sa.Enum(name="approval_decision_enum"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("comments", sa.Text, nullable=False, server_default=""),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_change_approvals_change_id", "change_approvals", ["change_id"])

    # ── ChangeTasks ─────────────────────────────────────────────────────
    op.create_table(
        "change_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "change_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("changes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(512), nullable=False),
        sa.Column("done", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_change_tasks_change_id", "change_tasks", ["change_id"])

    # ── ChangeEvents ────────────────────────────────────────────────────
    op.create_table(
        "change_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "change_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("changes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=True),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_change_events_change_id", "change_events", ["change_id"])

    # ── ChangeAssetLinks ────────────────────────────────────────────────
    op.create_table(
        "change_asset_links",
        sa.Column(
            "change_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("changes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # ── TicketAssetLinks ────────────────────────────────────────────────
    op.create_table(
        "ticket_asset_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "linked_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_ticket_asset_links_ticket_id", "ticket_asset_links", ["ticket_id"])
    op.create_index("ix_ticket_asset_links_asset_id", "ticket_asset_links", ["asset_id"])

    # ── AssetEvents ─────────────────────────────────────────────────────
    op.create_table(
        "asset_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=True),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_asset_events_asset_id", "asset_events", ["asset_id"])


def downgrade() -> None:
    op.drop_table("asset_events")
    op.drop_table("ticket_asset_links")
    op.drop_table("change_asset_links")
    op.drop_table("change_events")
    op.drop_table("change_tasks")
    op.drop_table("change_approvals")
    op.drop_table("changes")
    op.drop_table("assets")
    for enum_name in (
        "asset_condition_enum",
        "asset_usage_type_enum",
        "asset_hardware_type_enum",
        "asset_status_enum",
        "approval_decision_enum",
        "change_status_enum",
        "change_type_enum",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
