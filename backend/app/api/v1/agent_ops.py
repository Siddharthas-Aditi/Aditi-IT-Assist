"""Agent Operations API — operability surfaces for the agentic platform.

Read-only status (MCP + RAG + feature flags), the human-approval queue for
write actions (propose → approve → execute), and background-task monitoring.

RBAC, by segregation of duties:
* **status / list** — any IT staff (it_agent+).
* **propose** — any IT staff may *suggest* a write action (low privilege).
* **approve / reject** — it_lead+ only; the runtime additionally enforces the
  tool's specific ``integration:*_write`` permission against the approver.
* **tasks** — it_lead+ (admin monitor).

Handlers stay thin: they build a tool-runtime ``ToolContext`` from the
authenticated user and delegate to the approval queue / task runner singletons.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.auth import User
from app.schemas.agent_ops import (
    AgentOpsStatus,
    AgentTaskListResponse,
    AgentTaskRecord,
    ApprovalListResponse,
    ApprovalRecord,
    EnqueueTaskRequest,
    McpServerStatus,
    ProposeActionRequest,
)
from app.services.agents.approvals import ApprovalStatus, PendingApproval, get_approval_queue
from app.services.agents.mcp import profiles as mcp_profiles
from app.services.agents.mcp.tools import build_mcp_tools
from app.services.agents.registry import REGISTRY_VERSION
from app.services.agents.tasks.factory import get_task_runner
from app.services.agents.tasks.models import AgentTask
from app.services.agents.tools.base import ToolContext
from app.services.agents.tools.registry import TOOL_REGISTRY_VERSION, list_tool_specs
from app.services.auth.dependencies import get_current_active_user, require_roles
from app.services.auth.service import AuthService

router = APIRouter()

DBDep = Annotated[AsyncSession, Depends(get_db)]
ITStaff = Annotated[User, Depends(require_roles("it_agent", "it_lead", "it_admin"))]
Lead = Annotated[User, Depends(require_roles("it_lead", "it_admin"))]
CurrentUser = Annotated[User, Depends(get_current_active_user)]


async def _tool_context(user: User, db: AsyncSession) -> ToolContext:
    """Build a runtime ToolContext carrying the user's effective permissions."""
    perms = await AuthService(db).get_user_permissions(user)
    return ToolContext(
        user_id=str(user.id),
        permissions=frozenset(perms),
        roles=tuple(user.role_names),
    )


def _to_record(p: PendingApproval) -> ApprovalRecord:
    return ApprovalRecord(
        id=p.id,
        tool_name=p.tool_name,
        args=p.raw_args,
        reason=p.reason,
        status=p.status.value,
        side_effect=p.side_effect,
        mcp_server=p.mcp_server,
        args_hash=p.args_hash,
        proposer_id=p.proposer_id,
        created_at=p.created_at,
        decided_at=p.decided_at,
        decided_by=p.decided_by,
        result=p.result,
        error=p.error,
    )


