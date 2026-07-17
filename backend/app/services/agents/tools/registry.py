"""Tool registry — the declarative source of truth for callable tools.

Mirrors :mod:`app.services.agents.registry`: every tool an agent can invoke is
enumerated here, versioned, and never registered dynamically, so tests and
audits can grep this file. The supervisor/specialist references tools by name
(via ``SpecialistAgentSpec.allowed_tools``); the runtime resolves names through
this registry.

``TOOL_REGISTRY_VERSION`` bumps on any change to the set of tools or their
specs, so audit and analytics can join on it the same way they join on
``REGISTRY_VERSION``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.agents.tools.local_tools import (
    KbSearchTool,
    MailboxQuotaEstimateTool,
    TicketDraftTool,
)
from app.services.agents.tools.runtime import AgentToolRuntime, AuditSink

if TYPE_CHECKING:
    from app.services.agents.tools.base import Tool, ToolSpec

# Bump on any tool addition, removal, or arg/behaviour change.
# 1.1.0 — Phase 9: device-execution tools mergeable via build_default_runtime.
TOOL_REGISTRY_VERSION = "1.1.0"


def _build_registry() -> dict[str, Tool]:
    """Construct the canonical tool instances. Enumerated, not dynamic."""
    tools: tuple[Tool, ...] = (
        KbSearchTool(),
        MailboxQuotaEstimateTool(),
        TicketDraftTool(),
    )
    registry: dict[str, Tool] = {}
    for tool in tools:
        if tool.spec.name in registry:
            raise RuntimeError(f"duplicate tool name in registry: {tool.spec.name!r}")
        registry[tool.spec.name] = tool
    return registry


# Live mapping {tool_name: Tool}. Frozen-in-practice: built once at import.
TOOL_REGISTRY: dict[str, Tool] = _build_registry()


def get_tool(name: str) -> Tool | None:
    """Return the tool instance by name, or None if unknown."""
    return TOOL_REGISTRY.get(name)


def get_tool_spec(name: str) -> ToolSpec | None:
    """Return the spec for a tool by name, or None if unknown."""
    tool = TOOL_REGISTRY.get(name)
    return tool.spec if tool else None


def list_tool_specs() -> list[ToolSpec]:
    """All tool specs, sorted by name (stable for tests and docs)."""
    return sorted((t.spec for t in TOOL_REGISTRY.values()), key=lambda s: s.name)


def build_default_runtime(
    audit_sink: AuditSink | None = None,
    *,
    include_mcp: bool = False,
    include_device_execution: bool = False,
    mcp_session_provider=None,
) -> AgentToolRuntime:
    """Construct an :class:`AgentToolRuntime` over the local registry.

    When ``include_mcp`` is set, also merge MCP-backed tools for currently
    enabled servers (Phase 7). MCP tools are governed identically to local
    tools by the runtime; they appear only when ``FEATURE_MCP_TOOLS`` is on and
    the server is enabled. Local tools take precedence on a name clash.

    When ``include_device_execution`` is set, also merge the catalog-bound
    Intune device-execution tools (Phase 9). They appear only when
    ``FEATURE_DEVICE_EXECUTION`` is on and the ``msgraph_intune_exec`` server is
    enabled; each call is catalog-bound and autonomy-policy-gated inside the tool.
    """
    tools: dict = dict(TOOL_REGISTRY)
    if include_mcp:
        from app.services.agents.mcp.tools import build_mcp_tools

        for name, tool in build_mcp_tools(session_provider=mcp_session_provider).items():
            tools.setdefault(name, tool)
    if include_device_execution:
        from app.services.agents.device_actions.tools import build_device_execution_tools

        for name, tool in build_device_execution_tools(
            session_provider=mcp_session_provider
        ).items():
            tools.setdefault(name, tool)
    return AgentToolRuntime(tools, audit_sink=audit_sink)


__all__ = [
    "TOOL_REGISTRY",
    "TOOL_REGISTRY_VERSION",
    "build_default_runtime",
    "get_tool",
    "get_tool_spec",
    "list_tool_specs",
]
