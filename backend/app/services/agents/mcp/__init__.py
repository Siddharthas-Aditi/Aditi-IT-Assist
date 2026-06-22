"""MCP client layer (Phase 7) — agents consume external systems as governed tools.

Public surface:

* :mod:`.profiles` — declarative ``McpServerProfile`` registry (allow-list,
  trust tier, side-effect ceiling), ``MCP_PROFILE_VERSION``.
* :mod:`.session` — ``McpSession`` protocol + lazy SDK adapter + session provider.
* :mod:`.tools` — typed MCP-backed read tools + ``build_mcp_tools``.

See ``docs/architecture/mcp-integrations.md`` and
``plans/agentic-ops-platform-evolution.md`` (Phase 7).
"""

from __future__ import annotations

from app.services.agents.mcp.profiles import (
    MCP_PROFILE_VERSION,
    MCP_SERVER_REGISTRY,
    McpServerProfile,
    McpTransport,
    TrustTier,
    enabled_profiles,
    get_profile,
    list_profiles,
)
from app.services.agents.mcp.tools import build_mcp_tools

__all__ = [
    "MCP_PROFILE_VERSION",
    "MCP_SERVER_REGISTRY",
    "McpServerProfile",
    "McpTransport",
    "TrustTier",
    "build_mcp_tools",
    "enabled_profiles",
    "get_profile",
    "list_profiles",
]
