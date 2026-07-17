"""Unit tests for the agent-ops operability services (finish pass).

Covers the mock MCP session, the human-approval queue (propose/approve/reject
with segregation of duties + 0-unapproved guarantee), and the shared task-runner
singleton. Uses the mock MCP path (``MCP_USE_MOCK`` default True) — no network.
"""

from __future__ import annotations

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


def _queue() -> ApprovalQueue:
    # Build a runtime with local + MCP write tools over the mock session.
    mcp = build_mcp_tools(
        feature_on=True, enabled_server_ids=["msgraph", "servicenow"], write_actions_on=True
    )
    runtime = AgentToolRuntime({**TOOL_REGISTRY, **mcp}, audit_sink=lambda e: None)
    return ApprovalQueue(runtime=runtime)


def _ctx(*perms: str) -> ToolContext:
    return ToolContext(user_id="u1", permissions=frozenset(perms))


class TestApprovalQueue:
    async def test_propose_needs_no_permission(self) -> None:
        q = _queue()
        rec = await q.propose(
            tool_name="reset_mfa",
            raw_args={"user_principal_name": "a@b.com", "idempotency_key": "k-123456"},
            proposer_id="agent-1",
        )
        assert rec.status is ApprovalStatus.PENDING  # low-privilege propose

    async def test_propose_invalid_args(self) -> None:
        q = _queue()
        rec = await q.propose(tool_name="reset_mfa", raw_args={"bad": 1}, proposer_id="a")
        assert rec.status is ApprovalStatus.INVALID

    async def test_propose_rejects_non_gated_tool(self) -> None:
        q = _queue()
        rec = await q.propose(tool_name="kb_search", raw_args={"query": "x"}, proposer_id="a")
        assert rec.status is ApprovalStatus.INVALID  # read tool isn't approvable

    async def test_approve_executes_with_permission(self) -> None:
        q = _queue()
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
        q = _queue()
        rec = await q.propose(
            tool_name="reset_mfa",
            raw_args={"user_principal_name": "a@b.com", "idempotency_key": "k-123456"},
            proposer_id="agent-1",
        )
        decided = await q.approve(rec.id, _ctx())  # approver lacks write perm
        assert decided.status is ApprovalStatus.FAILED
        assert decided.result is None

    async def test_reject(self) -> None:
        q = _queue()
        rec = await q.propose(
            tool_name="entra_unlock_account",
            raw_args={"user_principal_name": "a@b.com", "idempotency_key": "k-123456"},
            proposer_id="agent-1",
        )
        rejected = q.reject(rec.id, "lead-1")
        assert rejected.status is ApprovalStatus.REJECTED

    async def test_list_filters_by_status(self) -> None:
        q = _queue()
        await q.propose(
            tool_name="reset_mfa",
            raw_args={"user_principal_name": "a@b.com", "idempotency_key": "k-123456"},
            proposer_id="agent-1",
        )
        assert len(q.list(status=ApprovalStatus.PENDING)) == 1
        assert q.list(status=ApprovalStatus.APPROVED) == []

    async def test_concurrent_approve_executes_exactly_once(self) -> None:
        """Two concurrent approve() calls on the same id must execute ONCE.

        Regression for the TOCTOU window: the PENDING check and the status
        update straddled an await, so both callers passed the check and both
        dispatched. The record is now claimed (EXECUTING) synchronously before
        the first await, so the second caller returns early.
        """
        import asyncio

        q = _queue()
        rec = await q.propose(
            tool_name="reset_mfa",
            raw_args={"user_principal_name": "a@b.com", "idempotency_key": "k-123456"},
            proposer_id="agent-1",
        )

        calls = {"n": 0}
        original = q._runtime.execute_approved

        async def counting_execute(*args, **kwargs):
            calls["n"] += 1
            await asyncio.sleep(0)  # yield so both coroutines interleave
            return await original(*args, **kwargs)

        q._runtime.execute_approved = counting_execute
        results = await asyncio.gather(
            q.approve(rec.id, _ctx(DIRW)),
            q.approve(rec.id, _ctx(DIRW)),
        )

        assert calls["n"] == 1  # executed exactly once despite two approvals
        assert rec.status is ApprovalStatus.APPROVED
        assert all(r.id == rec.id for r in results)


# ── Task runner singleton ────────────────────────────────────────────────────


class TestTaskSingleton:
    async def test_singleton_identity_and_run(self) -> None:
        from app.services.agents.tasks.factory import get_task_runner
        from app.services.agents.tasks.models import AgentTask, AgentTaskStatus

        r1 = get_task_runner()
        r2 = get_task_runner()
        assert r1 is r2  # shared instance across API + lifespan

        task = await r1.enqueue(AgentTask(task_type="knowledge_improvement_sweep"))
        await r1.run_once()
        stored = await r1._store.get(task.id)  # noqa: SLF001
        assert stored.status is AgentTaskStatus.COMPLETED
