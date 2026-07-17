"""MCP server profiles — the declarative allow-list of external systems agents
may reach (Phase 7, *consume* direction).

Aditi Assist acts as an **MCP client**: external IT systems (Microsoft Graph for
Entra/Intune/Exchange, ServiceNow) are reached through MCP servers and surfaced
to the existing :class:`~app.services.agents.tools.runtime.AgentToolRuntime` as
ordinary, governed tools. This module is the source of truth for *which servers
exist and what each may expose* — mirroring the discipline of the agent and tool
registries.

Governance properties (PR-reviewed, versioned via ``MCP_PROFILE_VERSION``):

* **Allow-list, not auto-discovery.** A server may advertise dozens of tools;
  only the tool names in ``allowed_tools`` here ever become callable. An
  upstream server adding a tool can never silently widen agent capability.
* **Trust tier.** Each server is tagged (``OFFICIAL`` / ``VENDOR`` / ``INTERNAL``)
  for audit and review, mirroring the web-fallback trust-tier model.
* **Side-effect ceiling.** Phase 7 servers are ``READ`` only — a binding whose
  declared side effect exceeds the server's ceiling is rejected at build time.
* **Per-server enablement.** Nothing is reachable unless ``FEATURE_MCP_TOOLS`` is
  on *and* the server id is listed in ``MCP_ENABLED_SERVERS``.
* **No secrets here.** Profiles reference an auth env/secret *name*; the value is
  resolved from configuration / the secrets manager at connection time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.services.agents.tools.base import SideEffect

# Bump on any change to the set of servers or their declared scope.
# 1.1.0 — Phase 9: add the msgraph_intune_exec server (device-execution writes).
MCP_PROFILE_VERSION = "1.1.0"


class McpTransport(StrEnum):
    """How the client connects to an MCP server."""

    STDIO = "stdio"
    STREAMABLE_HTTP = "streamable_http"
    SSE = "sse"


class TrustTier(StrEnum):
    """Provenance of an MCP server, for audit + review gating."""

    OFFICIAL = "official"  # first-party vendor (e.g. Microsoft Graph)
    VENDOR = "vendor"  # third-party product (e.g. ServiceNow)
    INTERNAL = "internal"  # in-house wrapper


@dataclass(frozen=True, kw_only=True)
class McpServerProfile:
    """Declarative description of one MCP server the client may connect to."""

    server_id: str  # stable id, referenced by tool bindings
    display_name: str
    transport: McpTransport
    endpoint: str  # URL (http/sse) or command (stdio)
    trust_tier: TrustTier
    # Tool names (our registry names, not the server's) this server may expose.
    allowed_tools: tuple[str, ...] = field(default_factory=tuple)
    # The most dangerous side effect any tool on this server may declare.
    side_effect_ceiling: SideEffect = SideEffect.READ
    # Name of the config/secret holding auth material — never the secret itself.
    auth_secret_ref: str | None = None
    owner: str = "platform-team"


# ── The registry ─────────────────────────────────────────────────────────────
# Enumerated, never dynamic. Adding a server is one declaration here plus a tool
# binding in ``tools.py``. Phase 7: all read-only.

_MSGRAPH = McpServerProfile(
    server_id="msgraph",
    display_name="Microsoft Graph (Entra / Intune / Exchange)",
    transport=McpTransport.STREAMABLE_HTTP,
    endpoint="https://graph-mcp.internal.aditi/mcp",  # in-house Graph MCP gateway
    trust_tier=TrustTier.OFFICIAL,
    allowed_tools=(
        # Phase 7 reads
        "entra_account_status",
        "intune_device_compliance",
        "mailbox_quota_status",
        # Phase 8 writes (human-approved; built only when write actions enabled)
        "entra_unlock_account",
        "reset_mfa",
    ),
    # Ceiling WRITE (Phase 8): write tools are permitted but never destructive,
    # and only built when FEATURE_AGENT_WRITE_ACTIONS is on.
    side_effect_ceiling=SideEffect.WRITE,
    auth_secret_ref="MCP_MSGRAPH_TOKEN",
)

_SERVICENOW = McpServerProfile(
    server_id="servicenow",
    display_name="ServiceNow ITSM",
    transport=McpTransport.STREAMABLE_HTTP,
    endpoint="https://servicenow-mcp.internal.aditi/mcp",
    trust_tier=TrustTier.VENDOR,
    allowed_tools=("servicenow_incident_lookup", "servicenow_create_incident"),
    side_effect_ceiling=SideEffect.WRITE,
    auth_secret_ref="MCP_SERVICENOW_TOKEN",
)

# Phase 9 — device execution. A SEPARATE server from the read-only msgraph
# profile so the high-blast-radius execution surface has its own enablement,
# allow-list, and audit boundary. Tools here install approved apps, run approved
# remediations, and take benign device actions on Intune-managed endpoints — all
# catalog-bound and autonomy-policy-gated (see device_actions/). Built only when
# FEATURE_DEVICE_EXECUTION is on.
_MSGRAPH_INTUNE_EXEC = McpServerProfile(
    server_id="msgraph_intune_exec",
    display_name="Microsoft Graph — Intune device execution",
    transport=McpTransport.STREAMABLE_HTTP,
    endpoint="https://graph-mcp.internal.aditi/intune-exec",
    trust_tier=TrustTier.OFFICIAL,
    allowed_tools=(
        "install_win32_app",
        "run_remediation_script",
        "device_action",
    ),
    # WRITE ceiling: writes are permitted but never destructive; every call is
    # additionally catalog-bound + policy-gated in the tool layer.
    side_effect_ceiling=SideEffect.WRITE,
    auth_secret_ref="MCP_MSGRAPH_TOKEN",
)

MCP_SERVER_REGISTRY: dict[str, McpServerProfile] = {
    p.server_id: p for p in (_MSGRAPH, _SERVICENOW, _MSGRAPH_INTUNE_EXEC)
}


# ── Accessors ────────────────────────────────────────────────────────────────


def get_profile(server_id: str) -> McpServerProfile | None:
    return MCP_SERVER_REGISTRY.get(server_id)


def list_profiles() -> list[McpServerProfile]:
    return sorted(MCP_SERVER_REGISTRY.values(), key=lambda p: p.server_id)


def enabled_profiles(*, feature_on: bool, enabled_server_ids: list[str]) -> list[McpServerProfile]:
    """Profiles that are actually live: master flag on AND server explicitly enabled."""
    if not feature_on:
        return []
    enabled = set(enabled_server_ids)
    return [p for p in list_profiles() if p.server_id in enabled]


__all__ = [
    "MCP_PROFILE_VERSION",
    "MCP_SERVER_REGISTRY",
    "McpServerProfile",
    "McpTransport",
    "TrustTier",
    "enabled_profiles",
    "get_profile",
    "list_profiles",
]
