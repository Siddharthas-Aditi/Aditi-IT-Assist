"""Pydantic schemas for the Change management domain."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.change import ApprovalDecision, ChangeStatus, ChangeType


class ChangePlanningData(BaseModel):
    reason_for_change: str = ""
    impact_analysis: str = ""
    rollout_plan: str = ""
    backup_plan: str = ""
    validation_plan: str = ""
    communication_plan: str = ""
    implementation_steps: str = ""
    rollback_trigger: str = ""
    post_implementation_review: str = ""


class ChangeCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    description: str = ""
    change_type: ChangeType = ChangeType.NORMAL
    priority: str = "medium"
    impact: str = "medium"
    risk: str = "medium"
    department: str | None = None
    category: str | None = None
    maintenance_window: str | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    emergency_justification: str = ""
    planning_data: ChangePlanningData = Field(default_factory=ChangePlanningData)
    source_ticket_id: uuid.UUID | None = None
    asset_ids: list[uuid.UUID] = Field(default_factory=list)


class ChangeUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=512)
    description: str | None = None
    priority: str | None = None
    impact: str | None = None
    risk: str | None = None
    department: str | None = None
    category: str | None = None
    maintenance_window: str | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    emergency_justification: str | None = None
    planning_data: ChangePlanningData | None = None
    assigned_to_id: uuid.UUID | None = None
    closure_notes: str | None = None


class ApprovalCreate(BaseModel):
    approver_id: uuid.UUID
    stage: int = Field(1, ge=1)


class ApprovalDecide(BaseModel):
    decision: ApprovalDecision
    comments: str = ""


class ChangeTaskCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=512)
    position: int = 0


class ChangeTaskUpdate(BaseModel):
    done: bool | None = None
    label: str | None = None


class ApprovalResponse(BaseModel):
    id: uuid.UUID
    change_id: uuid.UUID
    stage: int
    approver_id: uuid.UUID
    decision: str
    comments: str
    decided_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChangeTaskResponse(BaseModel):
    id: uuid.UUID
    change_id: uuid.UUID
    label: str
    done: bool
    position: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ChangeEventResponse(BaseModel):
    id: uuid.UUID
    change_id: uuid.UUID
    actor_id: uuid.UUID | None = None
    event_type: str
    from_status: str | None = None
    to_status: str | None = None
    detail: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChangeResponse(BaseModel):
    id: uuid.UUID
    change_number: str
    source_ticket_id: uuid.UUID | None = None
    requested_by_id: uuid.UUID
    assigned_to_id: uuid.UUID | None = None
    title: str
    description: str
    change_type: str
    status: str
    priority: str
    impact: str
    risk: str
    department: str | None = None
    category: str | None = None
    maintenance_window: str | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    actual_start: datetime | None = None
    actual_end: datetime | None = None
    closure_notes: str
    emergency_justification: str
    planning_data: dict[str, Any]
    approvals: list[ApprovalResponse] = []
    tasks: list[ChangeTaskResponse] = []
    events: list[ChangeEventResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChangeListResponse(BaseModel):
    items: list[ChangeResponse]
    total: int


class ChangeTransitionRequest(BaseModel):
    to_status: ChangeStatus
    comment: str = ""
