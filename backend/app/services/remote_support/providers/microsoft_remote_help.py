"""Microsoft Intune Remote Help provider adapter.

Integration with Microsoft's enterprise remote assistance solution.
This is an ORCHESTRATION adapter — it does not implement screen sharing.
It creates sessions in Microsoft's infrastructure and returns join links.

Prerequisites for production:
    1. Azure AD App Registration with these permissions:
       - DeviceManagementServiceConfig.ReadWrite.All
       - RemoteAssistance.ReadWrite.All
    2. Microsoft Intune P1/P2 license for agents
    3. Remote Help app installed on managed Windows/macOS devices
    4. Conditional Access policies configured (optional)

API Reference:
    - https://learn.microsoft.com/graph/api/resources/intune-remoteassistance
    - POST /deviceManagement/remoteAssistancePartners
    - POST /deviceManagement/remoteAssistanceSessions

Current Status: STUB — returns mock data for development.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from app.services.remote_support.providers.base import (
    ProviderSessionStatus,
    ProviderStatusUpdate,
    RemoteSessionInfo,
    RemoteSupportProvider,
    SessionCapability,
)

logger = structlog.get_logger()


class MicrosoftRemoteHelpProvider(RemoteSupportProvider):
    """Microsoft Intune Remote Help adapter.

    Attended remote assistance only. Employee must accept the
    connection in the Remote Help app.

    Flow:
        1. Agent requests session → we call Graph API → get session ID
        2. Employee receives notification in Remote Help app
        3. Employee accepts → session becomes active
        4. Agent gets join URL → opens Remote Help client
        5. Session ends → we record duration + outcome

    Configuration (injected at init):
        - tenant_id: Azure AD tenant
        - client_id: App registration client ID
        - client_secret: App registration secret
        - api_base_url: Graph API endpoint
    """

    def __init__(
        self,
        *,
        tenant_id: str = "",
        client_id: str = "",
        client_secret: str = "",
        api_base_url: str = "https://graph.microsoft.com/v1.0",
    ) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._api_base_url = api_base_url

    @property
    def provider_name(self) -> str:
        return "microsoft_remote_help"

    @property
    def display_name(self) -> str:
        return "Microsoft Remote Help"

    @property
    def supported_capabilities(self) -> list[SessionCapability]:
        return [
            SessionCapability.SCREEN_VIEW,
            SessionCapability.SCREEN_CONTROL,
            SessionCapability.CHAT,
            SessionCapability.ANNOTATION,
            SessionCapability.MULTI_MONITOR,
        ]

    @property
    def supports_unattended(self) -> bool:
        return False  # Remote Help is attended-only

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
        """Create a Remote Help session via Microsoft Graph API.

        In production, this calls:
            POST {api_base_url}/deviceManagement/remoteAssistanceSessions
            Body: {
                "deviceId": "<intune-device-id>",
                "helperUserId": "<agent-azure-ad-oid>",
                "sessionType": "fullControl" | "viewOnly",
            }
        """
        logger.info(
            "ms_remote_help_create_session",
            agent_id=agent_id,
            agent_name=agent_name,
            employee_id=employee_id,
            session_type=session_type,
            ticket_id=ticket_id,
        )

        # STUB: Generate mock session info for development
        # In production: call Microsoft Graph API here
        session_id = f"ms-rh-{uuid.uuid4().hex[:16]}"
        expiry = datetime.now(timezone.utc) + timedelta(minutes=30)

        requested_capabilities = capabilities or [
            SessionCapability.SCREEN_VIEW
            if session_type == "screen_view"
            else SessionCapability.SCREEN_CONTROL
        ]

        return RemoteSessionInfo(
            provider_session_id=session_id,
            status=ProviderSessionStatus.WAITING_FOR_USER,
            # In production: these URLs come from Graph API response
            join_url_agent=f"ms-remotehelp://session/{session_id}?role=helper",
            join_url_employee=f"ms-remotehelp://session/{session_id}?role=sharer",
            join_code=str(uuid.uuid4().int)[:8],  # 8-digit code
            session_expiry=expiry,
            capabilities_granted=requested_capabilities,
            provider_metadata={
                "tenant_id": self._tenant_id,
                "session_type": session_type,
                "ticket_reference": ticket_id,
            },
        )

    async def terminate_session(self, provider_session_id: str) -> bool:
        """Terminate Remote Help session via Graph API.

        In production: DELETE /deviceManagement/remoteAssistanceSessions/{id}
        """
        logger.info(
            "ms_remote_help_terminate",
            provider_session_id=provider_session_id,
        )
        # STUB: Always succeeds
        return True

    async def get_session_status(
        self, provider_session_id: str
    ) -> ProviderStatusUpdate:
        """Get Remote Help session status via Graph API.

        In production: GET /deviceManagement/remoteAssistanceSessions/{id}
        """
        logger.debug(
            "ms_remote_help_status_check",
            provider_session_id=provider_session_id,
        )
        # STUB: Return active status
        return ProviderStatusUpdate(
            provider_session_id=provider_session_id,
            status=ProviderSessionStatus.ACTIVE,
            connected_at=datetime.now(timezone.utc),
        )

    async def get_session_recording_url(
        self, provider_session_id: str
    ) -> str | None:
        """Remote Help doesn't provide session recordings directly.

        Audit logs are available via Microsoft 365 Audit Log.
        """
        return None

    async def validate_prerequisites(
        self, employee_device_id: str | None = None
    ) -> tuple[bool, str | None]:
        """Validate Remote Help prerequisites.

        Checks:
            - Device is Intune-enrolled
            - Remote Help app is installed
            - Agent has Intune license
            - No Conditional Access blocks
        """
        if not self._tenant_id:
            return False, "Microsoft Remote Help not configured (missing tenant_id)"

        # STUB: In production, query Intune for device compliance
        # GET /deviceManagement/managedDevices/{deviceId}
        return True, None

    async def health_check(self) -> bool:
        """Check Graph API connectivity."""
        if not self._tenant_id:
            return False
        # STUB: In production, call Graph API /me or similar
        return True