def _task_record(t: AgentTask) -> AgentTaskRecord:
    return AgentTaskRecord(
        id=t.id,
        task_type=t.task_type,
        status=t.status.value,
        attempts=t.attempts,
        max_attempts=t.max_attempts,
        result=t.result,
        error=t.error,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


# ── Status ───────────────────────────────────────────────────────────────────


@router.get("/status", response_model=AgentOpsStatus)
async def get_status(_user: ITStaff) -> AgentOpsStatus:
    active_mcp = build_mcp_tools()  # honours current flags + enabled servers
    enabled_ids = {
        p.server_id
        for p in mcp_profiles.enabled_profiles(
            feature_on=settings.FEATURE_MCP_TOOLS,
            enabled_server_ids=list(settings.MCP_ENABLED_SERVERS),
        )
    }
    servers = [
        McpServerStatus(
            server_id=p.server_id,
            display_name=p.display_name,
            trust_tier=p.trust_tier.value,
            transport=p.transport.value,
            enabled=p.server_id in enabled_ids,
            tools=list(p.allowed_tools),
        )
        for p in mcp_profiles.list_profiles()
    ]
    return AgentOpsStatus(
        agent_tools_enabled=settings.FEATURE_AGENT_TOOLS,
        vector_retrieval_enabled=settings.FEATURE_VECTOR_RETRIEVAL,
        mcp_tools_enabled=settings.FEATURE_MCP_TOOLS,
        write_actions_enabled=settings.FEATURE_AGENT_WRITE_ACTIONS,
        background_agents_enabled=settings.FEATURE_BACKGROUND_AGENTS,
        mcp_use_mock=settings.MCP_USE_MOCK,
        retrieval_mode="hybrid" if settings.FEATURE_VECTOR_RETRIEVAL else "keyword",
        ranking_version=_ranking_version(),
        registry_version=REGISTRY_VERSION,
        tool_registry_version=TOOL_REGISTRY_VERSION,
        mcp_profile_version=mcp_profiles.MCP_PROFILE_VERSION,
        local_tools=[s.name for s in list_tool_specs()],
        active_mcp_tools=sorted(active_mcp),
        servers=servers,
    )


def _ranking_version() -> str:
    from app.services.knowledge.ranking import RANKING_VERSION

    return RANKING_VERSION


# ── Approvals ────────────────────────────────────────────────────────────────


@router.get("/approvals", response_model=ApprovalListResponse)
async def list_approvals(
    _user: ITStaff,
    status: Annotated[str | None, Query()] = None,
) -> ApprovalListResponse:
    queue = get_approval_queue()
    status_enum = ApprovalStatus(status) if status else None
    return ApprovalListResponse(items=[_to_record(p) for p in await queue.list(status=status_enum)])


@router.post("/approvals", response_model=ApprovalRecord)
async def propose_action(body: ProposeActionRequest, user: ITStaff) -> ApprovalRecord:
    record = await get_approval_queue().propose(
        tool_name=body.tool_name,
        raw_args=body.args,
        proposer_id=str(user.id),
        reason=body.reason,
    )
    return _to_record(record)


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalRecord)
async def approve_action(approval_id: str, user: Lead, db: DBDep) -> ApprovalRecord:
    queue = get_approval_queue()
    if await queue.get(approval_id) is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    ctx = await _tool_context(user, db)
    record = await queue.approve(approval_id, ctx)
    return _to_record(record)


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalRecord)
async def reject_action(approval_id: str, user: Lead) -> ApprovalRecord:
    queue = get_approval_queue()
    if await queue.get(approval_id) is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return _to_record(await queue.reject(approval_id, str(user.id)))


# ── Background tasks ─────────────────────────────────────────────────────────


@router.get("/tasks", response_model=AgentTaskListResponse)
async def list_tasks(_user: Lead) -> AgentTaskListResponse:
    runner = get_task_runner()
    tasks = await runner._store.list_all()  # noqa: SLF001 — monitor reads the shared store
    tasks = sorted(tasks, key=lambda t: t.created_at, reverse=True)
    return AgentTaskListResponse(items=[_task_record(t) for t in tasks])


@router.post("/tasks", response_model=AgentTaskRecord)
async def enqueue_task(body: EnqueueTaskRequest, _user: Lead) -> AgentTaskRecord:
    runner = get_task_runner()
    task = await runner.enqueue(
        AgentTask(
            task_type=body.task_type,
            payload=body.payload,
            idempotency_key=body.idempotency_key,
            max_attempts=settings.AGENT_TASK_MAX_ATTEMPTS,
        )
    )
    # Run a drain pass so the demo sees results immediately (idempotent; the
    # lifespan loop would otherwise pick it up on the next poll).
    await runner.run_once()
    refreshed = await runner._store.get(task.id)  # noqa: SLF001
    return _task_record(refreshed or task)


__all__ = ["router"]
