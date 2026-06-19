"""Live specialist-chat models — the human-to-human leg after AI handoff.

Two tables:

* :class:`SpecialistChatSession` — one row per live conversation between an
  employee and an IT specialist (1:1). Lifecycle is captured as a state
  machine (``active`` → ``idle_warning`` → ``ended_*``) so analytics + audit
  can replay every transition with a typed reason.

* :class:`SpecialistChatMessage` — one row per message turn (user, specialist,
  or system). Full transcript kept verbatim so reviewers, SMEs, and the
  knowledge-improvement loop can learn from real human resolutions.

Why separate from ``SupportSession`` / ``Message``
--------------------------------------------------
``SupportSession`` is the *AI* conversation; mixing the human-to-human leg
into the same table conflated several concerns: distinct retention policies
(human transcripts often require a longer hold for compliance), distinct
audit needs (every specialist keystroke is auditable; every AI turn is
*observable* but not equally privileged), and distinct UI access patterns
(specialists pivot off these tables; employees off the AI-side tables).

Splitting them is the cleaner architectural choice and avoids growing
``SupportSession`` into a god-table.

Lifecycle invariants
--------------------
1. **One active live session per ticket** at a time (enforced via a unique
   partial index in the migration — *"WHERE status IN ('active',
   'idle_warning')"*).
2. **Idle timeout is deterministic.** The service checks ``last_activity_at``
   against an idle threshold (default 3 minutes). Two thresholds:
   * ``idle_warning_after`` — bot posts "Are you still there?" system message.
   * ``idle_end_after`` — chat auto-ends with ``end_reason='timeout'``.
3. **End reasons are typed.** No free-text — every transition is one of
   :data:`SPECIALIST_CHAT_END_REASONS`. Auditors can group by reason.
4. **No deletions.** Sessions and messages are immutable once written.
   "End" flips status; nothing is removed.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

SPECIALIST_CHAT_STATUSES = (
    "active",          # specialist + user are both in
    "idle_warning",    # idle threshold #1 hit — system asked if still there
    "ended_by_user",   # user clicked "End chat"
    "ended_by_specialist",  # specialist marked resolved / ended
    "ended_by_timeout",     # idle threshold #2 hit — auto-end
    "ended_by_system",      # error / forced close
)

SPECIALIST_CHAT_END_REASONS = (
    "resolved",                  # specialist closed with a resolution
    "user_left",                 # user ended explicitly
    "specialist_ended",          # specialist ended without resolution
    "idle_timeout",              # 3-minute (configurable) idle auto-end
    "session_error",             # error mid-session
)

SPECIALIST_MESSAGE_ROLES = (
    "user",         # the employee
    "specialist",   # the IT specialist
    "system",       # bot-emitted message (e.g. idle warning, end notice)
)


class SpecialistChatSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One live conversation between an employee and an IT specialist."""

    __tablename__ = "specialist_chat_sessions"

    # ── Foreign keys ────────────────────────────────────────────────────
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id"), index=True,
    )
    # The employee on the other end. Stored so we can build the
    # transcript-with-user-details audit export without joining users every
    # time.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True,
    )
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    specialist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True,
    )
    specialist_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    specialist_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # If this live chat continues a prior AI support session, link it for
    # the full audit chain: ai-chat → ticket → live-chat.
    ai_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("support_sessions.id"), nullable=True,
    )

    # ── Lifecycle ──────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        Enum(*SPECIALIST_CHAT_STATUSES, name="specialist_chat_status"),
        default="active",
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
        index=True,
    )
    idle_warning_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    end_reason: Mapped[str | None] = mapped_column(
        Enum(*SPECIALIST_CHAT_END_REASONS, name="specialist_chat_end_reason"),
        nullable=True,
    )
    ended_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )

    # ── Resolution metadata ────────────────────────────────────────────
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_to_knowledge_review: Mapped[bool] = mapped_column(Boolean, default=False)
    knowledge_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_candidates.id"), nullable=True,
    )

    # Tunable thresholds (seconds). Defaulted in the service but persisted
    # so per-session override is possible (e.g. critical incidents keep the
    # session longer).
    idle_warning_seconds: Mapped[int] = mapped_column(Integer, default=120)  # 2 min
    idle_end_seconds: Mapped[int] = mapped_column(Integer, default=180)      # 3 min

    # Free-form snapshot of context at the end (for export / learning).
    final_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    messages: Mapped[list["SpecialistChatMessage"]] = relationship(
        back_populates="session", order_by="SpecialistChatMessage.created_at",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # Quick lookup of "the one active session for this ticket" — useful
        # for resume-after-reconnect and for the my-assigned page.
        Index(
            "ix_specialist_chat_active_per_ticket",
            "ticket_id",
            postgresql_where=(status.in_(("active", "idle_warning"))),
            unique=True,
        ),
        # Specialist's active sessions — drives the "My Assigned" view.
        Index(
            "ix_specialist_chat_specialist_active",
            "specialist_id", "status",
        ),
    )


class SpecialistChatMessage(UUIDPrimaryKeyMixin, Base):
    """One message in a live specialist chat. Immutable once written."""

    __tablename__ = "specialist_chat_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("specialist_chat_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    role: Mapped[str] = mapped_column(
        Enum(*SPECIALIST_MESSAGE_ROLES, name="specialist_message_role"),
    )
    content: Mapped[str] = mapped_column(Text)
    # System-event sub-type (e.g. 'idle_warning', 'session_ended') for
    # filtering / styling without parsing content.
    system_event: Mapped[str | None] = mapped_column(String(80), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
        index=True,
    )

    session: Mapped["SpecialistChatSession"] = relationship(back_populates="messages")
