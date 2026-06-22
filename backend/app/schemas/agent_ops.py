"""Schemas for the Agent Operations API (Phase 5–8 operability surfaces)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ── Status (MCP + RAG + flags) ───────────────────────────────────────────────


class McpServerStatus(BaseModel):
    server_id: str
    display_name: str
    trust_tier: str
    transport: str
    enabled: bool
    tools: list[str]


class AgentOpsStatus(BaseModel):
    # Feature flags
    agent_tools_enabled: bool
    vector_retrieval_enabled: bool
    mcp_tools_enabled: bool
    write_actions_enabled: bool
    background_agents_enabled: bool
    mcp_use_mock: bool
    # Retrieval
    retrieval_mode: str                      # "hybrid" | "keyword"
    ranking_version: str
    # Registry / tooling
    registry_version: str
    tool_registry_version: str
    mcp_profile_version: str
    local_tools: list[str]
    active_mcp_tools: list[str]
    servers: list[McpServerStatus]


# ── Approvals ────────────────────────────────────────────────────────────────


class ProposeActionRequest(BaseModel):
    tool_name: str = Field(..., description="A human-gated write tool, e.g. 'reset_mfa'.")
    args: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field("", description="Why this action is being proposed.")


class ApprovalRecord(BaseModel):
    id: str
    tool_name: str
    args: dict[str, Any]
    reason: str
    status: str
    side_effect: str
    mcp_server: str | None
    args_hash: str
    proposer_id: str
    created_at: datetime
    decided_at: datetime | None
    decided_by: str | None
    result: dict[str, Any] | None
    error: str | None


class ApprovalListResponse(BaseModel):
    items: list[ApprovalRecord]


# ── Background tasks ─────────────────────────────────────────────────────────


class EnqueueTaskRequest(BaseModel):
    task_type: str = Field(..., description="e.g. 'knowledge_improvement_sweep'.")
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


class AgentTaskRecord(BaseModel):
    id: str
    task_type: str
    status: str
    attempts: int
    max_attempts: int
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class AgentTaskListResponse(BaseModel):
    items: list[AgentTaskRecord]


__all__ = [
    "AgentOpsStatus",
    "AgentTaskListResponse",
    "AgentTaskRecord",
    "ApprovalListResponse",
    "ApprovalRecord",
    "EnqueueTaskRequest",
    "McpServerStatus",
    "ProposeActionRequest",
]
