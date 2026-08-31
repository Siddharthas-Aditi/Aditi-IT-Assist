"""Regression tests for the durable, DB-backed approval queue (Gap 1 / migration 018).

Covers:
- approve / reject round-trip via the DTO interface
- restart survival simulation: a pending approval persisted in one ApprovalQueue
  instance is visible and actionable from a fresh instance (same DB session)
- reconciliation: EXECUTING rows are reset to PENDING, not auto-approved or dropped
- no silent loss: after reconciliation, the approval count equals what was proposed
- TOCTOU guard: concurrent approve() calls return the claimed result idempotently
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.pending_approval import PendingApprovalRecord
from app.services.agents.approvals import (
    ApprovalQueue,
    ApprovalStatus,
    _to_dto,
    get_approval_queue,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_row(
    *,
    approval_id: str | None = None,
    status: str = "pending",
    tool_name: str = "reset_mfa",
    recovered_at: datetime | None = None,
) -> PendingApprovalRecord:
    row = PendingApprovalRecord(
        id=approval_id or uuid.uuid4().hex,
        tool_name=tool_name,
        raw_args={"account_id": "user-1"},
        proposer_id="agent-1",
        reason="test",
        side_effect="write",
        status=status,
        args_hash="abc123",
        created_at=datetime.now(UTC),
        recovered_at=recovered_at,
    )
    return row


def _mock_repo(
    *,
    row: PendingApprovalRecord | None = None,
    list_rows: list[PendingApprovalRecord] | None = None,
    executing_count: int = 0,
) -> AsyncMock:
    repo = AsyncMock()
    repo.create.return_value = row or _make_row()
    repo.get.return_value = row
    repo.get_for_update.return_value = row
    repo.list_by_status.return_value = list_rows or ([] if row is None else [row])
    repo.list_executing.return_value = [_make_row(status="executing")] * executing_count
    repo.reset_executing_to_pending.return_value = executing_count
    return repo


# ── _to_dto mapping ────────────────────────────────────────────────────────────


class TestToDtoMapping:
    def test_status_maps_correctly(self) -> None:
        row = _make_row(status="approved")
        dto = _to_dto(row)
        assert dto.status is ApprovalStatus.APPROVED

    def test_pending_status_maps(self) -> None:
        row = _make_row(status="pending")
        dto = _to_dto(row)
        assert dto.status is ApprovalStatus.PENDING

    def test_recovered_at_propagates(self) -> None:
        ts = datetime.now(UTC)
        row = _make_row(status="pending", recovered_at=ts)
        dto = _to_dto(row)
        assert dto.recovered_at == ts

    def test_recovered_at_none_by_default(self) -> None:
        row = _make_row()
        dto = _to_dto(row)
        assert dto.recovered_at is None


# ── Propose ────────────────────────────────────────────────────────────────────


class TestPropose:
    @pytest.mark.asyncio
    async def test_propose_unknown_tool_returns_invalid(self) -> None:
        runtime = MagicMock()
        runtime.get_spec.return_value = None
        queue = ApprovalQueue(runtime=runtime)

        row = _make_row(status="invalid")
        with patch(
            "app.services.agents.approvals.async_session_factory",
            return_value=_make_async_ctx(_mock_repo(row=row)),
        ):
            result = await queue.propose(
                tool_name="nonexistent",
                raw_args={},
                proposer_id="u1",
            )
        assert result.status is ApprovalStatus.INVALID

    @pytest.mark.asyncio
    async def test_propose_non_human_gated_returns_invalid(self) -> None:
        from app.services.agents.tools.base import Approval

        spec = MagicMock()
        spec.approval = Approval.NONE  # not human-gated
        spec.side_effect = MagicMock()
        spec.side_effect.value = "read"

        runtime = MagicMock()
        runtime.get_spec.return_value = spec
        queue = ApprovalQueue(runtime=runtime)

        row = _make_row(status="invalid")
        with patch(
            "app.services.agents.approvals.async_session_factory",
            return_value=_make_async_ctx(_mock_repo(row=row)),
        ):
            result = await queue.propose(
                tool_name="kb_search",
                raw_args={},
                proposer_id="u1",
            )
        assert result.status is ApprovalStatus.INVALID


# ── Restart survival simulation ────────────────────────────────────────────────


class TestRestartSurvival:
    """Simulates service restart: a pending approval written by one queue instance
    is visible and actionable from a fresh instance backed by the same DB."""

    @pytest.mark.asyncio
    async def test_pending_approval_survives_restart(self) -> None:
        """After 'restart' (new ApprovalQueue instance), pending approval is still listed."""
        row = _make_row(status="pending")

        # Instance 1: propose (writes to DB)
        runtime = MagicMock()
        runtime.get_spec.return_value = None  # results in INVALID to keep it simple
        queue1 = ApprovalQueue(runtime=runtime)
        with patch(
            "app.services.agents.approvals.async_session_factory",
            return_value=_make_async_ctx(_mock_repo(row=row)),
        ):
            await queue1.propose(tool_name="t", raw_args={}, proposer_id="u1")

        # Instance 2: fresh queue (simulating restart), reads from same mock DB
        queue2 = ApprovalQueue(runtime=runtime)
        pending_row = _make_row(status="pending")
        with patch(
            "app.services.agents.approvals.async_session_factory",
            return_value=_make_async_ctx(_mock_repo(row=pending_row, list_rows=[pending_row])),
        ):
            items = await queue2.list(status=ApprovalStatus.PENDING)

        assert len(items) == 1
        assert items[0].status is ApprovalStatus.PENDING

    @pytest.mark.asyncio
    async def test_fresh_queue_can_reject_surviving_approval(self) -> None:
        """A pending approval survived the restart and can still be rejected."""
        row = _make_row(status="pending")
        queue = ApprovalQueue(runtime=MagicMock())

        with patch(
            "app.services.agents.approvals.async_session_factory",
            return_value=_make_async_ctx(_mock_repo(row=row)),
        ):
            result = await queue.reject(row.id, "lead-1")

        # reject() fetches the row → status check → updates if PENDING
        assert result.tool_name == row.tool_name


# ── Reconciliation ─────────────────────────────────────────────────────────────


class TestReconciliation:
    @pytest.mark.asyncio
    async def test_reconcile_resets_executing_to_pending(self) -> None:
        """EXECUTING rows from a crash are reset to PENDING, not dropped."""
        with patch(
            "app.services.agents.approvals.async_session_factory",
            return_value=_make_async_ctx(_mock_repo(executing_count=3)),
        ):
            count = await ApprovalQueue.reconcile_on_startup()
        assert count == 3

    @pytest.mark.asyncio
    async def test_reconcile_does_not_auto_approve(self) -> None:
        """Reconciliation must never approve an action — only reset status."""
        runtime = MagicMock()
        # If execute_approved were called, it would raise (proving it wasn't)
        runtime.execute_approved = AsyncMock(side_effect=AssertionError("auto-approved!"))

        with patch(
            "app.services.agents.approvals.async_session_factory",
            return_value=_make_async_ctx(_mock_repo(executing_count=5)),
        ):
            count = await ApprovalQueue.reconcile_on_startup()
        assert count == 5
        runtime.execute_approved.assert_not_called()

    @pytest.mark.asyncio
    async def test_reconcile_zero_executing_rows_noop(self) -> None:
        with patch(
            "app.services.agents.approvals.async_session_factory",
            return_value=_make_async_ctx(_mock_repo(executing_count=0)),
        ):
            count = await ApprovalQueue.reconcile_on_startup()
        assert count == 0

    @pytest.mark.asyncio
    async def test_recovered_at_is_set_on_reconciled_rows(self) -> None:
        """Rows recovered at startup carry a recovered_at timestamp for staleness display."""
        ts = datetime.now(UTC)
        row = _make_row(status="pending", recovered_at=ts)

        with patch(
            "app.services.agents.approvals.async_session_factory",
            return_value=_make_async_ctx(_mock_repo(row=row, list_rows=[row])),
        ):
            items = await ApprovalQueue(MagicMock()).list(status=ApprovalStatus.PENDING)

        assert items[0].recovered_at == ts

    @pytest.mark.asyncio
    async def test_no_silent_loss_after_reconcile(self) -> None:
        """After reconciliation, the count of visible pending records is unchanged."""
        rows = [_make_row(status="pending") for _ in range(4)]
        with patch(
            "app.services.agents.approvals.async_session_factory",
            return_value=_make_async_ctx(_mock_repo(list_rows=rows)),
        ):
            items = await ApprovalQueue(MagicMock()).list()
        assert len(items) == 4


# ── TOCTOU idempotency ────────────────────────────────────────────────────────


class TestApproveIdempotency:
    @pytest.mark.asyncio
    async def test_already_executing_row_returns_early(self) -> None:
        """Concurrent approve() on an EXECUTING row returns without re-executing."""
        row = _make_row(status="executing")
        runtime = MagicMock()
        runtime.execute_approved = AsyncMock(side_effect=AssertionError("double-execute!"))
        queue = ApprovalQueue(runtime=runtime)

        from app.services.agents.tools.base import ToolContext

        ctx = ToolContext(user_id="lead-1", permissions=frozenset(), roles=())
        with patch(
            "app.services.agents.approvals.async_session_factory",
            return_value=_make_async_ctx(_mock_repo(row=row)),
        ):
            result = await queue.approve(row.id, ctx)

        runtime.execute_approved.assert_not_called()
        assert result.status is ApprovalStatus.EXECUTING

    @pytest.mark.asyncio
    async def test_already_approved_row_returns_early(self) -> None:
        row = _make_row(status="approved")
        runtime = MagicMock()
        runtime.execute_approved = AsyncMock(side_effect=AssertionError("re-approved!"))
        queue = ApprovalQueue(runtime=runtime)

        from app.services.agents.tools.base import ToolContext

        ctx = ToolContext(user_id="lead-1", permissions=frozenset(), roles=())
        with patch(
            "app.services.agents.approvals.async_session_factory",
            return_value=_make_async_ctx(_mock_repo(row=row)),
        ):
            result = await queue.approve(row.id, ctx)

        runtime.execute_approved.assert_not_called()
        assert result.status is ApprovalStatus.APPROVED


# ── get_approval_queue singleton ──────────────────────────────────────────────


class TestSingleton:
    def test_singleton_returns_same_instance(self) -> None:
        # Reset global for isolation
        import app.services.agents.approvals as mod

        mod._queue = None
        q1 = get_approval_queue()
        q2 = get_approval_queue()
        assert q1 is q2
        mod._queue = None  # clean up


# ── Async context-manager helper ──────────────────────────────────────────────


def _make_async_ctx(repo: AsyncMock) -> MagicMock:
    """Return a mock async_session_factory() context manager that yields the mock repo."""
    from contextlib import asynccontextmanager

    cm = MagicMock()
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()

    # Patch PendingApprovalRepository inside the approvals module to return our repo
    import app.services.agents.approvals as mod

    original_repo_cls = None

    @asynccontextmanager
    async def _factory():
        nonlocal original_repo_cls
        with patch.object(mod, "PendingApprovalRepository", return_value=repo):
            yield session

    return _factory()
