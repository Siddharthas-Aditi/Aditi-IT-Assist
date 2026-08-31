"""Immutable ledger of every automated/agentic action taken by the system.

Every specialist dispatch, tool invocation, and approval decision is recorded
here. The ledger is append-only by convention (no updates to existing rows —
status transitions are new columns, not mutations), queryable by specialists
and auditors, and must survive service restarts.

Why a ledger (and not just structlog)
--------------------------------------
- Structlog is an ephemeral stream. The ledger is a durable, queryable table
  that can be joined against tickets, sessions, and the approval queue.
- Auditors can query "which automated actions were taken for ticket X?" in SQL.
- Specialists can check "have I already tried tool Y for this session?" without
  replaying the chat log.
- The ledger satisfies the Phase-2 observability requirement: confidence,
  escalation signal, and input fingerprints are indexed for analytics.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AgentActionLedger(Base):
    """One entry per agentic action taken during a support session.

    Rows are written at the moment of dispatch (before the specialist runs)
    and completed (result + confidence) when the specialist returns. An
    ``escalation_signal`` is recorded when the specialist signals it cannot
    proceed without human help.
    """

    __tablename__ = "agent_action_ledger"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Session context ──────────────────────────────────────────────────
    session_id: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)
    # Link to ticket if one exists (nullable — dispatch often precedes ticket creation)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True
    )

    # ── Who triggered it ─────────────────────────────────────────────────
    triggered_by: Mapped[str] = mapped_column(sa.String(255), nullable=False)

    # ── What ran ─────────────────────────────────────────────────────────
    # 'specialist_dispatch' | 'tool_call' | 'sub_agent_dispatch'
    action_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    specialist_name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    sub_agent_name: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    # Issue context at time of dispatch (category, subtype, system)
    inputs_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )

    # ── Approval ─────────────────────────────────────────────────────────
    # 'auto' = auto-approved (read-only / advisory specialist run)
    # 'pending' = waiting for human approval
    # 'approved' = human approved and executed
    # 'rejected' = human or policy rejected
    approval_status: Mapped[str] = mapped_column(sa.String(32), nullable=False, default="auto")
    approved_by: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    approval_decision_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    # ── Result ───────────────────────────────────────────────────────────
    # Serialized SpecialistOutput (steps, message, confidence).
    result_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    # Non-null when the specialist signalled "I'm done — escalate".
    escalation_signal: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)

    # ── Timestamps ───────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    # Set when the specialist's handle() returns (even on escalation).
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


__all__ = ["AgentActionLedger"]
