"""Durable model for human-approval queue records.

Write actions proposed by agents are persisted here so the queue survives
service restarts. This replaces the previous in-memory dict in ApprovalQueue.

Safety semantics
----------------
* A row in ``PENDING`` state is actionable by an IT lead.
* A row in ``EXECUTING`` state was claimed just before a service crashed. On
  startup, reconciliation resets these to ``PENDING`` and marks them with
  ``recovered_at`` so approvers know the execution never completed.
* Rows in terminal states (APPROVED, REJECTED, FAILED, INVALID) are permanent
  and never modified after the decision is recorded.
* No row is ever silently dropped or auto-approved by reconciliation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PendingApprovalRecord(Base):
    """One pending/decided approval record. Rows are append-mostly immutable."""

    __tablename__ = "pending_approval_records"

    id: Mapped[str] = mapped_column(sa.String(64), primary_key=True)

    # ── What was proposed ────────────────────────────────────────────────
    tool_name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    raw_args: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    proposer_id: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    reason: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    side_effect: Mapped[str] = mapped_column(sa.String(32), nullable=False, default="write")
    mcp_server: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    args_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False, default="")

    # ── Lifecycle ────────────────────────────────────────────────────────
    # Status: pending | executing | approved | rejected | failed | invalid
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    decided_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    # ── Restart recovery ─────────────────────────────────────────────────
    # Non-null when this record was in EXECUTING state at restart and was
    # reset to PENDING by the startup reconciliation step.
    recovered_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


__all__ = ["PendingApprovalRecord"]
