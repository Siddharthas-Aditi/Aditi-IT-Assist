"""Change management API endpoints — full CRUD plus lifecycle transitions."""

from __future__ import annotations

import uuid  # noqa: TC003 — FastAPI resolves path param types at startup
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import P
from app.models.change import ChangeStatus
from app.schemas.change import (
    ApprovalCreate,
    ApprovalDecide,
    ApprovalResponse,
    ChangeCreate,
    ChangeListResponse,
    ChangeResponse,
    ChangeTaskCreate,
    ChangeTaskResponse,
    ChangeTaskUpdate,
    ChangeTransitionRequest,
    ChangeUpdate,
)
from app.services.auth.dependencies import get_current_active_user, require_permissions
from app.services.auth.service import AuthService
from app.services.change_service import ChangeError, ChangeService

router = APIRouter()

_DB = Annotated[AsyncSession, Depends(get_db)]
_CreateChange = Annotated[object, Depends(require_permissions(P.CHANGE_CREATE))]
_ReadChange = Annotated[object, Depends(require_permissions(P.CHANGE_READ))]
_UpdateChange = Annotated[object, Depends(require_permissions(P.CHANGE_UPDATE))]
_DeleteChange = Annotated[object, Depends(require_permissions(P.CHANGE_DELETE))]
_ApproveChange = Annotated[object, Depends(require_permissions(P.CHANGE_APPROVE))]
_ImplementChange = Annotated[object, Depends(require_permissions(P.CHANGE_IMPLEMENT))]
_CloseChange = Annotated[object, Depends(require_permissions(P.CHANGE_CLOSE))]
_RollbackChange = Annotated[object, Depends(require_permissions(P.CHANGE_ROLLBACK))]
_CurrentUser = Annotated[object, Depends(get_current_active_user)]


def _svc(db: AsyncSession) -> ChangeService:
    return ChangeService(db)


async def _actor_id(user: object, db: AsyncSession) -> uuid.UUID:
    from app.models.auth import User as UserModel

    if isinstance(user, UserModel):
        return user.id
    raise HTTPException(status_code=401, detail="Not authenticated")


