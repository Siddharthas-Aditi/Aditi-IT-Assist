"""Agent tool-calling layer (Phase 5).

Public surface:

* :mod:`.base` — typed contracts (``ToolSpec``, ``ToolContext``, ``Tool`` …).
* :mod:`.runtime` — :class:`AgentToolRuntime`, the single enforcement point.
* :mod:`.registry` — ``TOOL_REGISTRY`` + accessors + ``build_default_runtime``.
* :mod:`.local_tools` — the Phase-5 read-only tools.

See ``docs/architecture/agent-tooling.md`` and
``plans/agentic-ops-platform-evolution.md`` (Phase 5).
"""

from __future__ import annotations

from app.services.agents.tools.base import (
    Approval,
    LLMToolResponse,
    SideEffect,
    Tool,
    ToolContext,
    ToolInvocation,
    ToolOutcome,
    ToolOutcomeStatus,
    ToolSpec,
)
from app.services.agents.tools.registry import (
    TOOL_REGISTRY,
    TOOL_REGISTRY_VERSION,
    build_default_runtime,
    get_tool,
    get_tool_spec,
    list_tool_specs,
)
from app.services.agents.tools.runtime import AgentToolRuntime, ProposedAction, ToolLoopResult

__all__ = [
    "TOOL_REGISTRY",
    "TOOL_REGISTRY_VERSION",
    "AgentToolRuntime",
    "Approval",
    "LLMToolResponse",
    "ProposedAction",
    "SideEffect",
    "Tool",
    "ToolContext",
    "ToolInvocation",
    "ToolLoopResult",
    "ToolOutcome",
    "ToolOutcomeStatus",
    "ToolSpec",
    "build_default_runtime",
    "get_tool",
    "get_tool_spec",
    "list_tool_specs",
]
