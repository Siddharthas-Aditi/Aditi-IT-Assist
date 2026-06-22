"""Mock MCP session for local development & demos (no real servers needed).

Returns realistic canned responses for every Phase-7/8 MCP tool so the whole
agentic stack — read diagnostics, the human-approval queue, and write actions —
can be exercised end-to-end locally without Microsoft Graph or ServiceNow.

Activated by ``MCP_USE_MOCK`` (default true in dev). The mock implements the
same :class:`McpSession` protocol the real adapter does, so nothing downstream
can tell the difference — the runtime still applies allow-list, RBAC, approval,
timeout, and audit exactly as in production.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.services.agents.mcp.profiles import McpServerProfile

logger = get_logger(__name__)


def _mock_result(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Deterministic-ish canned payloads keyed by the server tool name."""
    upn = args.get("user_principal_name") or args.get("mailbox") or "user@aditi.com"
    match tool:
        case "get_user_account_status":
            return {
                "user_principal_name": upn,
                "account_enabled": True,
                "locked": True,                       # interesting case for demos
                "mfa_registered": True,
                "last_sign_in": "2026-06-21T22:14:00Z",
            }
        case "get_device_compliance":
            return {
                "device_id": args.get("device_id") or "DEV-MOCK-0001",
                "compliance_state": "noncompliant",
                "os": "Windows 11",
                "last_check_in": "2026-06-22T06:02:00Z",
                "noncompliant_reasons": ["Disk not encrypted", "OS below minimum build"],
            }
        case "get_mailbox_usage":
            return {"mailbox": upn, "used_gb": 49.2, "quota_gb": 50.0, "percent_used": 98.4}
        case "get_incident":
            return {
                "number": args.get("number") or "INC0012345",
                "state": "In Progress",
                "short_description": "VPN drops every few minutes",
                "assigned_to": "network-team",
                "opened_at": "2026-06-20T09:30:00Z",
            }
        # ── write tools ──
        case "unlock_account":
            return {"user_principal_name": upn, "unlocked": True, "already_unlocked": False}
        case "reset_mfa":
            return {"user_principal_name": upn, "mfa_reset": True}
        case "create_incident":
            return {"number": f"INC{uuid.uuid4().int % 9000000 + 1000000}", "created": True}
        case _:
            return {"mock": True, "tool": tool}


class MockMcpSession:
    """In-memory fake MCP session — implements the McpSession protocol."""

    def __init__(self, profile: McpServerProfile) -> None:
        self._profile = profile

    async def list_tools(self) -> list[dict[str, Any]]:
        return [{"name": t} for t in self._profile.allowed_tools]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        logger.info("mcp_mock_call", server=self._profile.server_id, tool=name)
        return _mock_result(name, arguments)

    async def close(self) -> None:
        return None


__all__ = ["MockMcpSession"]
