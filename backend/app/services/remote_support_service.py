"""Remote support service — orchestration layer for enterprise remote assistance."""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.models.remote_support import (
    RemoteSupportConsent,
    RemoteSupportSession,
)

logger = structlog.get_logger()


# ─────────────────────────────────────────────────────────────────────
# Remote Support Provider Interface
# ─────────────────────────────────────────────────────────────────────


@dataclass
class RemoteSessionInfo:
    """Information returned from the remote support provider."""

    provider_session_id: str
    join_url_agent: str | None = None
    join_url_employee: str | None = None
    status: str = "pending"


class RemoteSupportProvider(ABC):
    """Abstract interface for remote support tool integration."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier."""
        ...

    @abstractmethod
    async def create_session(
        self, agent_id: str, employee_id: str, session_type: str, **kwargs
    ) -> RemoteSessionInfo:
        """Initiate a remote support session with the provider."""
        ...

    @abstractmethod
    async def terminate_session(self, provider_session_id: str) -> bool:
        """Terminate an active remote support session."""
        ...

    @abstractmethod
    async def get_session_status(self, provider_session_id: str) -> str:
        """Query current session status from provider."""
        ...


class MicrosoftRemoteHelpAdapter(RemoteSupportProvider):
    """Adapter stub for Microsoft Intune Remote Help integration.

    In production, this will integrate with:
    - Microsoft Graph API for Remote Help
    - Intune device management APIs
    - Conditional Access policies

    Prerequisites for production:
    1. Azure AD App Registration with Remote Help permissions
    2. Intune license assignment for agents
    3. Remote Help app installed on managed devices
    4. Conditional Access policies configured
    """

    @property
    def provider_name(self) -> str:
        return "microsoft_remote_help"

    async def create_session(
        self, agent_id: str, employee_id: str, session_type: str, **kwargs
    ) -> RemoteSessionInfo:
        """Create a Remote Help session via Microsoft Graph API (stub)."""
        logger.info(
            "remote_help_create_session",
            agent_id=agent_id, employee_id=employee_id, session_type=session_type,
        )
        # Stub: In production, call Microsoft Graph API
        # POST /deviceManagement/remoteAssistancePartners/.../sessions
        return RemoteSessionInfo(
            provider_session_id=f"ms-rh-{uuid.uuid4().hex[:12]}",
            join_url_agent=None,
            join_url_employee=None,
            status="pending",
        )

    async def terminate_session(self, provider_session_id: str) -> bool:
        """Terminate Remote Help session (stub)."""
        logger.info("remote_help_terminate", session_id=provider_session_id)
        return True

    async def get_session_status(self, provider_session_id: str) -> str:
        """Get Remote Help session status (stub)."""
        return "active"


# ─────────────────────────────────────────────────────────────────────
# Remote Support Service
# ─────────────────────────────────────────────────────────────────────


class RemoteSupportService:
    """Orchestrates remote assistance workflows with policy enforcement."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._providers: dict[str, RemoteSupportProvider] = {
            "microsoft_remote_help": MicrosoftRemoteHelpAdapter(),
        }

    async def request_session(
        self,
        agent: User,
        employee_id: uuid.UUID,
        session_type: str = "screen_view",
        ticket_id: uuid.UUID | None = None,
        justification: str | None = None,
    ) -> RemoteSupportSession:
        """IT agent requests a remote support session with employee."""
        # Policy check
        if not self._check_policy(agent, session_type):
            raise PermissionError("Policy check failed for remote session request")

        session = RemoteSupportSession(
            employee_id=employee_id,
            agent_id=agent.id,
            ticket_id=ticket_id,
            session_type=session_type,
            status="consent_pending",
            justification=justification,
            policy_check_passed=True,
        )
        self.db.add(session)
        await self.db.flush()

        logger.info(
            "remote_session_requested",
            session_id=str(session.id),
            agent=agent.email,
            employee_id=str(employee_id),
            session_type=session_type,
        )
        return session

    async def grant_consent(
        self,
        session_id: uuid.UUID,
        employee: User,
        consent_type: str,
        ip_address: str | None = None,
    ) -> RemoteSupportConsent:
        """Employee grants consent for remote assistance."""
        session = await self._get_session(session_id)
        if not session or session.employee_id != employee.id:
            raise PermissionError("Invalid session or unauthorized")

        consent = RemoteSupportConsent(
            session_id=session_id,
            employee_id=employee.id,
            consent_type=consent_type,
            granted=True,
            ip_address=ip_address,
            consent_text_shown=f"Employee {employee.full_name} granted {consent_type} access",
        )
        self.db.add(consent)

        # Update session status
        session.status = "consent_granted"
        await self.db.flush()

        logger.info(
            "remote_consent_granted",
            session_id=str(session_id),
            employee=employee.email,
            consent_type=consent_type,
        )
        return consent

    async def deny_consent(
        self, session_id: uuid.UUID, employee: User
    ) -> None:
        """Employee denies remote assistance consent."""
        session = await self._get_session(session_id)
        if not session or session.employee_id != employee.id:
            raise PermissionError("Invalid session or unauthorized")

        consent = RemoteSupportConsent(
            session_id=session_id,
            employee_id=employee.id,
            consent_type=session.session_type,
            granted=False,
        )
        self.db.add(consent)
        session.status = "consent_denied"

        logger.info("remote_consent_denied", session_id=str(session_id))

    async def start_session(self, session_id: uuid.UUID, agent: User) -> RemoteSupportSession:
        """Launch the remote support session after consent is granted."""
        session = await self._get_session(session_id)
        if not session or session.agent_id != agent.id:
            raise PermissionError("Invalid session or unauthorized")
        if session.status != "consent_granted":
            raise ValueError("Consent not yet granted")

        # Call provider to create session
        provider = self._providers.get(session.provider, list(self._providers.values())[0])
        provider_info = await provider.create_session(
            agent_id=str(agent.id),
            employee_id=str(session.employee_id),
            session_type=session.session_type,
        )

        session.status = "active"
        session.started_at = datetime.now(timezone.utc)
        session.provider_session_id = provider_info.provider_session_id

        logger.info("remote_session_started", session_id=str(session_id))
        return session

    async def end_session(
        self, session_id: uuid.UUID, actor: User, resolution_notes: str | None = None
    ) -> RemoteSupportSession:
        """End a remote support session."""
        session = await self._get_session(session_id)
        if not session:
            raise ValueError("Session not found")

        # Terminate with provider
        if session.provider_session_id:
            provider = self._providers.get(session.provider, list(self._providers.values())[0])
            await provider.terminate_session(session.provider_session_id)

        session.status = "completed"
        session.ended_at = datetime.now(timezone.utc)
        session.resolution_notes = resolution_notes

        logger.info("remote_session_ended", session_id=str(session_id))
        return session

    async def _get_session(self, session_id: uuid.UUID) -> RemoteSupportSession | None:
        """Fetch a remote support session by ID."""
        stmt = select(RemoteSupportSession).where(RemoteSupportSession.id == session_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _check_policy(self, agent: User, session_type: str) -> bool:
        """Check if agent has permission for the requested session type."""
        agent_roles = set(agent.role_names)

        # Screen control requires it_lead or above
        if session_type == "screen_control" and not agent_roles.intersection(
            {"it_lead", "it_admin"}
        ):
            return False

        # Full remote requires it_admin
        if session_type == "full_remote" and "it_admin" not in agent_roles:
            return False

        # Screen view allowed for all IT staff
        return bool(agent_roles.intersection({"it_agent", "it_lead", "it_admin"}))
