"""Add group_type to groups and index user_groups.group_id for team analytics.

Revision ID: 019_analytics_team_groups
Revises: 018_pending_approval_queue
Create Date: 2026-09-01

Why
---
``groups`` was originally designed for SAML group-to-role mapping. Adding a
``group_type`` column lets admins designate groups as analytics teams without
conflating them with SAML sync groups. The index on ``user_groups.group_id``
makes "find all members of a group" efficient for team-scoped analytics queries.
"""

import sqlalchemy as sa
from alembic import op

revision = "019_analytics_team_groups"
down_revision = "018_pending_approval_queue"
branch_labels = None
depends_on = None

_GROUP_TYPES = ("general", "saml_sync", "analytics_team")


def upgrade() -> None:
    # Add group_type to distinguish analytics teams from SAML sync groups.
    # Existing rows default to 'general'; admins promote to 'analytics_team'.
    op.add_column(
        "groups",
        sa.Column(
            "group_type",
            sa.Enum(*_GROUP_TYPES, name="group_type_enum"),
            nullable=False,
            server_default="general",
        ),
    )
    # Index for the analytics query pattern: "find all members of group X"
    op.create_index("ix_user_groups_group_id", "user_groups", ["group_id"])


def downgrade() -> None:
    op.drop_index("ix_user_groups_group_id", "user_groups")
    op.drop_column("groups", "group_type")
    op.execute("DROP TYPE IF EXISTS group_type_enum")
