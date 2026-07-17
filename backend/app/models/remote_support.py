"""Remote support session models — orchestration layer for enterprise remote assistance.

Design notes:
    - Sessions are NEVER raw screen-share infrastructure; they are metadata
      records that track orchestrated sessions in external tools (e.g. MS Remote Help).
    - Employee consent is mandatory and cryptographically timestamped.
    - Every status transition is recorded in RemoteSessionEvent for audit.
    - Consent can be revoked at any time; revocation terminates the session.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# ── Status / Type Enumerations ────────────────────────────────────────

REMOTE_SESSION_STATUSES = (
    "requested",  # Agent has requested a session
    "consent_pending",  # Consent notification sent to employee
    "consent_granted",  # Employee approved — ready to launch
    "consent_denied",  # Employee rejected
    "connecting",  # Provider session being established
    "active",  # Session in progress
    "paused",  # Temporarily suspended
    "completed",  # Ended normally with resolution
    "terminated",  # Force-ended (timeout, revocation, admin)
    "expired",  # Consent window or session timeout elapsed
)

REMOTE_SESSION_TYPES = (
    "screen_view",  # View only — agent cannot control
    "screen_control",  # Full control — requires elevated permission
)

CONSENT_TYPES = (
    "screen_view",  # Consent to view screen
    "screen_control",  # Consent to control mouse/keyboard
)

TERMINATION_REASONS = (
    "completed",  # Normal end of session
    "employee_revoked",  # Employee withdrew consent mid-session
    "employee_denied",  # Employee denied initial consent
    "agent_ended",  # Agent explicitly ended session
    "admin_terminated",  # Admin force-terminated
    "timeout",  # Session exceeded max duration
    "consent_expired",  # Consent window elapsed without response
    "provider_error",  # External provider returned an error
    "policy_violation",  # Policy check failed during session
)

SESSION_EVENT_TYPES = (
    "requested",
    "consent_sent",
    "consent_granted",
    "consent_denied",
    "session_launched",
    "session_connected",
    "session_paused",
    "session_resumed",
    "consent_revoked",
    "session_ended",
    "resolution_added",
    "status_updated",
)


# ── Models ────────────────────────────────────────────────────────────


class RemoteSupportSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Remote assistance session — lifecycle tracking for attended remote support.

    This record is the authoritative source of truth for a remote session.
    The external provider (e.g. Microsoft Remote Help) handles the actual
    screen sharing; we only store orchestration metadata here.
    """

    __tablename__ = "remote_support_sessions"

    # ── Participants ──
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        index=True,
        comment="Employee receiving support",
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        index=True,
        comment="IT agent providing support",
    )
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tickets.id"),
        nullable=True,
        comment="Associated support ticket (optional)",
    )
    support_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("support_sessions.id"),
        nullable=True,
        comment="Chat session this remote session originated from",
    )

    # ── Session Configuration ──
    session_type: Mapped[str] = mapped_column(
        Enum(*REMOTE_SESSION_TYPES, name="remote_session_type"),
        default="screen_view",
    )
    status: Mapped[str] = mapped_column(
        Enum(*REMOTE_SESSION_STATUSES, name="remote_session_status"),
        default="requested",
        index=True,
    )

    # ── Provider Details ──
    provider: Mapped[str] = mapped_column(
        String(100),
        default="microsoft_remote_help",
        comment="Remote support provider identifier",
    )
    provider_session_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Session ID assigned by external provider",
    )
    join_url_agent: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="Deep-link URL for agent to launch the remote tool",
    )
    join_url_employee: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="Deep-link URL for employee to accept in the remote tool",
    )
    join_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Numeric join code for employee (if provider uses codes)",
    )

    # ── Timing ──
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    consent_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When consent notification was sent to employee",
    )
    consent_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Consent must be given by this time or session expires",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    max_duration_minutes: Mapped[int] = mapped_column(
        Integer,
        default=30,
        comment="Hard cap on session duration; enforced by background worker",
    )

    # ── Policy & Justification ──
    justification: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Agent-provided reason for requesting remote access",
    )
    policy_check_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    termination_reason: Mapped[str | None] = mapped_column(
        Enum(*TERMINATION_REASONS, name="termination_reason"),
        nullable=True,
    )

    # ── Post-Session ──
    resolution_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="What was done / resolved during the session",
    )
    actions_taken: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Structured list of actions performed",
    )
    provider_metadata: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Raw metadata returned by external provider",
    )

    # ── Relationships ──
    consents: Mapped[list["RemoteSupportConsent"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    events: Mapped[list["RemoteSessionEvent"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="RemoteSessionEvent.occurred_at",
    )

    @property
    def duration_seconds(self) -> int | None:
        """Compute session duration if started and ended."""
        if self.started_at and self.ended_at:
            return int((self.ended_at - self.started_at).total_seconds())
        return None

    @property
    def active_consent(self) -> "RemoteSupportConsent | None":
        """Return the most recent non-revoked consent, if any."""
        for c in sorted(self.consents, key=lambda x: x.consented_at, reverse=True):
            if c.granted and not c.revoked_at:
                return c
        return None


class RemoteSupportConsent(UUIDPrimaryKeyMixin, Base):
    """Explicit employee consent record — immutable audit artifact.

    Each consent grant or denial is a separate row. Revocations add
    a revoked_at timestamp without deleting the original record.
    This preserves a full audit trail of all consent decisions.
    """

    __tablename__ = "remote_support_consents"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("remote_support_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
    )
    consent_type: Mapped[str] = mapped_column(
        Enum(*CONSENT_TYPES, name="consent_type"),
    )

    # ── Decision ──
    granted: Mapped[bool] = mapped_column(
        Boolean,
        comment="True = granted, False = denied",
    )
    consented_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        comment="Immutable timestamp of consent decision",
    )
    consent_text_shown: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Exact consent notice text shown to employee at time of consent",
    )

    # ── Revocation ──
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When employee revoked consent (mid-session)",
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # ── Context ──
    ip_address: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="IP address of employee at consent time",
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    denial_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Optional reason given when denying consent",
    )

    session: Mapped["RemoteSupportSession"] = relationship(back_populates="consents")


class RemoteSessionEvent(UUIDPrimaryKeyMixin, Base):
    """Immutable audit event log for a remote session lifecycle.

    Every status transition and significant action is recorded here.
    These records are append-only and must never be deleted.
    """

    __tablename__ = "remote_session_events"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("remote_support_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        Enum(*SESSION_EVENT_TYPES, name="session_event_type"),
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        comment="User who triggered this event",
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # NOTE: Cannot use 'metadata' — reserved by SQLAlchemy DeclarativeBase.
    # Python attribute is 'context_data'; DB column is 'event_metadata'.
    context_data: Mapped[dict | None] = mapped_column(
        "event_metadata",
        JSONB,
        nullable=True,
        comment="Structured event context (old_status, new_status, etc.)",
    )
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)

    session: Mapped["RemoteSupportSession"] = relationship(back_populates="events")
