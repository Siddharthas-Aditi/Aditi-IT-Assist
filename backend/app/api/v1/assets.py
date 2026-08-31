"""Asset management API endpoints — CRUD plus lifecycle actions."""

from __future__ import annotations

import uuid  # noqa: TC003 — FastAPI resolves path/query param types at startup
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import P
from app.models.asset import AssetStatus
from app.schemas.asset import (
    AssetAssignRequest,
    AssetCreate,
    AssetListResponse,
    AssetResponse,
    AssetRetireRequest,
    AssetUpdate,
)
from app.services.asset_service import AssetError, AssetService
from app.services.auth.dependencies import get_current_active_user, require_permissions

router = APIRouter()

_DB = Annotated[AsyncSession, Depends(get_db)]
_CreateAsset = Annotated[object, Depends(require_permissions(P.ASSET_CREATE))]
_ReadAsset = Annotated[object, Depends(require_permissions(P.ASSET_READ))]
_UpdateAsset = Annotated[object, Depends(require_permissions(P.ASSET_UPDATE))]
_DeleteAsset = Annotated[object, Depends(require_permissions(P.ASSET_DELETE))]
_AssignAsset = Annotated[object, Depends(require_permissions(P.ASSET_ASSIGN))]
_RetireAsset = Annotated[object, Depends(require_permissions(P.ASSET_RETIRE))]
_TransferAsset = Annotated[object, Depends(require_permissions(P.ASSET_TRANSFER))]
_CurrentUser = Annotated[object, Depends(get_current_active_user)]


def _svc(db: AsyncSession) -> AssetService:
    return AssetService(db)


async def _actor_id(user: object) -> uuid.UUID:
    from app.models.auth import User as UserModel

    if isinstance(user, UserModel):
        return user.id
    raise HTTPException(status_code=401, detail="Not authenticated")


def _http(exc: AssetError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


@router.post("", response_model=AssetResponse, status_code=201)
async def create_asset(
    body: AssetCreate, _: _CreateAsset, user: _CurrentUser, db: _DB
) -> AssetResponse:
    try:
        asset = await _svc(db).create(body, await _actor_id(user))
        return AssetResponse.model_validate(asset)
    except AssetError as exc:
        raise _http(exc) from exc


@router.get("", response_model=AssetListResponse)
async def list_assets(
    _: _ReadAsset,
    db: _DB,
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AssetListResponse:
    status_enum = AssetStatus(status) if status else None
    items, total = await _svc(db).list(status=status_enum, limit=limit, offset=offset)
    return AssetListResponse(items=[AssetResponse.model_validate(a) for a in items], total=total)


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(_: _ReadAsset, asset_id: uuid.UUID, db: _DB) -> AssetResponse:
    try:
        asset = await _svc(db).get(asset_id)
        return AssetResponse.model_validate(asset)
    except AssetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{asset_id}", response_model=AssetResponse)
async def update_asset(
    body: AssetUpdate, _: _UpdateAsset, user: _CurrentUser, asset_id: uuid.UUID, db: _DB
) -> AssetResponse:
    try:
        asset = await _svc(db).update(asset_id, body, await _actor_id(user))
        return AssetResponse.model_validate(asset)
    except AssetError as exc:
        raise _http(exc) from exc


@router.delete("/{asset_id}", status_code=204)
async def delete_asset(_: _DeleteAsset, user: _CurrentUser, asset_id: uuid.UUID, db: _DB) -> None:
    try:
        await _svc(db).delete(asset_id)
    except AssetError as exc:
        raise _http(exc) from exc


@router.post("/{asset_id}/assign", response_model=AssetResponse)
async def assign_asset(
    body: AssetAssignRequest, _: _AssignAsset, user: _CurrentUser, asset_id: uuid.UUID, db: _DB
) -> AssetResponse:
    try:
        asset = await _svc(db).assign(asset_id, body, await _actor_id(user))
        return AssetResponse.model_validate(asset)
    except AssetError as exc:
        raise _http(exc) from exc


@router.post("/{asset_id}/retire", response_model=AssetResponse)
async def retire_asset(
    body: AssetRetireRequest, _: _RetireAsset, user: _CurrentUser, asset_id: uuid.UUID, db: _DB
) -> AssetResponse:
    try:
        asset = await _svc(db).retire(asset_id, body, await _actor_id(user))
        return AssetResponse.model_validate(asset)
    except AssetError as exc:
        raise _http(exc) from exc


@router.post("/{asset_id}/transfer", response_model=AssetResponse)
async def transfer_asset(
    new_assigned_to_id: uuid.UUID,
    _: _TransferAsset,
    user: _CurrentUser,
    asset_id: uuid.UUID,
    db: _DB,
) -> AssetResponse:
    try:
        asset = await _svc(db).transfer(asset_id, new_assigned_to_id, await _actor_id(user))
        return AssetResponse.model_validate(asset)
    except AssetError as exc:
        raise _http(exc) from exc
