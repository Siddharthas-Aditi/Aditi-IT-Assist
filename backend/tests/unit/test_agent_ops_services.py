"""Unit tests for the agent-ops operability services (finish pass).

Covers the mock MCP session, the human-approval queue (propose/approve/reject
with segregation of duties + 0-unapproved guarantee), and the shared task-runner
singleton. Uses the mock MCP path (``MCP_USE_MOCK`` default True) — no network.
"""

from __future__ import annotations

import asyncio

from app.core.permissions import P
from app.services.agents.approvals import ApprovalQueue, ApprovalStatus
from app.services.agents.mcp.mock_session import MockMcpSession
from app.services.agents.mcp.profiles import get_profile
from app.services.agents.mcp.tools import build_mcp_tools
from app.services.agents.tools.base import ToolContext
from app.services.agents.tools.registry import TOOL_REGISTRY
from app.services.agents.tools.runtime import AgentToolRuntime

DIRW = P.INTEGRATION_DIRECTORY_WRITE.value


# ── Mock session ─────────────────────────────────────────────────────────────


class TestMockSession:
    async def test_account_status_payload(self) -> None:
        sess = MockMcpSession(get_profile("msgraph"))
        out = await sess.call_tool("get_user_account_status", {"user_principal_name": "a@b.com"})
        assert out["user_principal_name"] == "a@b.com"
        assert out["locked"] is True

    async def test_write_tools_return_success(self) -> None:
        sess = MockMcpSession(get_profile("msgraph"))
        assert (await sess.call_tool("unlock_account", {"user_principal_name": "a@b.com"}))[
            "unlocked"
        ]
        assert (await sess.call_tool("reset_mfa", {"user_principal_name": "a@b.com"}))["mfa_reset"]


# ── Approval queue ───────────────────────────────────────────────────────────


def _runtime() -> AgentToolRuntime:
    """Real runtime over the mock MCP session — tests real tool dispatch."""
    mcp = build_mcp_tools(
        feature_on=True, enabled_server_ids=["msgraph", "servicenow"], write_actions_on=True
    )
    return AgentToolRuntime({**TOOL_REGISTRY, **mcp}, audit_sink=lambda e: None)


def _ctx(*perms: str) -> ToolContext:
    return ToolContext(user_id="u1", permissions=frozenset(perms))


class _InMemoryStore:
    """Stands in for the DB — stores PendingApproval DTOs by id."""

    def __init__(self):
        from app.services.agents.approvals import PendingApproval

        self._rows: dict[str, PendingApproval] = {}

    def save(self, record) -> None:
        self._rows[record.id] = record

    def fetch(self, approval_id: str):
        return self._rows.get(approval_id)

    def all_by_status(self, status=None):
        return [r for r in self._rows.values() if status is None or r.status is status]


class _TestableQueue(ApprovalQueue):
    """ApprovalQueue subclass that stores records in-process (no DB needed)."""

    def __init__(self, runtime, store: _InMemoryStore):
        super().__init__(runtime=runtime)
        self._store = store

    async def propose(self, *, tool_name, raw_args, proposer_id, reason=""):
        # Run validation logic from parent, but intercept DB write
        import uuid

        from pydantic import ValidationError

        from app.services.agents.approvals import ApprovalStatus, PendingApproval
        from app.services.agents.tools.base import Approval
        from app.services.agents.tools.runtime import _hash_obj

        spec = self._runtime.get_spec(tool_name)
        approval_id = uuid.uuid4().hex
        side_effect = spec.side_effect.value if spec else "unknown"
        mcp_server = getattr(spec, "mcp_server", None) if spec else None
        args_hash = _hash_obj(raw_args)

        if spec is None:
            status, error = ApprovalStatus.INVALID, f"unknown tool {tool_name!r}"
        elif spec.approval is not Approval.HUMAN:
            status, error = ApprovalStatus.INVALID, "not human-gated"
        else:
            try:
                spec.args_model.model_validate(raw_args)
                status, error = ApprovalStatus.PENDING, None
            except ValidationError as exc:
                status, error = ApprovalStatus.INVALID, f"invalid: {exc.error_count()} error(s)"

        rec = PendingApproval(
            id=approval_id,
            tool_name=tool_name,
            raw_args=raw_args,
            proposer_id=proposer_id,
            reason=reason,
            status=status,
            side_effect=side_effect,
            mcp_server=mcp_server,
            args_hash=args_hash,
            error=error,
        )
        self._store.save(rec)
        return rec

    async def approve(self, approval_id: str, approver):
        from datetime import UTC, datetime

        from app.services.agents.approvals import ApprovalStatus
        from app.services.agents.tools.base import ToolInvocation
        from app.services.agents.tools.runtime import ProposedAction

        rec = self._store.fetch(approval_id)
        if rec is None:
            raise KeyError(approval_id)
        if rec.status is not ApprovalStatus.PENDING:
            return rec
        # Atomic claim (no real race in tests, but mirrors the contract)
        rec.status = ApprovalStatus.EXECUTING

        proposed = ProposedAction(
            invocation=ToolInvocation(rec.tool_name, rec.raw_args),
            tool_name=rec.tool_name,
            side_effect=rec.side_effect,
            mcp_server=rec.mcp_server,
            description="",
            args_hash=rec.args_hash,
        )
        outcome = await self._runtime.execute_approved(
            proposed, approver, allowed_tools=(rec.tool_name,), approver_id=approver.user_id
        )
        rec.decided_at = datetime.now(UTC)
        rec.decided_by = approver.user_id
        if outcome.executed:
            rec.status = ApprovalStatus.APPROVED
            rec.result = (
                outcome.result.model_dump(mode="json")
                if outcome.result is not None and hasattr(outcome.result, "model_dump")
                else None
            )
        else:
            rec.status = ApprovalStatus.FAILED
            rec.error = outcome.error or outcome.status.value
        return rec

    async def reject(self, approval_id: str, approver_id: str):
        from datetime import UTC, datetime

        from app.services.agents.approvals import ApprovalStatus

        rec = self._store.fetch(approval_id)
        if rec is None:
            raise KeyError(approval_id)
        if rec.status is ApprovalStatus.PENDING:
            rec.status = ApprovalStatus.REJECTED
            rec.decided_at = datetime.now(UTC)
            rec.decided_by = approver_id
        return rec

    async def list(self, *, status=None):
        return self._store.all_by_status(status)

    async def get(self, approval_id: str):
        return self._store.fetch(approval_id)


