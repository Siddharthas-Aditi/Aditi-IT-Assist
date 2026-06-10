"""Remote support service — orchestration with consent enforcement and audit trail.

This service is the single entry point for all remote session operations.
It enforces:
  1. Permission checks (agent role, session type caps)
  2. Consent collection before any session can launch
  3. Immutable audit event recording on every transition
  4. Policy enforcement (max duration, consent deadline, revocation)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.auth import User
from app.models.remote_support import (
    RemoteSessionEvent,
    RemoteSupportConsent,
    RemoteSupportSession,
)
from app.services.remote_support.providers.base import (
    RemoteSupportProvider,
    SessionCapability,
)
from app.services.remote_support.providers.microsoft_remote_help import (
    MicrosoftRemoteHelpProvider,
)

logger = structlog.get_logger()

# Consent notice shown verbatim to the employee
_CONSENT_NOTICE_SCREEN_VIEW = (
    "An IT support agent has requested to view your screen to assist with your "
    "support request. During this session, the agent will be able to see everything "
    "on your screen. You can end the session at any time by clicking the "
    "\"End Session\" button. Your consent is voluntary."
)

_CONSENT_NOTICE_SCREEN_CONTROL = (
    "An IT support agent has requested to take control of your screen and keyboard "
    "to assist with your support request. During this session, the agent will be able "
    "to see and interact with your screen. You can end the session at any time by "
    "clicking the \"End Session\" button. Your consent is voluntary."
)

CONSENT_NOTICES: dict[str, str] = {
    "screen_view": _CONSENT_NOTICE_SCREEN_VIEW,
    "screen_control": _CONSENT_NOTICE_SCREEN_CONTROL,
}

# Consent window — employee must respond within this period
CONSENT_WINDOW_MINUTES = 10


class RemoteSupportError(Exception):
    """Base error for remote support operations."""


class ConsentRequired(RemoteSupportError):
    """Session cannot proceed without explicit employee consent."""


class PolicyViolation(RemoteSupportError):
    """Request violates session policy."""


class SessionNotFound(RemoteSupportError):
    """Session does not exist or is not accessible."""


class InvalidTransition(RemoteSupportError):
    """The requested status transition is not allowed."""


# ── Valid status transitions ──────────────────────────────────────────
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "requested": {"consent_pending", "terminated"},
    "consent_pending": {"consent_granted", "consent_denied", "expired"},
    "consent_granted": {"connecting", "terminated"},
    "consent_denied": set(),       # terminal
    "connecting": {"active", "terminated"},
    "active": {"paused", "completed", "terminated"},
    "paused": {"active", "completed", "terminated"},
    "completed": set(),            # terminal
    "terminated": set(),           # terminal
    "expired": set(),              # terminal
}


def _assert_transition(current: str, target: str) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidTransition(
            f"Cannot transition from '{current}' to '{target}'"
        )


class RemoteSupportService:
    """Orchestrates remote assistance workflows with full consent and audit enforcement."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._providers: dict[str, RemoteSupportProvider] = self._build_providers()

    # ── Public API ────────────────────────────────────────────────────

    async def request_session(
        self,
        *,
        agent: User,
        employee_id: uuid.UUID,
        session_type: str = "screen_view",
        ticket_id: uuid.UUID | None = None,
        support_session_id: uuid.UUID | None = None,
        justification: str | None = None,
        max_duration_minutes: int = 30,
        ip_address: str | None = None,
    ) -> RemoteSupportSession:
        """IT agent requests a remote support session.

        Enforces:
            - Agent must have correct role for session_type
            - screen_control requires it_lead or above
            - Justification required for screen_control
        """
        self._enforce_request_policy(agent, session_type, justification)

        provider = self._resolve_provider()
        consent_deadline = datetime.now(timezone.utc) + timedelta(
            minutes=CONSENT_WINDOW_MINUTES
        )

        session = RemoteSupportSession(
            employee_id=employee_id,
            agent_id=agent.id,
            ticket_id=ticket_id,
            support_session_id=support_session_id,
            session_type=session_type,
            status="requested",
            provider=provider.provider_name,
            justification=justification,
            policy_check_passed=True,
            max_duration_minutes=max_duration_minutes,
            consent_deadline=consent_deadline,
        )
        self.db.add(session)
        await self.db.flush()

        await self._record_event(
            session=session,
            event_type="requested",
            actor_id=agent.id,
            description=f"Remote {session_type} session requested by {agent.full_name}",
            ip_address=ip_address,
        )

        logger.info(
            "remote_session_requested",
            session_id=str(session.id),
            agent_email=agent.email,
            employee_id=str(employee_id),
            session_type=session_type,
        )
        return session

    async def send_consent_request(
        self,
        session_id: uuid.UUID,
        agent: User,
    ) -> RemoteSupportSession:
        """Mark consent as sent and transition to consent_pending.

        In a real system this would trigger a WebSocket push or
        email/notification to the employee.
        """
        session = await self._get_or_raise(session_id)
        self._assert_agent(session, agent)
        _assert_transition(session.status, "consent_pending")

        session.status = "consent_pending"
        session.consent_sent_at = datetime.now(timezone.utc)

        await self._record_event(
            session=session,
            event_type="consent_sent",
            actor_id=agent.id,
            description="Consent notification sent to employee",
        )
        return session

    async def grant_consent(
        self,
        *,
        session_id: uuid.UUID,
        employee: User,
        granted: bool,
        denial_reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[RemoteSupportSession, RemoteSupportConsent]:
        """Employee grants or denies consent for a remote session.

        The consent record is immutable once written — revocation adds
        a revoked_at timestamp via revoke_consent().
        """
        session = await self._get_or_raise(session_id)

        # Only the target employee can respond
        if session.employee_id != employee.id:
            raise PolicyViolation("Only the target employee can respond to this consent request")

        # Check consent window hasn't expired
        if session.consent_deadline and datetime.now(timezone.utc) > session.consent_deadline:
            await self._expire_session(session)
            raise PolicyViolation("Consent window has expired")

        target_status = "consent_granted" if granted else "consent_denied"
        _assert_transition(session.status, target_status)

        consent = RemoteSupportConsent(
            session_id=session.id,
            employee_id=employee.id,
            consent_type=session.session_type,
            granted=granted,
            consent_text_shown=CONSENT_NOTICES.get(session.session_type, ""),
            ip_address=ip_address,
            user_agent=user_agent,
            denial_reason=denial_reason if not granted else None,
        )
        self.db.add(consent)
        session.status = target_status

        event_type = "consent_granted" if granted else "consent_denied"
        await self._record_event(
            session=session,
            event_type=event_type,
            actor_id=employee.id,
            description=f"Employee {'granted' if granted else 'denied'} {session.session_type} consent",
            metadata={"denial_reason": denial_reason} if denial_reason else None,
            ip_address=ip_address,
        )

        logger.info(
            "remote_consent_decision",
            session_id=str(session_id),
            employee_email=employee.email,
            granted=granted,
        )
        return session, consent

    async def launch_session(
        self,
        session_id: uuid.UUID,
        agent: User,
    ) -> RemoteSupportSession:
        """Launch the remote session via the external provider.

        Requires consent_granted. Returns join URLs embedded in the session.
        """
        session = await self._get_or_raise(session_id)
        self._assert_agent(session, agent)
        _assert_transition(session.status, "connecting")

        if not session.active_consent:
            raise ConsentRequired("Employee consent has not been granted")

        # Get employee user for display name
        from sqlalchemy import select as sa_select
        employee_result = await self.db.execute(
            sa_select(User).where(User.id == session.employee_id)
        )
        employee = employee_result.scalar_one_or_none()

        provider = self._resolve_provider(session.provider)
        capabilities = [
            SessionCapability(session.session_type)
        ]

        provider_info = await provider.create_session(
            agent_id=str(agent.id),
            agent_name=agent.full_name,
            employee_id=str(session.employee_id),
            employee_name=employee.full_name if employee else "Employee",
            session_type=session.session_type,
            capabilities=capabilities,
            ticket_id=str(session.ticket_id) if session.ticket_id else None,
        )

        session.status = "connecting"
        session.provider_session_id = provider_info.provider_session_id
        session.join_url_agent = provider_info.join_url_agent
        session.join_url_employee = provider_info.join_url_employee
        session.join_code = provider_info.join_code
        session.provider_metadata = provider_info.provider_metadata

        await self._record_event(
            session=session,
            event_type="session_launched",
            actor_id=agent.id,
            description=f"Session launched via {provider.display_name}",
            metadata={
                "provider_session_id": provider_info.provider_session_id,
                "capabilities": [c.value for c in provider_info.capabilities_granted],
            },
        )

        logger.info(
            "remote_session_launched",
            session_id=str(session_id),
            provider_session_id=provider_info.provider_session_id,
            provider=provider.provider_name,
        )
        return session

    async def mark_connected(
        self,
        session_id: uuid.UUID,
        actor: User,
    ) -> RemoteSupportSession:
        """Mark session as actively connected (agent joined the provider session)."""
        session = await self._get_or_raise(session_id)
        _assert_transition(session.status, "active")

        session.status = "active"
        session.started_at = datetime.now(timezone.utc)

        await self._record_event(
            session=session,
            event_type="session_connected",
            actor_id=actor.id,
            description="Remote session is now active",
        )
        return session

    async def revoke_consent(
        self,
        *,
        session_id: uuid.UUID,
        employee: User,
        reason: str | None = None,
        ip_address: str | None = None,
    ) -> RemoteSupportSession:
        """Employee revokes consent mid-session — terminates session immediately."""
        session = await self._get_or_raise(session_id)

        if session.employee_id != employee.id:
            raise PolicyViolation("Only the employee can revoke their own consent")

        # Mark active consent as revoked
        if session.active_consent:
            session.active_consent.revoked_at = datetime.now(timezone.utc)
            session.active_consent.revocation_reason = reason

        # Terminate with provider if active
        if session.provider_session_id and session.status in ("connecting", "active", "paused"):
            provider = self._resolve_provider(session.provider)
            await provider.terminate_session(session.provider_session_id)

        session.status = "terminated"
        session.ended_at = datetime.now(timezone.utc)
        session.termination_reason = "employee_revoked"

        await self._record_event(
            session=session,
            event_type="consent_revoked",
            actor_id=employee.id,
            description=f"Employee revoked consent: {reason or 'no reason given'}",
            ip_address=ip_address,
        )

        logger.warning(
            "remote_consent_revoked",
            session_id=str(session_id),
            employee_email=employee.email,
        )
        return session

    async def end_session(
        self,
        *,
        session_id: uuid.UUID,
        actor: User,
        resolution_notes: str | None = None,
        actions_taken: list[str] | None = None,
        reason: str = "completed",
    ) -> RemoteSupportSession:
        """End a remote session normally (agent or employee)."""
        session = await self._get_or_raise(session_id)

        # Agent or employee may end; admin can terminate any session
        actor_roles = set(actor.role_names)
        is_participant = (
            session.agent_id == actor.id or session.employee_id == actor.id
        )
        is_admin = bool(actor_roles.intersection({"it_admin", "it_lead"}))

        if not is_participant and not is_admin:
            raise PolicyViolation("Only session participants or admins can end sessions")

        target_status = "completed" if reason == "completed" else "terminated"
        _assert_transition(session.status, target_status)

        # Terminate with provider
        if session.provider_session_id:
            provider = self._resolve_provider(session.provider)
            await provider.terminate_session(session.provider_session_id)

        session.status = target_status
        session.ended_at = datetime.now(timezone.utc)
        session.termination_reason = reason
        if resolution_notes:
            session.resolution_notes = resolution_notes
        if actions_taken:
            session.actions_taken = actions_taken

        await self._record_event(
            session=session,
            event_type="session_ended",
            actor_id=actor.id,
            description=f"Session ended by {actor.full_name} ({reason})",
            metadata={"resolution_notes_added": bool(resolution_notes)},
        )

        logger.info(
            "remote_session_ended",
            session_id=str(session_id),
            actor_email=actor.email,
            duration_seconds=session.duration_seconds,
            reason=reason,
        )
        return session

    async def update_resolution_notes(
        self,
        *,
        session_id: uuid.UUID,
        agent: User,
        resolution_notes: str,
        actions_taken: list[str] | None = None,
    ) -> RemoteSupportSession:
        """Update resolution notes after a session ends."""
        session = await self._get_or_raise(session_id)

        if session.agent_id != agent.id and "it_admin" not in agent.role_names:
            raise PolicyViolation("Only the session agent can update resolution notes")

        if session.status not in ("completed", "terminated"):
            raise InvalidTransition("Resolution notes can only be set after session ends")

        session.resolution_notes = resolution_notes
        if actions_taken is not None:
            session.actions_taken = actions_taken

        await self._record_event(
            session=session,
            event_type="resolution_added",
            actor_id=agent.id,
            description="Resolution notes updated",
        )
        return session

    async def get_session(
        self, session_id: uuid.UUID, viewer: User
    ) -> RemoteSupportSession:
        """Get a session, enforcing visibility rules."""
        session = await self._get_or_raise(session_id)
        viewer_roles = set(viewer.role_names)

        # Participants can always see their own session
        if session.agent_id == viewer.id or session.employee_id == viewer.id:
            return session
        # IT leads / admins / auditors can see all
        if viewer_roles.intersection({"it_lead", "it_admin", "security_auditor"}):
            return session

        raise PolicyViolation("You do not have access to this session")

    async def list_sessions(
        self,
        viewer: User,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RemoteSupportSession]:
        """List sessions visible to the viewer."""

        viewer_roles = set(viewer.role_names)
        stmt = select(RemoteSupportSession)

        if viewer_roles.intersection({"it_lead", "it_admin", "security_auditor"}):
            # Can see all sessions
            pass
        elif "it_agent" in viewer_roles:
            # Agent sees their own assigned sessions
            stmt = stmt.where(RemoteSupportSession.agent_id == viewer.id)
        else:
            # Employee sees their own sessions
            stmt = stmt.where(RemoteSupportSession.employee_id == viewer.id)

        if status:
            stmt = stmt.where(RemoteSupportSession.status == status)

        stmt = (
            stmt.order_by(RemoteSupportSession.requested_at.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_consent_notification(
        self, session_id: uuid.UUID, employee: User
    ) -> dict[str, Any]:
        """Build the consent notification payload for the employee consent modal."""
        session = await self._get_or_raise(session_id)

        if session.employee_id != employee.id:
            raise PolicyViolation("This consent request is not for you")

        # Fetch agent name
        agent_result = await self.db.execute(
            select(User).where(User.id == session.agent_id)
        )
        agent = agent_result.scalar_one_or_none()

        type_labels = {"screen_view": "View Only", "screen_control": "Full Control"}

        return {
            "session_id": str(session.id),
            "agent_name": agent.full_name if agent else "IT Support Agent",
            "agent_email": agent.email if agent else "",
            "session_type": session.session_type,
            "session_type_label": type_labels.get(session.session_type, session.session_type),
            "justification": session.justification,
            "consent_deadline": session.consent_deadline,
            "consent_text": CONSENT_NOTICES.get(session.session_type, ""),
            "ticket_reference": str(session.ticket_id) if session.ticket_id else None,
        }

    async def poll_provider_status(
        self, session_id: uuid.UUID
    ) -> RemoteSupportSession:
        """Poll the external provider for session status and sync to our DB."""
        session = await self._get_or_raise(session_id)

        if not session.provider_session_id:
            return session

        provider = self._resolve_provider(session.provider)
        update = await provider.get_session_status(session.provider_session_id)

        # Map provider status → our status
        status_map = {
            "active": "active",
            "connecting": "connecting",
            "completed": "completed",
            "failed": "terminated",
            "expired": "expired",
        }
        new_status: str = status_map.get(update.status.value) or session.status

        if new_status != session.status:
            try:
                _assert_transition(session.status, new_status)
                session.status = new_status
                if new_status in ("completed", "terminated") and not session.ended_at:
                    session.ended_at = update.disconnected_at or datetime.now(timezone.utc)
                if new_status == "active" and not session.started_at:
                    session.started_at = update.connected_at or datetime.now(timezone.utc)

                await self._record_event(
                    session=session,
                    event_type="status_updated",
                    description=f"Status synced from provider: {new_status}",
                    metadata={"provider_status": update.status.value},
                )
            except InvalidTransition:
                pass  # Provider status diverged; don't force invalid transition

        return session

    # ── Internals ─────────────────────────────────────────────────────

    async def _get_or_raise(self, session_id: uuid.UUID) -> RemoteSupportSession:
        result = await self.db.execute(
            select(RemoteSupportSession).where(RemoteSupportSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            raise SessionNotFound(f"Session {session_id} not found")
        return session

    async def _expire_session(self, session: RemoteSupportSession) -> None:
        session.status = "expired"
        session.termination_reason = "consent_expired"
        session.ended_at = datetime.now(timezone.utc)
        await self._record_event(
            session=session,
            event_type="status_updated",
            description="Session expired: consent window elapsed",
        )

    async def _record_event(
        self,
        *,
        session: RemoteSupportSession,
        event_type: str,
        actor_id: uuid.UUID | None = None,
        description: str | None = None,
        metadata: dict | None = None,
        ip_address: str | None = None,
    ) -> None:
        event = RemoteSessionEvent(
            session_id=session.id,
            event_type=event_type,
            actor_id=actor_id,
            description=description,
            context_data=metadata,
            ip_address=ip_address,
        )
        self.db.add(event)

    @staticmethod
    def _assert_agent(session: RemoteSupportSession, agent: User) -> None:
        if session.agent_id != agent.id:
            raise PolicyViolation("Only the requesting agent can perform this action")

    @staticmethod
    def _enforce_request_policy(agent: User, session_type: str, justification: str | None) -> None:
        agent_roles = set(agent.role_names)

        if not agent_roles.intersection({"it_agent", "it_lead", "it_admin"}):
            raise PolicyViolation("Only IT staff can request remote sessions")

        if session_type == "screen_control" and not agent_roles.intersection({"it_lead", "it_admin"}):
            raise PolicyViolation("screen_control requires IT Lead or Admin role")

        if session_type == "screen_control" and not justification:
            raise PolicyViolation("Justification is required for screen_control sessions")

    def _resolve_provider(self, name: str | None = None) -> RemoteSupportProvider:
        target = name or settings.REMOTE_SUPPORT_PROVIDER
        if target not in self._providers:
            target = next(iter(self._providers))
        return self._providers[target]

    @staticmethod
    def _build_providers() -> dict[str, RemoteSupportProvider]:
        return {
            "microsoft_remote_help": MicrosoftRemoteHelpProvider(
                tenant_id=getattr(settings, "AZURE_TENANT_ID", ""),
                client_id=getattr(settings, "AZURE_CLIENT_ID", ""),
                client_secret=getattr(settings, "AZURE_CLIENT_SECRET", ""),
            ),
        }
