"""Ticket categories API — admin-managed 3-level hierarchy.

Routes (all require IT staff access; write routes require it_admin):
  GET    /ticket-categories/tree     — full tree (IT staff read)
  GET    /ticket-categories          — flat list, filterable by level/parent
  POST   /ticket-categories          — create node (admin only)
  POST   /ticket-categories/reorder  — batch sort_order update (admin only)
  PATCH  /ticket-categories/{id}     — update node (admin only)
  DELETE /ticket-categories/{id}     — delete leaf node (admin only)
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.auth.dependencies import require_roles
from app.services.ticket_category_service import TicketCategoryError, TicketCategoryService

router = APIRouter()

DBDep = Annotated[AsyncSession, Depends(get_db)]
ITStaffDep = Annotated[object, Depends(require_roles("it_agent", "it_lead", "it_admin"))]
AdminOnlyDep = Annotated[object, Depends(require_roles("it_admin"))]


# ── Schemas ────────────────────────────────────────────────────────────────


class CategoryOut(BaseModel):
    id: str
    name: str
    level: int
    parent_id: str | None = None
    is_active: bool
    sort_order: int


class CategoryTreeNode(CategoryOut):
    children: list["CategoryTreeNode"] = []


class CategoryTreeResponse(BaseModel):
    categories: list[CategoryTreeNode]


class CategoryCreate(BaseModel):
    name: str
    level: int  # 1 | 2 | 3
    parent_id: str | None = None
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class CategoryReorderRequest(BaseModel):
    ordered_ids: list[str]


# ── Helpers ────────────────────────────────────────────────────────────────


def _svc(db: DBDep) -> TicketCategoryService:
    return TicketCategoryService(db)


def _out(cat) -> CategoryOut:
    return CategoryOut(
        id=str(cat.id),
        name=cat.name,
        level=cat.level,
        parent_id=str(cat.parent_id) if cat.parent_id else None,
        is_active=cat.is_active,
        sort_order=cat.sort_order,
    )


def _category_error_status(exc: TicketCategoryError) -> int:
    """Map service errors to HTTP status — 404 for missing, 409 for conflicts."""
    if str(exc) == "Category not found":
        return 404
    return 409


# ── Routes ─────────────────────────────────────────────────────────────────


@router.get("/tree", response_model=CategoryTreeResponse)
async def get_category_tree(
    _actor: ITStaffDep,
    db: DBDep,
) -> CategoryTreeResponse:
    """Full 3-level tree for the manager UI (admin) or cascading dropdowns (IT staff)."""
    svc = _svc(db)
    tree = await svc.tree()
    return CategoryTreeResponse(**tree)


@router.get("", response_model=list[CategoryOut])
async def list_categories(
    _actor: ITStaffDep,
    db: DBDep,
    level: int | None = None,
    parent_id: str | None = None,
    active_only: bool = True,
) -> list[CategoryOut]:
    """Flat list — filterable by level and parent_id (drives cascading dropdowns)."""
    svc = _svc(db)
    parent_uuid = uuid.UUID(parent_id) if parent_id else None
    if level is not None:
        cats = await svc.list_by_level(level, parent_id=parent_uuid, active_only=active_only)
    else:
        cats = await svc.list_all(active_only=active_only)
    return [_out(c) for c in cats]


@router.post("", response_model=CategoryOut, status_code=201)
async def create_category(
    data: CategoryCreate,
    _actor: AdminOnlyDep,
    db: DBDep,
) -> CategoryOut:
    """Create a new category node (admin only)."""
    svc = _svc(db)
    parent_uuid = uuid.UUID(data.parent_id) if data.parent_id else None
    try:
        cat = await svc.create(
            name=data.name,
            level=data.level,
            parent_id=parent_uuid,
            sort_order=data.sort_order,
        )
        await db.commit()
    except TicketCategoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _out(cat)


@router.post("/reorder", status_code=204)
async def reorder_categories(
    data: CategoryReorderRequest,
    _actor: AdminOnlyDep,
    db: DBDep,
) -> None:
    """Batch update sort_order (position = index). Admin only."""
    svc = _svc(db)
    await svc.reorder([uuid.UUID(i) for i in data.ordered_ids])
    await db.commit()


@router.patch("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: uuid.UUID,
    data: CategoryUpdate,
    _actor: AdminOnlyDep,
    db: DBDep,
) -> CategoryOut:
    """Update a category node (admin only)."""
    svc = _svc(db)
    try:
        cat = await svc.update(
            category_id,
            name=data.name,
            is_active=data.is_active,
            sort_order=data.sort_order,
        )
        await db.commit()
    except TicketCategoryError as exc:
        raise HTTPException(status_code=_category_error_status(exc), detail=str(exc)) from exc
    return _out(cat)


@router.delete("/{category_id}", status_code=204)
async def delete_category(
    category_id: uuid.UUID,
    _actor: AdminOnlyDep,
    db: DBDep,
) -> None:
    """Delete a leaf category node (admin only).

    Returns 409 if the category still has children — admin must remove
    children first to prevent orphan subtrees.
    """
    svc = _svc(db)
    try:
        await svc.delete(category_id)
        await db.commit()
    except TicketCategoryError as exc:
        raise HTTPException(status_code=_category_error_status(exc), detail=str(exc)) from exc
