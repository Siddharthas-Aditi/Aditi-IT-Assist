"""Remote support provider interface — pluggable abstraction for remote assistance tools.

This module defines the contract for all remote assistance providers.
Aditi IT Assist does NOT build raw screen-sharing software; it orchestrates
external enterprise remote support tools through this interface.

Supported providers (current and planned):
- Microsoft Intune Remote Help (attended)
- TeamViewer Business (attended + unattended future)
- ConnectWise ScreenConnect (future)
- BeyondTrust (future)

Architecture:
    Provider instances are stateless adapters. Session state lives in our
    database (RemoteSupportSession). Providers create/manage external sessions
    and return join links + status.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class SessionCapability(StrEnum):
    """Capabilities a provider may offer."""

    SCREEN_VIEW = "screen_view"
    SCREEN_CONTROL = "screen_control"
    FILE_TRANSFER = "file_transfer"
    CLIPBOARD_SHARE = "clipboard_share"
    CHAT = "chat"
    ANNOTATION = "annotation"
    MULTI_MONITOR = "multi_monitor"
    UNATTENDED = "unattended"  # Future roadmap only


class ProviderSessionStatus(StrEnum):
    """Provider-side session status (mapped to our internal statuses)."""

    PENDING = "pending"
    WAITING_FOR_USER = "waiting_for_user"
    CONNECTING = "connecting"
    ACTIVE = "active"
    PAUSED = "paused"
    DISCONNECTED = "disconnected"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class RemoteSessionInfo:
    """Information returned from the remote support provider after session creation."""

    provider_session_id: str
    status: ProviderSessionStatus = ProviderSessionStatus.PENDING

    # Join URLs (the critical handoff to the external tool)
    join_url_agent: str | None = None
    join_url_employee: str | None = None
    join_code: str | None = None  # Numeric code for employee to enter

    # Session metadata
    session_expiry: datetime | None = None
    capabilities_granted: list[SessionCapability] = field(default_factory=list)
    provider_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderStatusUpdate:
    """Status update from polling/webhook from the provider."""

    provider_session_id: str
    status: ProviderSessionStatus
    connected_at: datetime | None = None
    disconnected_at: datetime | None = None
    duration_seconds: int | None = None
    error_message: str | None = None


class RemoteSupportProvider(ABC):
    """Abstract interface for remote support tool integration.

    Each provider adapter translates between our orchestration layer
    and the external tool's API.

    Lifecycle:
        1. create_session() — create session, get join links
        2. get_session_status() — poll for status updates
        3. terminate_session() — end session gracefully
        4. get_session_recording_url() — post-session audit artifact
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique identifier for this provider (e.g., 'microsoft_remote_help')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable provider name."""
        ...

    @property
    @abstractmethod
    def supported_capabilities(self) -> list[SessionCapability]:
        """Capabilities this provider supports."""
        ...

    @property
    def supports_unattended(self) -> bool:
        """Whether provider supports unattended access (future roadmap)."""
        return False

    @abstractmethod
    async def create_session(
        self,
        *,
        agent_id: str,
        agent_name: str,
        employee_id: str,
        employee_name: str,
        session_type: str,
        capabilities: list[SessionCapability] | None = None,
        ticket_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RemoteSessionInfo:
        """Create a remote support session with the external provider.

        Args:
            agent_id: Internal agent user ID
            agent_name: Agent display name (for employee-facing UI)
            employee_id: Internal employee user ID
            employee_name: Employee display name
            session_type: "screen_view" | "screen_control"
            capabilities: Specific capabilities to request
            ticket_id: Associated support ticket (for context)
            metadata: Additional provider-specific data

        Returns:
            RemoteSessionInfo with join URLs and session ID
        """
        ...

    @abstractmethod
    async def terminate_session(self, provider_session_id: str) -> bool:
        """Terminate an active remote support session.

        Args:
            provider_session_id: The provider's session identifier

        Returns:
            True if successfully terminated
        """
        ...

    @abstractmethod
    async def get_session_status(self, provider_session_id: str) -> ProviderStatusUpdate:
        """Query current session status from the provider.

        Args:
            provider_session_id: The provider's session identifier

        Returns:
            Current status with timing metadata
        """
        ...

    async def get_session_recording_url(self, provider_session_id: str) -> str | None:
        """Get URL to session recording/audit log (if supported).

        Default: None (not all providers support recording).
        """
        return None

    async def validate_prerequisites(
        self, employee_device_id: str | None = None
    ) -> tuple[bool, str | None]:
        """Check if prerequisites are met for a session.

        Validates device enrollment, agent availability, license, etc.

        Returns:
            (success, error_message)
        """
        return True, None

    async def health_check(self) -> bool:
        """Verify provider API connectivity."""
        return True