def _http(exc: ChangeError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


@router.post("", response_model=ChangeResponse, status_code=201)
async def create_change(
    body: ChangeCreate, _: _CreateChange, user: _CurrentUser, db: _DB
) -> ChangeResponse:
    try:
        change = await _svc(db).create(body, await _actor_id(user, db))
        return ChangeResponse.model_validate(change)
    except ChangeError as exc:
        raise _http(exc) from exc


@router.get("", response_model=ChangeListResponse)
async def list_changes(
    _: _ReadChange,
    db: _DB,
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ChangeListResponse:
    status_enum = ChangeStatus(status) if status else None
    items, total = await _svc(db).list(status=status_enum, limit=limit, offset=offset)
    return ChangeListResponse(items=[ChangeResponse.model_validate(c) for c in items], total=total)


@router.get("/{change_id}", response_model=ChangeResponse)
async def get_change(_: _ReadChange, change_id: uuid.UUID, db: _DB) -> ChangeResponse:
    try:
        change = await _svc(db).get(change_id)
        return ChangeResponse.model_validate(change)
    except ChangeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{change_id}", response_model=ChangeResponse)
async def update_change(
    body: ChangeUpdate, _: _UpdateChange, user: _CurrentUser, change_id: uuid.UUID, db: _DB
) -> ChangeResponse:
    try:
        change = await _svc(db).update(change_id, body, await _actor_id(user, db))
        return ChangeResponse.model_validate(change)
    except ChangeError as exc:
        raise _http(exc) from exc


@router.delete("/{change_id}", status_code=204)
async def delete_change(
    _: _DeleteChange, user: _CurrentUser, change_id: uuid.UUID, db: _DB
) -> None:
    try:
        await _svc(db).delete(change_id)
    except ChangeError as exc:
        raise _http(exc) from exc


@router.post("/{change_id}/transition", response_model=ChangeResponse)
async def transition_change(
    body: ChangeTransitionRequest,
    change_id: uuid.UUID,
    db: _DB,
    user: _CurrentUser,
    # Permit is checked per-destination inside the endpoint.
    _read: _ReadChange,
) -> ChangeResponse:
    """Transition a change to a new status.

    Permission required depends on target status:
    - In Progress / Implemented / Rolled Back → change:implement
    - Closed                                   → change:close
    - All others (submit, plan, schedule, …)   → change:update
    """
    from app.models.auth import User as UserModel

    caller = user
    if not isinstance(caller, UserModel):
        raise HTTPException(status_code=401)

    perms = frozenset(await AuthService(db).get_user_permissions(caller))
    implement_targets = {
        ChangeStatus.IN_PROGRESS,
        ChangeStatus.IMPLEMENTED,
        ChangeStatus.ROLLED_BACK,
    }
    if body.to_status in implement_targets and P.CHANGE_IMPLEMENT.value not in perms:
        raise HTTPException(status_code=403, detail="change:implement permission required")
    if body.to_status == ChangeStatus.CLOSED and P.CHANGE_CLOSE.value not in perms:
        raise HTTPException(status_code=403, detail="change:close permission required")
    if body.to_status == ChangeStatus.ROLLED_BACK and P.CHANGE_ROLLBACK.value not in perms:
        raise HTTPException(status_code=403, detail="change:rollback permission required")

    try:
        change = await _svc(db).transition(change_id, body, caller.id)
        return ChangeResponse.model_validate(change)
    except ChangeError as exc:
        raise _http(exc) from exc


# ── Approvals ─────────────────────────────────────────────────────────


@router.post("/{change_id}/approvals", response_model=ApprovalResponse, status_code=201)
async def add_approval(
    body: ApprovalCreate, _: _UpdateChange, user: _CurrentUser, change_id: uuid.UUID, db: _DB
) -> ApprovalResponse:
    try:
        approval = await _svc(db).add_approval(change_id, body, await _actor_id(user, db))
        return ApprovalResponse.model_validate(approval)
    except ChangeError as exc:
        raise _http(exc) from exc


@router.post("/{change_id}/approvals/{approval_id}/decide", response_model=ApprovalResponse)
async def decide_approval(
    body: ApprovalDecide,
    _: _ApproveChange,
    user: _CurrentUser,
    change_id: uuid.UUID,
    approval_id: uuid.UUID,
    db: _DB,
) -> ApprovalResponse:
    try:
        approval = await _svc(db).decide_approval(
            change_id, approval_id, body, await _actor_id(user, db)
        )
        return ApprovalResponse.model_validate(approval)
    except ChangeError as exc:
        raise _http(exc) from exc


# ── Tasks ─────────────────────────────────────────────────────────────


@router.post("/{change_id}/tasks", response_model=ChangeTaskResponse, status_code=201)
async def add_task(
    body: ChangeTaskCreate, _: _UpdateChange, user: _CurrentUser, change_id: uuid.UUID, db: _DB
) -> ChangeTaskResponse:
    try:
        task = await _svc(db).add_task(change_id, body, await _actor_id(user, db))
        return ChangeTaskResponse.model_validate(task)
    except ChangeError as exc:
        raise _http(exc) from exc


@router.patch("/{change_id}/tasks/{task_id}", response_model=ChangeTaskResponse)
async def update_task(
    body: ChangeTaskUpdate,
    _: _UpdateChange,
    user: _CurrentUser,
    change_id: uuid.UUID,
    task_id: uuid.UUID,
    db: _DB,
) -> ChangeTaskResponse:
    try:
        task = await _svc(db).update_task(change_id, task_id, body, await _actor_id(user, db))
        return ChangeTaskResponse.model_validate(task)
    except ChangeError as exc:
        raise _http(exc) from exc
