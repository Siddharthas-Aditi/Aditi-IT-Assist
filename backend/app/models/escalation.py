"""Chat-escalation artifacts — immutable transcript snapshot + structured context.

When an unresolved AI conversation is escalated to a live IT specialist, the
system captures **two linked, immutable artifacts** (see
``docs/architecture/chat-escalation-artifacts.md``):

1. :class:`TranscriptSnapshot` — the full ordered Employee ↔ AI message history
   exactly as it stood at handoff time. Write-once; later session edits, message
   deletions, or chat-state mutations must never alter it. Post-escalation
   human↔human messages live separately in ``specialist_chat_messages``.

2. :class:`EscalationContext` — the structured support-handoff payload optimized
   for specialist triage, queue routing, analytics, KB improvement, and AI
   evaluation. It also carries the **resolution-comparison** fields filled in
   *after* the specialist resolves (what the AI suggested vs. what the
   specialist actually did) for human-reviewed improvement workflows.

Both records hang off ``tickets`` (the parent operational object). We deliberately
do NOT reuse ``tickets.session_id`` (an FK to the unused ``support_sessions``
table); the in-memory chat-session identifier is stored as a plain
``chat_session_id`` string on both artifacts.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# Snapshot/context schema version — bump on any breaking shape change so that
# older persisted records remain interpretable.
ESCALATION_CONTEXT_VERSION = "1.0"

# Status the AI flow reached for the issue at escalation time.
AI_RESOLUTION_STATUSES = (
    "unresolved",
    "partially_resolved",
    "user_abandoned",
    "user_requested_human",
)


class TranscriptSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable, ordered snapshot of the AI ↔ employee conversation at handoff.

    Write-once by contract: the service layer creates this record and never
    updates ``messages``. The payload is a *copy* of the conversation at
    escalation time, so subsequent session mutations cannot reach it.

    ``messages`` is an ordered JSONB array; each element is::

        {
          "seq": 0,                       # 0-based ordering, authoritative
          "role": "employee"|"assistant"|"system",
          "content": "...",
          "message_type": "text"|"system_event"|"handoff"|"resolution"|null,
          "timestamp": "2026-06-27T10:00:00Z" | null
        }
    """

    __tablename__ = "transcript_snapshots"

    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    # The in-memory chat-session identifier (string) the snapshot was taken from.
    chat_session_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    # Ordered array of message dicts (see class docstring).
    messages: Mapped[list] = mapped_column(JSONB, default=list)
    context_version: Mapped[str] = mapped_column(
        String(16), default=ESCALATION_CONTEXT_VERSION,
    )


class EscalationContext(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Structured handoff payload for one escalated chat → ticket.

    One per ticket (``ticket_id`` is unique). Created at escalation time with the
    AI-side fields; the resolution-comparison fields are filled later when the
    specialist resolves the ticket.
    """

    __tablename__ = "escalation_contexts"

    # ── Links (parent ticket + transcript artifact) ─────────────────────────
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"),
        unique=True, index=True,
    )
    transcript_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transcript_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    chat_session_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    escalation_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )

    # ── Issue understanding (what the AI understood) ─────────────────────────
    issue_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_problem_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_intent: Mapped[str | None] = mapped_column(String(80), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)
    affected_system: Mapped[str | None] = mapped_column(String(120), nullable=True)
    urgency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # ── What the AI attempted + how it went ──────────────────────────────────
    # ai_attempted_steps: [{"instruction": str, "outcome": str, "source_kb_title": str|None}]
    ai_attempted_steps: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # user_feedback_on_steps: [{"step": str, "feedback": str}]
    user_feedback_on_steps: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # kb_articles_referenced: [{"article_id": str, "title": str, "relevance": float|None}]
    kb_articles_referenced: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # kb_gap_tags: controlled vocabulary (see services/agents/kb_gap_tags.py)
    kb_gap_tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_resolution_status: Mapped[str] = mapped_column(
        String(40), default="unresolved",
    )

    # ── Why it escalated + routing ───────────────────────────────────────────
    escalation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    live_support_required: Mapped[bool] = mapped_column(Boolean, default=False)
    specialist_queue_target: Mapped[str | None] = mapped_column(String(80), nullable=True)
    handoff_triggered_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Replayable supervisor decision trace + raw diagnostic slots for audit.
    supervisor_decision_trace: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    diagnostic_slots: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    context_version: Mapped[str] = mapped_column(
        String(16), default=ESCALATION_CONTEXT_VERSION,
    )

    # ── Resolution comparison (filled AFTER specialist resolves) ─────────────
    # Powers human-reviewed AI/KB improvement — NOT uncontrolled self-learning.
    specialist_resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # specialist_resolution_steps: ["step 1", "step 2", ...]
    specialist_resolution_steps: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    final_resolution_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_vs_specialist_resolution_gap: Mapped[str | None] = mapped_column(Text, nullable=True)
    kb_candidate_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution_compared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # ── Relationships ────────────────────────────────────────────────────────
    transcript_snapshot: Mapped["TranscriptSnapshot | None"] = relationship(
        "TranscriptSnapshot", lazy="joined",
    )


__all__ = [
    "AI_RESOLUTION_STATUSES",
    "ESCALATION_CONTEXT_VERSION",
    "EscalationContext",
    "TranscriptSnapshot",
]
