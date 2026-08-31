"""Human-approval queue for agent write actions — durable, DB-backed.

The queue turns the runtime's propose→approve→execute contract into something
an IT specialist can act on:

* an IT agent (or an agent turn) **proposes** a governed write action — it is
  dispatched through the :class:`AgentToolRuntime`, which (because every write
  tool is ``approval=human``) returns ``needs_approval`` and the action is
  parked here, executing nothing;
* an authorized lead **approves** it — the exact captured invocation is
  re-dispatched via ``execute_approved`` under the approver's identity, so RBAC,
  audit, and idempotency all still apply;
* or it is **rejected**.

Durability
----------
Records are persisted to ``pending_approval_records`` (migration 018). A service
restart does NOT lose pending approvals. On restart, any row stuck in the
``EXECUTING`` state (crash during execution) is reset to ``PENDING`` and marked
with ``recovered_at`` so approvers can see it is stale. No row is ever silently
dropped or auto-approved.

TOCTOU safety
-------------
``approve()`` uses ``SELECT ... FOR UPDATE`` inside an explicit transaction so
only one caller can claim a given approval at a time. A second concurrent
``approve()`` sees the row in ``EXECUTING`` and returns the current record.

External interface
------------------
The ``PendingApproval`` dataclass is preserved as the DTO returned by all methods.
``reject()``, ``list()``, and ``get()`` are now async (DB access requires await);
callers in agent_ops.py are updated accordingly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import ValidationError

from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.models.pending_approval import PendingApprovalRecord
from app.repositories.pending_approval_repository import PendingApprovalRepository
from app.services.agents.tools.base import Approval, ToolContext, ToolInvocation
from app.services.agents.tools.registry import build_default_runtime
from app.services.agents.tools.runtime import AgentToolRuntime

logger = get_logger(__name__)


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    EXECUTING = "executing"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"
    INVALID = "invalid"


@dataclass
class PendingApproval:
    """DTO returned by all queue methods. Unchanged public surface."""

    tool_name: str
    raw_args: dict[str, Any]
    proposer_id: str
    reason: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: ApprovalStatus = ApprovalStatus.PENDING
    side_effect: str = "write"
    mcp_server: str | None = None
    args_hash: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = None
    decided_by: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    # Non-null when the row was recovered from EXECUTING state at restart.
    recovered_at: datetime | None = None


def _to_dto(row: PendingApprovalRecord) -> PendingApproval:
    return PendingApproval(
        id=row.id,
        tool_name=row.tool_name,
        raw_args=row.raw_args or {},
        proposer_id=row.proposer_id,
        reason=row.reason or "",
        status=ApprovalStatus(row.status),
        side_effect=row.side_effect or "write",
        mcp_server=row.mcp_server,
        args_hash=row.args_hash or "",
        created_at=row.created_at,
        decided_at=row.decided_at,
        decided_by=row.decided_by,
        result=row.result,
        error=row.error,
        recovered_at=row.recovered_at,
    )


class ApprovalQueue:
    """DB-backed store + workflow for human-gated agent actions."""

    def __init__(self, runtime: AgentToolRuntime | None = None) -> None:
        self._runtime = runtime or build_default_runtime(
            include_mcp=True, include_device_execution=True
        )

    # ── Proposing ────────────────────────────────────────────────────────

    async def propose(
        self,
        *,
        tool_name: str,
        raw_args: dict[str, Any],
        proposer_id: str,
        reason: str = "",
    ) -> PendingApproval:
        """Validate + persist a write action. Segregation of duties: no RBAC
        at proposal time — RBAC is enforced against the approver at approval."""
        from app.services.agents.tools.runtime import _hash_obj

        spec = self._runtime.get_spec(tool_name)
        approval_id = uuid.uuid4().hex
        side_effect = spec.side_effect.value if spec else "unknown"
        mcp_server = getattr(spec, "mcp_server", None) if spec else None
        args_hash = _hash_obj(raw_args)

        if spec is None:
            status = ApprovalStatus.INVALID
            error: str | None = f"unknown tool {tool_name!r}"
        elif spec.approval is not Approval.HUMAN:
            status = ApprovalStatus.INVALID
            error = "tool is not human-approval-gated; nothing to queue"
        else:
            try:
                spec.args_model.model_validate(raw_args)
                status = ApprovalStatus.PENDING
                error = None
            except ValidationError as exc:
                status = ApprovalStatus.INVALID
                error = f"invalid arguments: {exc.error_count()} error(s)"

        row = PendingApprovalRecord(
            id=approval_id,
            tool_name=tool_name,
            raw_args=raw_args,
            proposer_id=proposer_id,
            reason=reason,
            side_effect=side_effect,
            mcp_server=mcp_server,
            args_hash=args_hash,
            status=status.value,
            error=error,
        )
        async with async_session_factory() as db:
            repo = PendingApprovalRepository(db)
            await repo.create(row)
            await db.commit()

        logger.info(
            "approval_proposed",
            id=approval_id,
            tool=tool_name,
            status=status.value,
            proposer=proposer_id,
        )
        return _to_dto(row)

    # ── Deciding ─────────────────────────────────────────────────────────

    async def approve(self, approval_id: str, approver: ToolContext) -> PendingApproval:
        """Claim and execute. Row lock prevents concurrent double-execution."""
        from app.services.agents.tools.runtime import ProposedAction

        # Phase 1: lock + claim atomically.
        async with async_session_factory() as db:
            repo = PendingApprovalRepository(db)
            row = await repo.get_for_update(approval_id)
            if row is None:
                raise KeyError(approval_id)
            if row.status != ApprovalStatus.PENDING.value:
                return _to_dto(row)
            row.status = ApprovalStatus.EXECUTING.value
            await db.commit()

        # Phase 2: execute outside the lock (long-running, possibly MCP call).
        proposed = ProposedAction(
            invocation=ToolInvocation(row.tool_name, row.raw_args),
            tool_name=row.tool_name,
            side_effect=row.side_effect or "write",
            mcp_server=row.mcp_server,
            description="",
            args_hash=row.args_hash or "",
        )
        outcome = await self._runtime.execute_approved(
            proposed, approver, allowed_tools=(row.tool_name,), approver_id=approver.user_id
        )

        # Phase 3: persist decision.
        async with async_session_factory() as db:
            repo = PendingApprovalRepository(db)
            row2 = await repo.get(approval_id)
            if row2 is None:
                raise KeyError(approval_id)
            row2.decided_at = datetime.now(UTC)
            row2.decided_by = approver.user_id
            if outcome.executed:
                row2.status = ApprovalStatus.APPROVED.value
                row2.result = (
                    outcome.result.model_dump(mode="json")
                    if outcome.result is not None and hasattr(outcome.result, "model_dump")
                    else None
                )
            else:
                row2.status = ApprovalStatus.FAILED.value
                row2.error = outcome.error or outcome.status.value
            await db.commit()

        logger.info(
            "approval_decided",
            id=approval_id,
            status=row2.status,
            approver=approver.user_id,
        )
        return _to_dto(row2)

    async def reject(self, approval_id: str, approver_id: str) -> PendingApproval:
        async with async_session_factory() as db:
            repo = PendingApprovalRepository(db)
            row = await repo.get(approval_id)
            if row is None:
                raise KeyError(approval_id)
            if row.status == ApprovalStatus.PENDING.value:
                row.status = ApprovalStatus.REJECTED.value
                row.decided_at = datetime.now(UTC)
                row.decided_by = approver_id
                await db.commit()
        return _to_dto(row)

    # ── Reading ──────────────────────────────────────────────────────────

    async def list(self, *, status: ApprovalStatus | None = None) -> list[PendingApproval]:
        async with async_session_factory() as db:
            repo = PendingApprovalRepository(db)
            rows = await repo.list_by_status(status.value if status else None)
        return [_to_dto(r) for r in rows]

    async def get(self, approval_id: str) -> PendingApproval | None:
        async with async_session_factory() as db:
            repo = PendingApprovalRepository(db)
            row = await repo.get(approval_id)
        return _to_dto(row) if row is not None else None

    # ── Startup reconciliation ────────────────────────────────────────────

    @classmethod
    async def reconcile_on_startup(cls) -> int:
        """Reset EXECUTING rows (crash leftovers) to PENDING. Never auto-approves."""
        async with async_session_factory() as db:
            repo = PendingApprovalRepository(db)
            count = await repo.reset_executing_to_pending()
            await db.commit()
        if count:
            logger.warning(
                "approval_queue_reconciled",
                recovered=count,
                note="EXECUTING rows reset to PENDING; execution never completed",
            )
        return count


# Process-wide singleton. DB-backed; no mutable state on the object itself.
_queue: ApprovalQueue | None = None


def get_approval_queue() -> ApprovalQueue:
    global _queue
    if _queue is None:
        _queue = ApprovalQueue()
    return _queue


__all__ = ["ApprovalQueue", "ApprovalStatus", "PendingApproval", "get_approval_queue"]
