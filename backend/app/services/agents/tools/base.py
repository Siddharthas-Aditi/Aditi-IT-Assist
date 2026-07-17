"""Tool-calling contracts — the typed foundation for agent actions (Phase 5).

This module defines *what a tool is* and *how the agent talks about tools*,
without binding to any concrete tool, LLM, or external system. It mirrors the
design discipline of :mod:`app.services.agents.registry`: every capability an
agent can reach is a frozen, versioned, declarative spec — nothing is callable
that is not declared.

Why a tool layer
----------------
Specialists today return canned steps. To behave like a real IT analyst an
agent must be able to *do* things: search the KB, estimate a mailbox quota,
draft a ticket, and (in later phases) reach external systems over MCP. Every
one of those is a :class:`ToolSpec` with a typed argument model, a typed result
model, an explicit ``side_effect`` classification, RBAC requirements, and an
approval gate. The :class:`~app.services.agents.tools.runtime.AgentToolRuntime`
enforces all of that uniformly — local tools and (Phase 7+) MCP tools are
indistinguishable to the agent and equally governed.

Phase 5 scope
-------------
Local, read-only tools only. ``side_effect`` and ``approval`` are modelled in
full so Phase 8 (write/destructive actions, human approval) reuses this layer
unchanged — but no tool shipped in Phase 5 has a side effect beyond reading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class SideEffect(StrEnum):
    """How dangerous a tool's execution is. Drives the default approval gate."""

    READ = "read"  # no state change anywhere (KB search, quota math)
    WRITE = "write"  # mutates a system (reset MFA, create incident)
    DESTRUCTIVE = "destructive"  # irreversible / high blast radius (delete, disable)


class Approval(StrEnum):
    """Who must approve a tool call before it executes."""

    NONE = "none"  # auto-executes (read-only tools)
    HUMAN = "human"  # an IT specialist must approve (default for writes)
    AUTO_ALLOWLISTED = "auto_allowlisted"  # signed-off auto-exec; tiny blast radius only


class ToolOutcomeStatus(StrEnum):
    """Terminal status of a single tool invocation through the runtime."""

    EXECUTED = "executed"
    REJECTED_NOT_ALLOWED = "rejected_not_allowed"  # tool not in the agent's allow-list
    REJECTED_UNKNOWN = "rejected_unknown"  # tool name not in the registry
    REJECTED_FORBIDDEN = "rejected_forbidden"  # caller lacks required permission(s)
    INVALID_ARGS = "invalid_args"  # args failed schema validation
    NEEDS_APPROVAL = "needs_approval"  # gated; surfaced for human approval
    ERROR = "error"  # the tool raised at execution time


@dataclass(frozen=True, kw_only=True)
class ToolSpec:
    """Declarative description of one tool. Frozen and versioned.

    The spec is the *only* thing the runtime trusts. ``args_model`` and
    ``result_model`` are Pydantic models so every boundary is typed and
    validated — the LLM never hands raw dicts into tool logic.
    """

    name: str  # stable id, e.g. "kb_search"
    version: str = "1.0.0"  # bump on arg/behaviour change
    description: str = ""  # surfaced to the LLM as the function description
    args_model: type[BaseModel] = BaseModel
    result_model: type[BaseModel] = BaseModel
    side_effect: SideEffect = SideEffect.READ
    # Permission codes (see app.core.permissions.P) the caller must hold.
    required_permissions: tuple[str, ...] = ()
    approval: Approval = Approval.NONE
    # Set when this tool is backed by an MCP server (Phase 7+). None = local.
    mcp_server: str | None = None
    owner: str = "platform-team"

    def to_llm_tool(self) -> dict[str, Any]:
        """Render this spec as an OpenAI/LiteLLM-compatible tool definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }


@dataclass(frozen=True)
class ToolContext:
    """Caller identity + authorization, threaded through every tool call.

    Immutable. The runtime uses ``permissions`` for RBAC and ``approvals`` to
    decide whether a human-gated tool may execute this turn. ``approvals`` holds
    the names of tools the caller has explicitly approved (Phase 8 wires this to
    the specialist queue UI; in Phase 5 it stays empty).
    """

    user_id: str
    permissions: frozenset[str] = frozenset()
    roles: tuple[str, ...] = ()
    session_id: str = ""
    approvals: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ToolInvocation:
    """A request to run a tool — the LLM's choice, before validation."""

    tool_name: str
    raw_args: dict[str, Any] = field(default_factory=dict)
    call_id: str = ""  # provider-supplied id, echoed back in the tool result message


@dataclass(frozen=True)
class ToolOutcome:
    """The result of pushing one :class:`ToolInvocation` through the runtime."""

    tool_name: str
    status: ToolOutcomeStatus
    result: BaseModel | None = None
    error: str | None = None
    call_id: str = ""
    audit: dict[str, Any] = field(default_factory=dict)

    @property
    def executed(self) -> bool:
        return self.status is ToolOutcomeStatus.EXECUTED


@dataclass(frozen=True)
class LLMToolResponse:
    """A normalized response from an LLM tool-use turn.

    Either the model produced final text (``tool_calls`` empty) or it requested
    one or more tool calls. Decoupled from any provider SDK so tests can drive
    the runtime with a scripted fake.
    """

    text: str | None = None
    tool_calls: tuple[ToolInvocation, ...] = ()


@runtime_checkable
class Tool(Protocol):
    """The contract every concrete tool implements.

    ``run`` receives an already-validated args model (the runtime validates
    against ``spec.args_model`` before calling) and the caller context, and
    returns an instance of ``spec.result_model``.
    """

    spec: ToolSpec

    async def run(self, args: BaseModel, context: ToolContext) -> BaseModel:
        """Execute the tool. Must not perform RBAC/approval — the runtime does."""
        ...


__all__ = [
    "Approval",
    "LLMToolResponse",
    "SideEffect",
    "Tool",
    "ToolContext",
    "ToolInvocation",
    "ToolOutcome",
    "ToolOutcomeStatus",
    "ToolSpec",
]