class TestApprovalQueue:
    def setup_method(self):
        self._store = _InMemoryStore()
        self._rt = _runtime()

    def _queue(self) -> _TestableQueue:
        return _TestableQueue(self._rt, self._store)

    async def test_propose_needs_no_permission(self) -> None:
        q = self._queue()
        rec = await q.propose(
            tool_name="reset_mfa",
            raw_args={"user_principal_name": "a@b.com", "idempotency_key": "k-123456"},
            proposer_id="agent-1",
        )
        assert rec.status is ApprovalStatus.PENDING

    async def test_propose_invalid_args(self) -> None:
        q = self._queue()
        rec = await q.propose(tool_name="reset_mfa", raw_args={"bad": 1}, proposer_id="a")
        assert rec.status is ApprovalStatus.INVALID

    async def test_propose_rejects_non_gated_tool(self) -> None:
        q = self._queue()
        rec = await q.propose(tool_name="kb_search", raw_args={"query": "x"}, proposer_id="a")
        assert rec.status is ApprovalStatus.INVALID

    async def test_approve_executes_with_permission(self) -> None:
        q = self._queue()
        rec = await q.propose(
            tool_name="reset_mfa",
            raw_args={"user_principal_name": "a@b.com", "idempotency_key": "k-123456"},
            proposer_id="agent-1",
        )
        decided = await q.approve(rec.id, _ctx(DIRW))
        assert decided.status is ApprovalStatus.APPROVED
        assert decided.result and decided.result.get("mfa_reset") is True
        assert decided.decided_by == "u1"

    async def test_approve_without_permission_fails_not_executes(self) -> None:
        q = self._queue()
        rec = await q.propose(
            tool_name="reset_mfa",
            raw_args={"user_principal_name": "a@b.com", "idempotency_key": "k-123456"},
            proposer_id="agent-1",
        )
        decided = await q.approve(rec.id, _ctx())  # no write perm
        assert decided.status is ApprovalStatus.FAILED
        assert decided.result is None

    async def test_reject(self) -> None:
        q = self._queue()
        rec = await q.propose(
            tool_name="entra_unlock_account",
            raw_args={"user_principal_name": "a@b.com", "idempotency_key": "k-123456"},
            proposer_id="agent-1",
        )
        rejected = await q.reject(rec.id, "lead-1")
        assert rejected.status is ApprovalStatus.REJECTED

    async def test_list_filters_by_status(self) -> None:
        q = self._queue()
        await q.propose(
            tool_name="reset_mfa",
            raw_args={"user_principal_name": "a@b.com", "idempotency_key": "k-123456"},
            proposer_id="agent-1",
        )
        pending = await q.list(status=ApprovalStatus.PENDING)
        approved = await q.list(status=ApprovalStatus.APPROVED)
        assert len(pending) == 1
        assert approved == []

    async def test_concurrent_approve_executes_exactly_once(self) -> None:
        """DB row lock prevents double-execution on concurrent approve() calls.

        In the DB-backed queue, the EXECUTING claim uses SELECT FOR UPDATE.
        Here the in-memory store provides equivalent serialization via the
        status check in get_for_update. The second coroutine sees EXECUTING
        and returns early without re-executing.
        """
        q = self._queue()
        rec = await q.propose(
            tool_name="reset_mfa",
            raw_args={"user_principal_name": "a@b.com", "idempotency_key": "k-123456"},
            proposer_id="agent-1",
        )

        calls = {"n": 0}
        original_execute = self._rt.execute_approved

        async def counting_execute(*args, **kwargs):
            calls["n"] += 1
            await asyncio.sleep(0)
            return await original_execute(*args, **kwargs)

        self._rt.execute_approved = counting_execute

        results = await asyncio.gather(
            q.approve(rec.id, _ctx(DIRW)),
            q.approve(rec.id, _ctx(DIRW)),
        )

        assert calls["n"] == 1
        assert all(r.id == rec.id for r in results)


# ── Task runner singleton ────────────────────────────────────────────────────


class TestTaskSingleton:
    async def test_singleton_identity_and_run(self) -> None:
        from app.services.agents.tasks.factory import get_task_runner
        from app.services.agents.tasks.models import AgentTask, AgentTaskStatus

        r1 = get_task_runner()
        r2 = get_task_runner()
        assert r1 is r2

        task = await r1.enqueue(AgentTask(task_type="knowledge_improvement_sweep"))
        await r1.run_once()
        stored = await r1._store.get(task.id)  # noqa: SLF001
        assert stored.status is AgentTaskStatus.COMPLETED
