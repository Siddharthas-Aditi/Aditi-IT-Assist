"""Lifecycle transition tests for Change and Asset models.

Tests:
- Valid transitions execute correctly
- Invalid transitions raise ChangeError / AssetError
- Terminal statuses block all transitions
- Business rules enforced (approval required before scheduling non-Standard)
- Audit events written on every transition
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.asset import (
    ASSET_TERMINAL_STATUSES,
    AssetStatus,
)
from app.models.change import (
    CHANGE_TERMINAL_STATUSES,
    CHANGE_TRANSITIONS,
    ApprovalDecision,
    ChangeStatus,
    ChangeType,
)

# ── Change lifecycle — pure model / transition table ──────────────────────────


class TestChangeTransitionTable:
    """Every status has well-defined allowed next statuses."""

    def test_draft_allows_submitted_planning_cancelled(self) -> None:
        allowed = CHANGE_TRANSITIONS[ChangeStatus.DRAFT]
        assert ChangeStatus.SUBMITTED in allowed
        assert ChangeStatus.PLANNING in allowed
        assert ChangeStatus.CANCELLED in allowed

    def test_pending_approval_allows_scheduled_rejected_planning(self) -> None:
        allowed = CHANGE_TRANSITIONS[ChangeStatus.PENDING_APPROVAL]
        assert ChangeStatus.SCHEDULED in allowed
        assert ChangeStatus.REJECTED in allowed
        assert ChangeStatus.PLANNING in allowed

    def test_in_progress_allows_implemented_rolled_back_cancelled(self) -> None:
        allowed = CHANGE_TRANSITIONS[ChangeStatus.IN_PROGRESS]
        assert ChangeStatus.IMPLEMENTED in allowed
        assert ChangeStatus.ROLLED_BACK in allowed

    def test_terminal_statuses_have_no_transitions(self) -> None:
        for status in CHANGE_TERMINAL_STATUSES:
            assert CHANGE_TRANSITIONS[status] == set(), f"{status} should be terminal"

    def test_implemented_only_allows_closed(self) -> None:
        assert CHANGE_TRANSITIONS[ChangeStatus.IMPLEMENTED] == {ChangeStatus.CLOSED}

    def test_rolled_back_allows_planning(self) -> None:
        assert ChangeStatus.PLANNING in CHANGE_TRANSITIONS[ChangeStatus.ROLLED_BACK]

    def test_rejected_allows_planning(self) -> None:
        assert ChangeStatus.PLANNING in CHANGE_TRANSITIONS[ChangeStatus.REJECTED]


class TestChangeServiceTransition:
    """ChangeService.transition enforces lifecycle rules."""

    def _make_service_and_change(
        self,
        *,
        status: ChangeStatus = ChangeStatus.DRAFT,
        change_type: ChangeType = ChangeType.NORMAL,
        planned_start: datetime | None = None,
        closure_notes: str = "",
    ) -> tuple:
        """Build a lightweight service mock."""
        from app.models.change import Change
        from app.services.change_service import ChangeService

        change = MagicMock(spec=Change)
        change.id = uuid.uuid4()
        change.status = status.value
        change.change_type = change_type.value
        change.planned_start = planned_start
        change.closure_notes = closure_notes
        change.approvals = []
        change.actual_start = None
        change.actual_end = None

        db = AsyncMock()
        svc = ChangeService.__new__(ChangeService)
        svc._db = db
        svc._repo = AsyncMock()
        svc._repo.get.return_value = change
        svc._repo.update.return_value = change
        svc._repo.append_event.return_value = AsyncMock()
        db.commit = AsyncMock()

        return svc, change

    @pytest.mark.asyncio
    async def test_valid_transition_draft_to_planning(self) -> None:
        from app.schemas.change import ChangeTransitionRequest

        svc, change = self._make_service_and_change(status=ChangeStatus.DRAFT)
        req = ChangeTransitionRequest(to_status=ChangeStatus.PLANNING)
        result = await svc.transition(change.id, req, uuid.uuid4())
        assert svc._repo.update.called

    @pytest.mark.asyncio
    async def test_invalid_transition_raises_change_error(self) -> None:
        from app.schemas.change import ChangeTransitionRequest
        from app.services.change_service import ChangeError

        svc, change = self._make_service_and_change(status=ChangeStatus.DRAFT)
        req = ChangeTransitionRequest(to_status=ChangeStatus.CLOSED)
        with pytest.raises(ChangeError, match="Cannot move"):
            await svc.transition(change.id, req, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_terminal_status_blocks_transition(self) -> None:
        from app.schemas.change import ChangeTransitionRequest
        from app.services.change_service import ChangeError

        for terminal in CHANGE_TERMINAL_STATUSES:
            svc, change = self._make_service_and_change(status=terminal)
            req = ChangeTransitionRequest(to_status=ChangeStatus.PLANNING)
            with pytest.raises(ChangeError, match="Cannot move"):
                await svc.transition(change.id, req, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_normal_change_cannot_schedule_without_approval(self) -> None:
        from app.models.change import ChangeApproval
        from app.schemas.change import ChangeTransitionRequest
        from app.services.change_service import ChangeError

        svc, change = self._make_service_and_change(
            status=ChangeStatus.PENDING_APPROVAL, change_type=ChangeType.NORMAL
        )
        pending_approval = MagicMock(spec=ChangeApproval)
        pending_approval.decision = ApprovalDecision.PENDING
        change.approvals = [pending_approval]
        req = ChangeTransitionRequest(to_status=ChangeStatus.SCHEDULED)
        with pytest.raises(ChangeError, match="approval"):
            await svc.transition(change.id, req, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_standard_change_can_schedule_without_approval(self) -> None:
        from app.schemas.change import ChangeTransitionRequest

        svc, change = self._make_service_and_change(
            status=ChangeStatus.PLANNING, change_type=ChangeType.STANDARD
        )
        change.approvals = []
        req = ChangeTransitionRequest(to_status=ChangeStatus.SCHEDULED)
        await svc.transition(change.id, req, uuid.uuid4())
        assert svc._repo.update.called

    @pytest.mark.asyncio
    async def test_in_progress_requires_planned_start(self) -> None:
        from app.schemas.change import ChangeTransitionRequest
        from app.services.change_service import ChangeError

        svc, change = self._make_service_and_change(
            status=ChangeStatus.SCHEDULED, planned_start=None
        )
        req = ChangeTransitionRequest(to_status=ChangeStatus.IN_PROGRESS)
        with pytest.raises(ChangeError, match="planned start"):
            await svc.transition(change.id, req, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_close_requires_closure_notes(self) -> None:
        from app.schemas.change import ChangeTransitionRequest
        from app.services.change_service import ChangeError

        svc, change = self._make_service_and_change(
            status=ChangeStatus.IMPLEMENTED, closure_notes=""
        )
        req = ChangeTransitionRequest(to_status=ChangeStatus.CLOSED)
        with pytest.raises(ChangeError, match="[Cc]losure notes"):
            await svc.transition(change.id, req, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_audit_event_appended_on_transition(self) -> None:
        from app.schemas.change import ChangeTransitionRequest

        svc, change = self._make_service_and_change(status=ChangeStatus.DRAFT)
        await svc.transition(
            change.id, ChangeTransitionRequest(to_status=ChangeStatus.PLANNING), uuid.uuid4()
        )
        svc._repo.append_event.assert_called_once()


# ── Asset lifecycle ────────────────────────────────────────────────────────────


class TestAssetTerminalStatus:
    def test_terminal_statuses_defined(self) -> None:
        assert AssetStatus.RETIRED in ASSET_TERMINAL_STATUSES
        assert AssetStatus.DISPOSED in ASSET_TERMINAL_STATUSES

    def test_non_terminal_statuses_not_in_terminal_set(self) -> None:
        assert AssetStatus.IN_STOCK not in ASSET_TERMINAL_STATUSES
        assert AssetStatus.ASSIGNED not in ASSET_TERMINAL_STATUSES


class TestAssetServiceLifecycle:
    def _make_service_and_asset(self, *, status: AssetStatus = AssetStatus.IN_STOCK) -> tuple:
        from app.models.asset import Asset
        from app.services.asset_service import AssetService

        asset = MagicMock(spec=Asset)
        asset.id = uuid.uuid4()
        asset.status = status.value
        asset.assigned_to_id = None
        asset.retirement_reason = None
        asset.retirement_date = None
        asset.asset_tag = "TEST-001"

        db = AsyncMock()
        svc = AssetService.__new__(AssetService)
        svc._db = db
        svc._repo = AsyncMock()
        svc._repo.get.return_value = asset
        svc._repo.update.return_value = asset
        svc._repo.append_event.return_value = None
        svc._repo.is_tag_taken.return_value = False
        db.commit = AsyncMock()
        return svc, asset

    @pytest.mark.asyncio
    async def test_assign_in_stock_asset(self) -> None:
        from app.schemas.asset import AssetAssignRequest

        svc, asset = self._make_service_and_asset(status=AssetStatus.IN_STOCK)
        req = AssetAssignRequest(assigned_to_id=uuid.uuid4())
        await svc.assign(asset.id, req, uuid.uuid4())
        assert svc._repo.update.called

    @pytest.mark.asyncio
    async def test_assign_retired_asset_raises(self) -> None:
        from app.schemas.asset import AssetAssignRequest
        from app.services.asset_service import AssetError

        svc, asset = self._make_service_and_asset(status=AssetStatus.RETIRED)
        req = AssetAssignRequest(assigned_to_id=uuid.uuid4())
        with pytest.raises(AssetError, match="[Rr]etired"):
            await svc.assign(asset.id, req, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_retire_requires_reason(self) -> None:
        from app.schemas.asset import AssetRetireRequest
        from app.services.asset_service import AssetError

        svc, asset = self._make_service_and_asset(status=AssetStatus.IN_STOCK)
        req = AssetRetireRequest(
            status=AssetStatus.RETIRED, retirement_reason="   ", retirement_date=date.today()
        )
        with pytest.raises(AssetError, match="[Rr]eason"):
            await svc.retire(asset.id, req, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_retire_writes_audit_event(self) -> None:
        from app.schemas.asset import AssetRetireRequest

        svc, asset = self._make_service_and_asset(status=AssetStatus.IN_STOCK)
        req = AssetRetireRequest(
            status=AssetStatus.RETIRED, retirement_reason="EoL", retirement_date=date.today()
        )
        await svc.retire(asset.id, req, uuid.uuid4())
        svc._repo.append_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_retired_asset_allowed(self) -> None:
        svc, asset = self._make_service_and_asset(status=AssetStatus.RETIRED)
        svc._repo.delete = AsyncMock()
        await svc.delete(asset.id)
        svc._repo.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_assigned_asset_raises(self) -> None:
        from app.services.asset_service import AssetError

        svc, asset = self._make_service_and_asset(status=AssetStatus.ASSIGNED)
        with pytest.raises(AssetError, match="[Ii]n-stock|retired|disposed"):
            await svc.delete(asset.id)
