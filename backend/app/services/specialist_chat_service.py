"""Live specialist-chat service — start, message, end, idle-sweep.

This service owns the *human-to-human* leg after the AI handoff. It is
designed around three invariants:

1. **Every transition writes an audit event.** Start, every message (with
   role + content hash), end, and any auto-action by the idle sweeper.
   Auditors can replay the entire interaction.
2. **Idle is deterministic, not "magical".** The service exposes a single
   ``check_and_apply_idle`` method that does the time math against
   ``last_activity_at``. Any caller (the GET-state polling endpoint, a
   background sweeper, or a test) gets the same answer. No hidden timers.
3. **Endings are explicit and typed.** Five reasons total:
   ``resolved``, ``user_left``, ``specialist_ended``, ``idle_timeout``,
   ``session_error``. The state never silently flips back to active.

The service does NOT commit — callers control the transaction (typically
the route handler). Every public method is async.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.specialist_chat import (
    SpecialistChatMessage,
    SpecialistChatSession,
)
from app.services.audit_service import AuditService

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.auth import User
    from app.models.ticket import Ticket

logger = get_logger(__name__)


@dataclass(frozen=True)
class IdleEvaluation:
    """The result of the idle check — pure value object for tests + logs."""

    is_idle_warning: bool
    is_idle_end: bool
    seconds_since_activity: float


class LiveChatStateError(RuntimeError):
    """The session is not in a state where this action is permitted."""


class LiveChatPermissionError(PermissionError):
    """Caller is not the user or specialist on this session."""


class SpecialistChatService:
    """Live chat between an employee and an IT specialist."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.audit = AuditService(db)

    # ── Start ──────────────────────────────────────────────────────────

    async def start(
        self,
        *,
        ticket: Ticket,
        specialist: User,
        user: User,
        ai_session_id: uuid.UUID | None = None,
        idle_warning_seconds: int = 120,
        idle_end_seconds: int = 180,
    ) -> SpecialistChatSession:
        """Start a live chat after the specialist has claimed the ticket.

        Enforces "one active session per ticket" via the unique partial
        index in the schema; an IntegrityError on insert means another
        session is already active and we return the existing one.
        """
        now = datetime.now(UTC)
        session = SpecialistChatSession(
            ticket_id=ticket.id,
            user_id=user.id,
            user_email=getattr(user, "email", None),
            user_name=getattr(user, "full_name", None),
            specialist_id=specialist.id,
            specialist_email=getattr(specialist, "email", None),
            specialist_name=getattr(specialist, "full_name", None),
            ai_session_id=ai_session_id,
            status="active",
            started_at=now,
            last_activity_at=now,
            idle_warning_seconds=idle_warning_seconds,
            idle_end_seconds=idle_end_seconds,
        )
        self.db.add(session)
        try:
            await self.db.flush()
        except IntegrityError:
            # Active session already exists for this ticket — resume it.
            await self.db.rollback()
            existing = await self._get_active_for_ticket(ticket.id)
            if existing is None:
                raise
            return existing

        await self._append_system_message(
            session,
            content=(
                f"You're now connected with {specialist.full_name or 'an IT specialist'}. "
                f"They have the full context of your conversation so far."
            ),
            event="session_started",
        )

        await self.audit.log(
            action="specialist_chat.started",
            resource_type="specialist_chat_session",
            resource_id=str(session.id),
            actor=specialist,
            session_id=session.id,
            new_value={
                "ticket_id": str(ticket.id),
                "ticket_number": ticket.ticket_number,
                "user_id": str(user.id),
                "specialist_id": str(specialist.id),
                "idle_end_seconds": idle_end_seconds,
            },
        )
        logger.info(
            "specialist_chat_started",
            session_id=str(session.id),
            ticket_number=ticket.ticket_number,
            specialist_id=str(specialist.id),
        )
        return session

    # ── Messaging ──────────────────────────────────────────────────────

    async def send_message(
        self,
        session_id: uuid.UUID,
        *,
        sender: User,
        content: str,
    ) -> SpecialistChatMessage:
        """Post a message. Role is derived from sender_id (user vs specialist).

        Bumps ``last_activity_at``. If the session was in ``idle_warning``,
        flips it back to ``active`` (the user/specialist came back).
        """
        session = await self._load(session_id)
        if not _is_participant(session, sender):
            raise LiveChatPermissionError(
                "Only the user or assigned specialist may post messages"
            )
        if session.status.startswith("ended"):
            raise LiveChatStateError(
                f"Cannot post to a {session.status} session"
            )

        role = "user" if sender.id == session.user_id else "specialist"
        msg = SpecialistChatMessage(
            session_id=session.id,
            sender_id=sender.id,
            role=role,
            content=content,
        )
        self.db.add(msg)

        now = datetime.now(UTC)
        session.last_activity_at = now
        if session.status == "idle_warning":
            # Activity returned — clear the warning.
            session.status = "active"
            session.idle_warning_at = None

        await self.db.flush()

        await self.audit.log(
            action="specialist_chat.message_sent",
            resource_type="specialist_chat_session",
            resource_id=str(session.id),
            actor=sender,
            session_id=session.id,
            metadata={
                "role": role,
                "message_id": str(msg.id),
                # Hash, not content — keeps audit storage small + redacts on log
                # while transcript table holds the verbatim message.
                "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "content_length": len(content),
            },
        )
        return msg

    async def append_system_message(
        self, session_id: uuid.UUID, *, content: str, event: str,
    ) -> SpecialistChatMessage:
        """Public wrapper for inserting a system message (idle warning, etc.)."""
        session = await self._load(session_id)
        return await self._append_system_message(session, content=content, event=event)

    async def _append_system_message(
        self,
        session: SpecialistChatSession,
        *,
        content: str,
        event: str,
    ) -> SpecialistChatMessage:
        msg = SpecialistChatMessage(
            session_id=session.id,
            sender_id=None,
            role="system",
            content=content,
            system_event=event,
        )
        self.db.add(msg)
        await self.db.flush()
        return msg

    # ── End ────────────────────────────────────────────────────────────

    async def end(
        self,
        session_id: uuid.UUID,
        *,
        actor: User | None,
        reason: str,
        resolution_notes: str | None = None,
    ) -> SpecialistChatSession:
        """End the session with a typed reason.

        ``actor`` may be None when the system ends the session (idle timeout,
        error). When set, the actor must be the user (→ ``user_left``) or
        the specialist (→ ``specialist_ended`` / ``resolved``).
        """
        session = await self._load(session_id)
        if session.status.startswith("ended"):
            return session  # idempotent

        if actor is not None and not _is_participant(session, actor):
            raise LiveChatPermissionError(
                "Only the user or assigned specialist may end this session"
            )

        now = datetime.now(UTC)
        new_status = _status_for_reason(reason)
        old_status = session.status
        session.status = new_status
        session.end_reason = reason
        session.ended_at = now
        session.ended_by = actor.id if actor is not None else None
        session.resolution_notes = resolution_notes or session.resolution_notes
        session.last_activity_at = now

        await self._append_system_message(
            session,
            content=_end_message_for_reason(reason),
            event=f"session_{new_status}",
        )
        await self.db.flush()

        await self.audit.log(
            action="specialist_chat.ended",
            resource_type="specialist_chat_session",
            resource_id=str(session.id),
            actor=actor,
            session_id=session.id,
            old_value={"status": old_status},
            new_value={
                "status": new_status,
                "end_reason": reason,
                "ended_by": str(actor.id) if actor else None,
            },
            severity="info" if reason == "resolved" else "info",
        )
        logger.info(
            "specialist_chat_ended",
            session_id=str(session.id),
            reason=reason,
            actor=str(actor.id) if actor else "system",
        )
        return session

    # ── Idle handling ──────────────────────────────────────────────────

    def evaluate_idle(
        self,
        session: SpecialistChatSession,
        *,
        now: datetime | None = None,
    ) -> IdleEvaluation:
        """Pure-function idle check (no DB write). Used by the polling endpoint
        and by the background sweeper alike."""
        now = now or datetime.now(UTC)
        delta = (now - session.last_activity_at).total_seconds()
        return IdleEvaluation(
            is_idle_warning=delta >= session.idle_warning_seconds,
            is_idle_end=delta >= session.idle_end_seconds,
            seconds_since_activity=delta,
        )

    async def check_and_apply_idle(
        self, session: SpecialistChatSession,
    ) -> SpecialistChatSession:
        """Apply idle rules. Mutates session + writes audit events.

        * If past ``idle_end_seconds`` → end with reason ``idle_timeout``.
        * Else if past ``idle_warning_seconds`` AND status is still
          ``active`` → flip to ``idle_warning`` and post a "still there?"
          system message.
        * Else no-op.
        """
        if session.status.startswith("ended"):
            return session

        ev = self.evaluate_idle(session)
        if ev.is_idle_end:
            return await self.end(
                session.id, actor=None, reason="idle_timeout",
                resolution_notes=None,
            )
        if ev.is_idle_warning and session.status == "active":
            session.status = "idle_warning"
            session.idle_warning_at = datetime.now(UTC)
            await self._append_system_message(
                session,
                content=(
                    "It's been quiet for a couple of minutes. Are you still there? "
                    "The chat will end automatically if there's no reply soon."
                ),
                event="idle_warning",
            )
            await self.db.flush()
            await self.audit.log(
                action="specialist_chat.idle_warning",
                resource_type="specialist_chat_session",
                resource_id=str(session.id),
                actor=None,
                session_id=session.id,
                metadata={"seconds_since_activity": ev.seconds_since_activity},
            )
        return session

    async def sweep_idle(self, batch_limit: int = 200) -> int:
        """Background-worker entry point: end all sessions past their idle
        threshold. Returns the count ended.

        Phase 1 has no scheduler — call this from a cron / scheduler later.
        For now the polling endpoint also runs the check, so users see the
        right state the next time they fetch.
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=60)
        stmt = (
            select(SpecialistChatSession)
            .where(
                and_(
                    SpecialistChatSession.status.in_(("active", "idle_warning")),
                    SpecialistChatSession.last_activity_at <= cutoff,
                )
            )
            .limit(batch_limit)
        )
        result = await self.db.execute(stmt)
        sessions = list(result.scalars().all())
        ended = 0
        for s in sessions:
            ev = self.evaluate_idle(s)
            if ev.is_idle_end:
                await self.end(s.id, actor=None, reason="idle_timeout")
                ended += 1
            elif ev.is_idle_warning and s.status == "active":
                await self.check_and_apply_idle(s)
        return ended

    # ── Reads ──────────────────────────────────────────────────────────

    async def get_state(
        self,
        session_id: uuid.UUID,
        *,
        caller: User,
        run_idle_check: bool = True,
    ) -> SpecialistChatSession:
        """Fetch the session + messages.

        ``run_idle_check`` lets the polling endpoint apply idle rules
        lazily without needing a background worker.
        """
        session = await self._load(session_id, with_messages=True)
        if not _is_participant(session, caller) and not _is_admin(caller):
            raise LiveChatPermissionError("Not a participant in this session")
        if run_idle_check:
            session = await self.check_and_apply_idle(session)
            # If the idle check ended the session, reload messages to include
            # the system "ended" notice we just appended.
            if session.status.startswith("ended"):
                session = await self._load(session.id, with_messages=True)
        return session

    async def list_active_for_specialist(
        self, specialist_id: uuid.UUID,
    ) -> list[SpecialistChatSession]:
        stmt = (
            select(SpecialistChatSession)
            .where(
                and_(
                    SpecialistChatSession.specialist_id == specialist_id,
                    SpecialistChatSession.status.in_(("active", "idle_warning")),
                )
            )
            .order_by(SpecialistChatSession.last_activity_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_transcript(
        self, session_id: uuid.UUID,
    ) -> list[SpecialistChatMessage]:
        session = await self._load(session_id, with_messages=True)
        return list(session.messages)

    # ── Internals ──────────────────────────────────────────────────────

    async def _load(
        self, session_id: uuid.UUID, *, with_messages: bool = False,
    ) -> SpecialistChatSession:
        stmt = select(SpecialistChatSession).where(
            SpecialistChatSession.id == session_id
        )
        if with_messages:
            stmt = stmt.options(selectinload(SpecialistChatSession.messages))
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()
        if session is None:
            raise LookupError(f"Specialist chat session {session_id} not found")
        return session

    async def get_active_for_participant(
        self, user_id: uuid.UUID,
    ) -> SpecialistChatSession | None:
        """Most-recent non-ended session where this user is a participant.

        Powers the employee "an IT specialist has joined — open chat" banner:
        the employee polls this after escalation and is routed into the live
        chat the moment the specialist starts it.
        """
        stmt = (
            select(SpecialistChatSession)
            .where(
                and_(
                    or_(
                        SpecialistChatSession.user_id == user_id,
                        SpecialistChatSession.specialist_id == user_id,
                    ),
                    SpecialistChatSession.status.in_(("active", "idle_warning")),
                )
            )
            .order_by(SpecialistChatSession.started_at.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _get_active_for_ticket(
        self, ticket_id: uuid.UUID,
    ) -> SpecialistChatSession | None:
        stmt = (
            select(SpecialistChatSession)
            .where(
                and_(
                    SpecialistChatSession.ticket_id == ticket_id,
                    or_(
                        SpecialistChatSession.status == "active",
                        SpecialistChatSession.status == "idle_warning",
                    ),
                )
            )
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()


# ── helpers ────────────────────────────────────────────────────────────


def _is_participant(session: SpecialistChatSession, actor: User) -> bool:
    return actor.id in (session.user_id, session.specialist_id)


def _is_admin(actor: User) -> bool:
    roles = set(getattr(actor, "role_names", None) or [])
    return bool(roles & {"it_admin", "it_lead", "security_auditor"})


def _status_for_reason(reason: str) -> str:
    return {
        "resolved": "ended_by_specialist",
        "specialist_ended": "ended_by_specialist",
        "user_left": "ended_by_user",
        "idle_timeout": "ended_by_timeout",
        "session_error": "ended_by_system",
    }.get(reason, "ended_by_system")


def _end_message_for_reason(reason: str) -> str:
    return {
        "resolved": "The IT specialist marked this as resolved. Thanks for chatting!",
        "specialist_ended": "The IT specialist has ended this chat.",
        "user_left": "You ended this chat.",
        "idle_timeout": (
            "The chat ended automatically due to inactivity. "
            "Start a new chat anytime if you need more help."
        ),
        "session_error": "The chat ended unexpectedly. Please reach out again.",
    }.get(reason, "Chat ended.")


__all__ = [
    "IdleEvaluation",
    "LiveChatPermissionError",
    "LiveChatStateError",
    "SpecialistChatService",
]
