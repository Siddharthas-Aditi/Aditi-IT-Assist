"""Mock remote support provider — dev/staging stand-in (no external calls).

Mirrors the ``MCP_USE_MOCK`` pattern: with ``REMOTE_SUPPORT_USE_MOCK=true``
(the default) the *entire* remote-support workflow — request → consent →
launch → connect → end, with full RBAC, consent gating, and audit — runs
locally with fabricated join links. Nothing here ever reaches Microsoft.

The session/audit records honestly show ``provider="mock_remote_support"``
so a mock session can never masquerade as a real one in the audit trail.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
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


class MockRemoteSupportProvider(RemoteSupportProvider):
    """Fabricated sessions for local development and staging demos."""

    @property
    def provider_name(self) -> str:
        return "mock_remote_support"

    @property
    def display_name(self) -> str:
        return "Mock Remote Support (dev)"

    @property
    def supported_capabilities(self) -> list[SessionCapability]:
        return [
            SessionCapability.SCREEN_VIEW,
            SessionCapability.SCREEN_CONTROL,
            SessionCapability.CHAT,
            SessionCapability.ANNOTATION,
            SessionCapability.MULTI_MONITOR,
        ]

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
        session_id = f"mock-{uuid.uuid4().hex[:16]}"
        logger.info(
            "mock_remote_session_created",
            provider_session_id=session_id,
            session_type=session_type,
            ticket_id=ticket_id,
        )
        requested = capabilities or [
            SessionCapability.SCREEN_VIEW
            if session_type == "screen_view"
            else SessionCapability.SCREEN_CONTROL
        ]
        return RemoteSessionInfo(
            provider_session_id=session_id,
            status=ProviderSessionStatus.WAITING_FOR_USER,
            join_url_agent=f"https://mock.remote.local/session/{session_id}?role=helper",
            join_url_employee=f"https://mock.remote.local/session/{session_id}?role=sharer",
            join_code=str(uuid.uuid4().int)[:8],
            session_expiry=datetime.now(UTC) + timedelta(minutes=30),
            capabilities_granted=requested,
            provider_metadata={"mock": True, "ticket_reference": ticket_id},
        )

    async def terminate_session(self, provider_session_id: str) -> bool:
        logger.info("mock_remote_session_terminated", provider_session_id=provider_session_id)
        return True

    async def get_session_status(self, provider_session_id: str) -> ProviderStatusUpdate:
        return ProviderStatusUpdate(
            provider_session_id=provider_session_id,
            status=ProviderSessionStatus.ACTIVE,
            connected_at=datetime.now(UTC),
        )

    async def validate_prerequisites(
        self, employee_device_id: str | None = None
    ) -> tuple[bool, str | None]:
        return True, None

    async def health_check(self) -> bool:
        return True
