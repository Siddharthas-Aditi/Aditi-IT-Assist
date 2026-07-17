"""Human-approval queue for agent write actions (Phase 8 operability).

A small in-memory queue that turns the runtime's propose→approve→execute
contract into something an IT specialist can act on:

* an IT agent (or an agent turn) **proposes** a governed write action — it is
  dispatched through the :class:`AgentToolRuntime`, which (because every write
  tool is ``approval=human``) returns ``needs_approval`` and the action is
  parked here, executing nothing;
* an authorized lead **approves** it — the exact captured invocation is
  re-dispatched via ``execute_approved`` under the approver's identity, so RBAC,
  audit, and idempotency all still apply;
* or it is **rejected**.

In-memory (single instance) by design for now — same trade-off as the agent
task store; the API/UI contract is identical to a future DB-backed queue. No
write ever executes without an explicit approve() call (the runtime guarantees
it; the action-safety eval pins it).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import ValidationError

from app.core.logging import get_logger
from app.services.agents.tools.base import Approval, ToolContext, ToolInvocation
from app.services.agents.tools.registry import build_default_runtime

logger = get_logger(__name__)


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    EXECUTING = "executing"  # claimed by an approve() call; execution in flight
    APPROVED = "approved"  # approved + executed successfully
    REJECTED = "rejected"
    FAILED = "failed"  # approved but execution errored
    INVALID = "invalid"  # proposal rejected by the runtime (bad args / not gated)


@dataclass
class PendingApproval:
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


class ApprovalQueue:
    """In-memory store + workflow for human-gated agent actions."""

    def __init__(self, runtime=None) -> None:
        # Include MCP write tools + device-execution tools so both are dispatchable
        # from the shared approval queue (Phase 8 writes + Phase 9 device actions).
        self._runtime = runtime or build_default_runtime(
            include_mcp=True, include_device_execution=True
        )
        self._records: dict[str, PendingApproval] = {}

    # ── Proposing ────────────────────────────────────────────────────────

    async def propose(
        self,
        *,
        tool_name: str,
        raw_args: dict[str, Any],
        proposer_id: str,
        reason: str = "",
    ) -> PendingApproval:
        """Validate + park a write action for human approval.

        Segregation of duties: proposing is low-privilege (an IT agent suggests
        a remediation), so RBAC is **not** checked here — it is enforced at
        approval time against the *approver*. Proposing only validates that the
        tool exists, the args are well-formed, and the tool is genuinely
        human-gated (a non-gated/unknown tool or bad args is recorded
        ``invalid`` and is never executable).
        """
        from app.services.agents.tools.runtime import _hash_obj

        spec = self._runtime.get_spec(tool_name)
        record = PendingApproval(
            tool_name=tool_name,
            raw_args=raw_args,
            proposer_id=proposer_id,
            reason=reason,
            side_effect=spec.side_effect.value if spec else "unknown",
            mcp_server=spec.mcp_server if spec else None,
            args_hash=_hash_obj(raw_args),
        )
        if spec is None:
            record.status = ApprovalStatus.INVALID
            record.error = f"unknown tool {tool_name!r}"
        elif spec.approval is not Approval.HUMAN:
            record.status = ApprovalStatus.INVALID
            record.error = "tool is not human-approval-gated; nothing to queue"
        else:
            try:
                spec.args_model.model_validate(raw_args)
                record.status = ApprovalStatus.PENDING
            except ValidationError as exc:
                record.status = ApprovalStatus.INVALID
                record.error = f"invalid arguments: {exc.error_count()} error(s)"
        self._records[record.id] = record
        logger.info(
            "approval_proposed",
            id=record.id,
            tool=tool_name,
            status=record.status.value,
            proposer=proposer_id,
        )
        return record

    # ── Deciding ─────────────────────────────────────────────────────────

    async def approve(self, approval_id: str, approver: ToolContext) -> PendingApproval:
        record = self._records.get(approval_id)
        if record is None:
            raise KeyError(approval_id)
        if record.status is not ApprovalStatus.PENDING:
            return record
        # Claim the record BEFORE the first await. The event loop can only switch
        # coroutines at an await point, so setting a non-PENDING status here (with
        # no await in between) makes the check-and-claim atomic: a second
        # concurrent approve() on the same id sees EXECUTING and returns early,
        # preventing a double execution of a human-gated write/device action.
        record.status = ApprovalStatus.EXECUTING

        from app.services.agents.tools.runtime import ProposedAction

        proposed = ProposedAction(
            invocation=ToolInvocation(record.tool_name, record.raw_args),
            tool_name=record.tool_name,
            side_effect=record.side_effect,
            mcp_server=record.mcp_server,
            description="",
            args_hash=record.args_hash,
        )
        outcome = await self._runtime.execute_approved(
            proposed, approver, allowed_tools=(record.tool_name,), approver_id=approver.user_id
        )
        record.decided_at = datetime.now(UTC)
        record.decided_by = approver.user_id
        if outcome.executed:
            record.status = ApprovalStatus.APPROVED
            record.result = (
                outcome.result.model_dump(mode="json")
                if outcome.result is not None and hasattr(outcome.result, "model_dump")
                else None
            )
        else:
            record.status = ApprovalStatus.FAILED
            record.error = outcome.error or outcome.status.value
        logger.info(
            "approval_decided",
            id=approval_id,
            status=record.status.value,
            approver=approver.user_id,
        )
        return record

    def reject(self, approval_id: str, approver_id: str) -> PendingApproval:
        record = self._records.get(approval_id)
        if record is None:
            raise KeyError(approval_id)
        if record.status is ApprovalStatus.PENDING:
            record.status = ApprovalStatus.REJECTED
            record.decided_at = datetime.now(UTC)
            record.decided_by = approver_id
        return record

    # ── Reading ──────────────────────────────────────────────────────────

    def list(self, *, status: ApprovalStatus | None = None) -> list[PendingApproval]:
        items = sorted(self._records.values(), key=lambda r: r.created_at, reverse=True)
        return [r for r in items if status is None or r.status is status]

    def get(self, approval_id: str) -> PendingApproval | None:
        return self._records.get(approval_id)


# Process-wide singleton so the API and any agent turn share one queue.
_queue: ApprovalQueue | None = None


def get_approval_queue() -> ApprovalQueue:
    global _queue
    if _queue is None:
        _queue = ApprovalQueue()
    return _queue


__all__ = ["ApprovalQueue", "ApprovalStatus", "PendingApproval", "get_approval_queue"]
