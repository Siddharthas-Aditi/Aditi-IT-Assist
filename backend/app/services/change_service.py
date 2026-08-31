"""Change management service — lifecycle enforcement and business rules.

All state transitions are validated here before any DB write.
Every transition appends an immutable ChangeEvent row for audit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.models.change import (
    CHANGE_TERMINAL_STATUSES,
    CHANGE_TRANSITIONS,
    ApprovalDecision,
    Change,
    ChangeApproval,
    ChangeEvent,
    ChangeEventType,
    ChangeStatus,
    ChangeTask,
    ChangeType,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.change import (
        ApprovalCreate,
        ApprovalDecide,
        ChangeCreate,
        ChangeTaskCreate,
        ChangeTaskUpdate,
        ChangeTransitionRequest,
        ChangeUpdate,
    )


class ChangeError(Exception):
    """Raised when a business rule prevents a change operation."""


class ChangeService:
    """Service layer for Change management — no direct DB queries; delegates to repository."""

    def __init__(self, db: AsyncSession) -> None:
        from app.repositories.change_repository import ChangeRepository

        self._db = db
        self._repo = ChangeRepository(db)

    async def create(self, data: ChangeCreate, actor_id: uuid.UUID) -> Change:
        change_number = await self._repo.next_change_number()
        change = Change(
            id=uuid.uuid4(),
            change_number=change_number,
            source_ticket_id=data.source_ticket_id,
            requested_by_id=actor_id,
            title=data.title,
            description=data.description,
            change_type=data.change_type,
            status=ChangeStatus.DRAFT,
            priority=data.priority,
            impact=data.impact,
            risk=data.risk,
            department=data.department,
            category=data.category,
            maintenance_window=data.maintenance_window,
            planned_start=data.planned_start,
            planned_end=data.planned_end,
            emergency_justification=data.emergency_justification,
            planning_data=data.planning_data.model_dump(),
        )
        await self._repo.create(change)
        await self._repo.append_event(
            ChangeEvent(
                id=uuid.uuid4(),
                change_id=change.id,
                actor_id=actor_id,
                event_type=ChangeEventType.CREATED,
                to_status=ChangeStatus.DRAFT,
                detail=f"Change {change_number} created",
            )
        )
        if data.asset_ids:
            await self._repo.set_asset_links(change.id, data.asset_ids)
        await self._db.commit()
        return change

    async def get(self, change_id: uuid.UUID) -> Change:
        change = await self._repo.get(change_id)
        if change is None:
            raise ChangeError(f"Change {change_id} not found")
        return change

    async def list(
        self,
        *,
        status: ChangeStatus | None = None,
        requested_by_id: uuid.UUID | None = None,
        assigned_to_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Change], int]:
        return await self._repo.find_all(
            status=status,
            requested_by_id=requested_by_id,
            assigned_to_id=assigned_to_id,
            limit=limit,
            offset=offset,
        )

    async def update(self, change_id: uuid.UUID, data: ChangeUpdate, actor_id: uuid.UUID) -> Change:
        change = await self.get(change_id)
        if change.status in CHANGE_TERMINAL_STATUSES:
            raise ChangeError(f"Cannot update a {change.status} change")
        patch: dict[str, Any] = data.model_dump(exclude_unset=True)
        if "planning_data" in patch and patch["planning_data"] is not None:
            patch["planning_data"] = (
                patch["planning_data"].model_dump()
                if hasattr(patch["planning_data"], "model_dump")
                else patch["planning_data"]
            )
        for field, value in patch.items():
            setattr(change, field, value)
        await self._repo.update(change)
        await self._repo.append_event(
            ChangeEvent(
                id=uuid.uuid4(),
                change_id=change.id,
                actor_id=actor_id,
                event_type=ChangeEventType.FIELD_UPDATED,
                detail=f"Fields updated: {', '.join(patch.keys())}",
            )
        )
        await self._db.commit()
        return change

    async def transition(
        self, change_id: uuid.UUID, req: ChangeTransitionRequest, actor_id: uuid.UUID
    ) -> Change:
        change = await self.get(change_id)
        self._validate_transition(change, req.to_status)
        old_status = change.status
        change.status = req.to_status
        if req.to_status == ChangeStatus.IN_PROGRESS and change.actual_start is None:
            change.actual_start = datetime.now(UTC)
        if req.to_status in (ChangeStatus.IMPLEMENTED, ChangeStatus.ROLLED_BACK):
            change.actual_end = datetime.now(UTC)
        await self._repo.update(change)
        await self._repo.append_event(
            ChangeEvent(
                id=uuid.uuid4(),
                change_id=change.id,
                actor_id=actor_id,
                event_type=ChangeEventType.STATUS_CHANGED,
                from_status=old_status,
                to_status=req.to_status,
                detail=req.comment or None,
            )
        )
        await self._db.commit()
        return change

    def _validate_transition(self, change: Change, to_status: ChangeStatus) -> None:
        allowed = CHANGE_TRANSITIONS.get(ChangeStatus(change.status), set())
        if to_status not in allowed:
            raise ChangeError(
                f"Cannot move change from {change.status!r} to {to_status!r}. "
                f"Allowed: {sorted(s.value for s in allowed) or 'none (terminal)'}"
            )
        # Standard changes may reach Scheduled without approval; others must clear approvals.
        if to_status == ChangeStatus.SCHEDULED and change.change_type != ChangeType.STANDARD:
            outstanding = [a for a in change.approvals if a.decision == ApprovalDecision.PENDING]
            if outstanding:
                raise ChangeError(
                    f"{change.change_type} changes require all approvals before scheduling"
                )
        if to_status == ChangeStatus.IN_PROGRESS and not change.planned_start:
            raise ChangeError("Set a planned start before starting implementation")
        if (
            to_status in (ChangeStatus.IMPLEMENTED, ChangeStatus.CLOSED)
            and not change.closure_notes.strip()
        ):
            raise ChangeError("Closure notes are required")

    async def delete(self, change_id: uuid.UUID) -> None:
        change = await self.get(change_id)
        if change.status not in (ChangeStatus.DRAFT, ChangeStatus.CANCELLED, ChangeStatus.REJECTED):
            raise ChangeError("Only draft, cancelled, or rejected changes may be deleted")
        await self._repo.delete(change)
        await self._db.commit()

    # ── Approvals ──────────────────────────────────────────────────────

    async def add_approval(
        self, change_id: uuid.UUID, data: ApprovalCreate, actor_id: uuid.UUID
    ) -> ChangeApproval:
        change = await self.get(change_id)
        if change.status in CHANGE_TERMINAL_STATUSES:
            raise ChangeError("Cannot add approval to a terminal change")
        approval = ChangeApproval(
            id=uuid.uuid4(),
            change_id=change_id,
            stage=data.stage,
            approver_id=data.approver_id,
        )
        await self._repo.add_approval(approval)
        await self._repo.append_event(
            ChangeEvent(
                id=uuid.uuid4(),
                change_id=change_id,
                actor_id=actor_id,
                event_type=ChangeEventType.APPROVAL_REQUESTED,
                detail=f"Stage {data.stage} approval requested",
            )
        )
        await self._db.commit()
        return approval

    async def decide_approval(
        self,
        change_id: uuid.UUID,
        approval_id: uuid.UUID,
        data: ApprovalDecide,
        actor_id: uuid.UUID,
    ) -> ChangeApproval:
        approval = await self._repo.get_approval(approval_id)
        if approval is None or approval.change_id != change_id:
            raise ChangeError("Approval not found on this change")
        if approval.decision != ApprovalDecision.PENDING:
            raise ChangeError("Approval already decided")
        approval.decision = data.decision
        approval.comments = data.comments
        approval.decided_at = datetime.now(UTC)
        await self._repo.update_approval(approval)
        await self._repo.append_event(
            ChangeEvent(
                id=uuid.uuid4(),
                change_id=change_id,
                actor_id=actor_id,
                event_type=ChangeEventType.APPROVAL_DECIDED,
                detail=f"Stage {approval.stage}: {data.decision.value}. {data.comments}",
            )
        )
        await self._db.commit()
        return approval

    # ── Tasks ───────────────────────────────────────────────────────────

    async def add_task(
        self, change_id: uuid.UUID, data: ChangeTaskCreate, actor_id: uuid.UUID
    ) -> ChangeTask:
        change = await self.get(change_id)
        if change.status in CHANGE_TERMINAL_STATUSES:
            raise ChangeError("Cannot add tasks to a terminal change")
        task = ChangeTask(
            id=uuid.uuid4(), change_id=change_id, label=data.label, position=data.position
        )
        await self._repo.add_task(task)
        await self._repo.append_event(
            ChangeEvent(
                id=uuid.uuid4(),
                change_id=change_id,
                actor_id=actor_id,
                event_type=ChangeEventType.TASK_UPDATED,
                detail=f"Task added: {data.label}",
            )
        )
        await self._db.commit()
        return task

    async def update_task(
        self, change_id: uuid.UUID, task_id: uuid.UUID, data: ChangeTaskUpdate, actor_id: uuid.UUID
    ) -> ChangeTask:
        task = await self._repo.get_task(task_id)
        if task is None or task.change_id != change_id:
            raise ChangeError("Task not found on this change")
        if data.done is not None:
            task.done = data.done
        if data.label is not None:
            task.label = data.label
        await self._repo.update_task(task)
        await self._repo.append_event(
            ChangeEvent(
                id=uuid.uuid4(),
                change_id=change_id,
                actor_id=actor_id,
                event_type=ChangeEventType.TASK_UPDATED,
                detail=f"Task updated: {task.label}",
            )
        )
        await self._db.commit()
        return task


__all__ = ["ChangeError", "ChangeService"]
