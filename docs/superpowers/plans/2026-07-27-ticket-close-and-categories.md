# IT Ticket Close + Cascading Categories — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce IT-only ticket close with mandatory resolution notes + Category → Sub-Category → Item, add an admin-managed cascading category tree, and upgrade the Operations ticket workspace with a Properties panel + Close modal.

**Architecture:** Reuse WIP migration `014` + `TicketCategory` + `TicketCategoryService`. Add cascade validation + `TicketService.close_ticket` (block `closed` via status update). Mount category APIs. Frontend: shared cascade fields, Close modal, Properties rail on `TicketWorkspacePage`, Admin Manage Category page. Seed a starter tree so every L2 has ≥1 Item.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async / Alembic / PostgreSQL. React 18 + TypeScript + Vite. pytest + Vitest/RTL.

**Spec:** `docs/superpowers/specs/2026-07-27-ticket-close-and-categories-design.md`

## Global Constraints

- Line length 100; Ruff must pass (`uv run ruff check . && uv run ruff format --check .`).
- Services never commit; API routes own `await db.commit()`.
- Employees never close; only `it_agent` / `it_lead` / `it_admin`.
- Item is **always** required on close; if L2 has zero active Items → 400.
- `POST /tickets/{id}/status` must reject `closed` (409); only `POST /tickets/{id}/close`.
- Category writes: `it_admin` only. Category reads: IT staff.
- Do not invent Group/Department/Location fields.
- Frontend: no `any`; mirror RBAC with `isITStaff` / `isAdmin`.
- Prefer finishing existing WIP over rewriting it.

---

## File Structure

**Already present (finish, do not rewrite):**
- `backend/alembic/versions/014_ticket_categories_and_close_fields.py`
- `backend/app/models/ticket.py` — `TicketCategory` + close columns
- `backend/app/services/ticket_category_service.py`
- `backend/app/api/v1/ticket_categories.py`
- `backend/app/api/v1/tickets.py` — `TicketCloseRequest` / `TicketUpdateRequest` schemas

**Create:**
- `backend/app/services/ticket_category_validation.py` — pure/async cascade name validation
- `backend/tests/unit/test_ticket_close.py`
- `backend/tests/unit/test_ticket_category_service.py`
- `backend/tests/api/test_ticket_close_api.py`
- `backend/tests/api/test_ticket_categories_api.py`
- `frontend/src/features/tickets/CategoryCascadeFields.tsx`
- `frontend/src/features/tickets/CloseTicketModal.tsx`
- `frontend/src/features/tickets/TicketPropertiesPanel.tsx`
- `frontend/src/features/tickets/CloseTicketModal.test.tsx`
- `frontend/src/pages/admin/TicketCategoriesPage.tsx`

**Modify:**
- `backend/app/models/__init__.py` — export `TicketCategory`
- `backend/app/api/v1/router.py` — mount ticket-categories
- `backend/app/api/v1/ticket_categories.py` — add `/reorder`
- `backend/app/api/v1/tickets.py` — close + PATCH endpoints; block status=closed; extend response
- `backend/app/services/ticket_service.py` — `close_ticket`, `update_ticket_properties`, status guard
- `backend/scripts/seed_enterprise.py` — seed category tree
- `frontend/src/lib/api.ts` — close/update + categories client
- `frontend/src/pages/operations/TicketWorkspacePage.tsx` — layout + wire modal/panel
- `frontend/src/pages/operations/TicketWorkspacePage.test.tsx` — close gating
- `frontend/src/app/App.tsx` — admin route
- `frontend/src/components/layouts/AdminLayout.tsx` — nav (it_admin)
- `frontend/src/components/RouteGuard.tsx` — `ITAdminRoute`
- `memory/domain-model.md` — TicketCategory + close invariants

---

### Task 1: Mount category API + export model + reorder

**Files:**
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/app/api/v1/ticket_categories.py`
- Test: `backend/tests/api/test_ticket_categories_api.py`

**Interfaces:**
- Produces: `GET/POST/PATCH/DELETE /api/v1/ticket-categories*`, `POST /api/v1/ticket-categories/reorder`

- [ ] **Step 1: Export `TicketCategory` from models package**

In `backend/app/models/__init__.py`, change the ticket import to:

```python
from app.models.ticket import Ticket, TicketCategory, TicketComment, TicketEvent
```

Add `TicketCategory` to `__all__` if the module defines one.

- [ ] **Step 2: Mount the router**

In `backend/app/api/v1/router.py`, after the tickets router import/include:

```python
from app.api.v1.ticket_categories import router as ticket_categories_router

api_router.include_router(
    ticket_categories_router, prefix="/ticket-categories", tags=["ticket-categories"]
)
```

Place the include immediately after `tickets_router`.

- [ ] **Step 3: Add reorder endpoint**

Append to `backend/app/api/v1/ticket_categories.py`:

```python
class CategoryReorderRequest(BaseModel):
    ordered_ids: list[str]


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
```

Ensure `GET /tree` is registered **before** any `/{category_id}` routes (already true).

- [ ] **Step 4: Write API smoke tests**

Create `backend/tests/api/test_ticket_categories_api.py`:

```python
"""API tests for /ticket-categories — RBAC + basic tree read."""

from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient


class TestTicketCategoriesRBAC:
    async def test_tree_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/ticket-categories/tree")
        assert resp.status_code == 401

    async def test_tree_employee_forbidden(self, employee_client: AsyncClient):
        resp = await employee_client.get("/api/v1/ticket-categories/tree")
        assert resp.status_code == 403

    async def test_tree_agent_ok(self, agent_client: AsyncClient):
        with patch("app.api.v1.ticket_categories.TicketCategoryService") as cls:
            inst = cls.return_value
            inst.tree = AsyncMock(return_value={"categories": []})
            resp = await agent_client.get("/api/v1/ticket-categories/tree")
        assert resp.status_code == 200
        assert resp.json() == {"categories": []}

    async def test_create_agent_forbidden(self, agent_client: AsyncClient):
        resp = await agent_client.post(
            "/api/v1/ticket-categories",
            json={"name": "Incident", "level": 1},
        )
        assert resp.status_code == 403

    async def test_create_admin_ok(self, admin_client: AsyncClient):
        cat = MagicMock()
        cat.id = "00000000-0000-0000-0000-000000000001"
        cat.name = "Incident"
        cat.level = 1
        cat.parent_id = None
        cat.is_active = True
        cat.sort_order = 0
        with patch("app.api.v1.ticket_categories.TicketCategoryService") as cls:
            cls.return_value.create = AsyncMock(return_value=cat)
            resp = await admin_client.post(
                "/api/v1/ticket-categories",
                json={"name": "Incident", "level": 1},
            )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Incident"
```

If `admin_client` fixture does not exist, use the existing pattern from `tests/api/conftest.py` (create one mirroring `agent_client` with `it_admin`).

- [ ] **Step 5: Run tests**

Run: `cd backend && uv run pytest tests/api/test_ticket_categories_api.py -v`  
Expected: PASS (or fix fixture name to match conftest).

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/__init__.py backend/app/api/v1/router.py \
  backend/app/api/v1/ticket_categories.py backend/tests/api/test_ticket_categories_api.py \
  backend/alembic/versions/014_ticket_categories_and_close_fields.py \
  backend/app/services/ticket_category_service.py backend/app/models/ticket.py
git commit -m "feat(tickets): mount ticket-categories API and export TicketCategory"
```

---

### Task 2: Cascade validation + close_ticket + status bypass

**Files:**
- Create: `backend/app/services/ticket_category_validation.py`
- Modify: `backend/app/services/ticket_service.py`
- Test: `backend/tests/unit/test_ticket_close.py`

**Interfaces:**
- Produces:
  - `async def validate_category_cascade(db, category, subcategory, item) -> None`
  - `TicketService.close_ticket(...)`
  - `TicketService.update_ticket_properties(...)`
  - `update_status` raises `ValueError("Use POST /tickets/{id}/close")` when `new_status == "closed"`

- [ ] **Step 1: Write failing unit tests**

Create `backend/tests/unit/test_ticket_close.py`:

```python
"""Unit tests for IT-only close + status bypass."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ticket_service import TicketService


def _user(role: str = "it_agent") -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.full_name = "Agent"
    u.email = f"{role}@test.com"
    u.role_names = [role]
    return u


def _ticket(**kwargs) -> MagicMock:
    t = MagicMock()
    t.id = uuid.uuid4()
    t.status = kwargs.get("status", "in_progress")
    t.resolution_notes = None
    t.category = None
    t.subcategory = None
    t.item = None
    t.closed_at = None
    t.closed_by = None
    t.close_notes = None
    return t


@pytest.mark.asyncio
async def test_update_status_rejects_closed():
    db = AsyncMock()
    svc = TicketService(db)
    ticket = _ticket()
    with patch.object(svc, "_get_ticket", AsyncMock(return_value=ticket)):
        with pytest.raises(ValueError, match="close"):
            await svc.update_status(ticket.id, "closed", _user())


@pytest.mark.asyncio
async def test_close_requires_resolution_notes():
    db = AsyncMock()
    svc = TicketService(db)
    ticket = _ticket()
    with patch.object(svc, "_get_ticket", AsyncMock(return_value=ticket)):
        with pytest.raises(ValueError, match="resolution"):
            await svc.close_ticket(
                ticket.id,
                _user(),
                resolution_notes="  ",
                category="Incident",
                subcategory="Network Connectivity",
                item="VPN",
            )


@pytest.mark.asyncio
async def test_close_employee_forbidden():
    db = AsyncMock()
    svc = TicketService(db)
    ticket = _ticket()
    with patch.object(svc, "_get_ticket", AsyncMock(return_value=ticket)):
        with pytest.raises(PermissionError):
            await svc.close_ticket(
                ticket.id,
                _user("employee"),
                resolution_notes="Fixed VPN",
                category="Incident",
                subcategory="Network Connectivity",
                item="VPN",
            )


@pytest.mark.asyncio
async def test_close_happy_path_sets_fields():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    svc = TicketService(db)
    ticket = _ticket()
    actor = _user()
    with (
        patch.object(svc, "_get_ticket", AsyncMock(return_value=ticket)),
        patch.object(svc, "_add_event", AsyncMock()),
        patch(
            "app.services.ticket_service.validate_category_cascade",
            AsyncMock(),
        ),
    ):
        result = await svc.close_ticket(
            ticket.id,
            actor,
            resolution_notes="Reset MFA and confirmed login.",
            category="Incident",
            subcategory="System Login Issue",
            item="Account Locked",
        )
    assert result.status == "closed"
    assert result.closed_by == actor.id
    assert result.category == "Incident"
    assert result.subcategory == "System Login Issue"
    assert result.item == "Account Locked"
    assert result.resolution_notes == "Reset MFA and confirmed login."
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `cd backend && uv run pytest tests/unit/test_ticket_close.py -v`  
Expected: FAIL (`close_ticket` missing / status still accepts closed).

- [ ] **Step 3: Implement cascade validator**

Create `backend/app/services/ticket_category_validation.py`:

```python
"""Validate Category → Sub-Category → Item names against the active tree."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import TicketCategory


class CategoryCascadeError(ValueError):
    """Invalid or incomplete category cascade."""


async def validate_category_cascade(
    db: AsyncSession,
    category: str,
    subcategory: str,
    item: str,
) -> tuple[TicketCategory, TicketCategory, TicketCategory]:
    """Require active L1/L2/L3 nodes with correct parent links.

    Raises CategoryCascadeError with a clear message when:
    - any name is blank
    - any node missing/inactive
    - parent chain is wrong
    - L2 has zero active L3 children (Item always required — close blocked)
    """
    cat_name = (category or "").strip()
    sub_name = (subcategory or "").strip()
    item_name = (item or "").strip()
    if not cat_name or not sub_name or not item_name:
        raise CategoryCascadeError(
            "Category, Sub-Category, and Item are all required"
        )

    l1 = await _find_active(db, level=1, name=cat_name, parent_id=None)
    if not l1:
        raise CategoryCascadeError("Invalid category cascade")

    l2 = await _find_active(db, level=2, name=sub_name, parent_id=l1.id)
    if not l2:
        raise CategoryCascadeError("Invalid category cascade")

    # Item always required: if this L2 has no active children, block close
    children = (
        await db.execute(
            select(TicketCategory).where(
                TicketCategory.parent_id == l2.id,
                TicketCategory.is_active.is_(True),
            )
        )
    ).scalars().all()
    if not children:
        raise CategoryCascadeError(
            "No items configured for this sub-category; ask an IT admin to add items"
        )

    l3 = await _find_active(db, level=3, name=item_name, parent_id=l2.id)
    if not l3:
        raise CategoryCascadeError("Invalid category cascade")

    return l1, l2, l3


async def _find_active(
    db: AsyncSession,
    *,
    level: int,
    name: str,
    parent_id: uuid.UUID | None,
) -> TicketCategory | None:
    stmt = select(TicketCategory).where(
        TicketCategory.level == level,
        TicketCategory.name == name,
        TicketCategory.is_active.is_(True),
    )
    if parent_id is None:
        stmt = stmt.where(TicketCategory.parent_id.is_(None))
    else:
        stmt = stmt.where(TicketCategory.parent_id == parent_id)
    return (await db.execute(stmt)).scalar_one_or_none()
```

- [ ] **Step 4: Implement service methods**

In `backend/app/services/ticket_service.py`:

1. Import:

```python
from app.services.ticket_category_validation import (
    CategoryCascadeError,
    validate_category_cascade,
)
```

2. At the start of `update_status`, after loading the ticket:

```python
if new_status == "closed":
    raise ValueError("Use POST /tickets/{id}/close")
```

Remove the `elif new_status == "closed": ticket.closed_at = now` branch (close_ticket owns that).

3. Add:

```python
_STAFF = frozenset({"it_agent", "it_lead", "it_admin"})

async def close_ticket(
    self,
    ticket_id: uuid.UUID,
    actor: User,
    *,
    resolution_notes: str,
    category: str,
    subcategory: str,
    item: str,
    close_notes: str | None = None,
) -> Ticket:
    """Close a ticket — IT staff only; mandatory notes + full category cascade."""
    roles = set(getattr(actor, "role_names", None) or [])
    if not roles & self._STAFF:
        raise PermissionError("Only IT staff can close tickets")

    ticket = await self._get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket not found")
    if ticket.status == "closed":
        raise ValueError("Ticket is already closed")

    notes = (resolution_notes or "").strip()
    if not notes:
        raise ValueError("resolution_notes is required")

    try:
        await validate_category_cascade(self.db, category, subcategory, item)
    except CategoryCascadeError:
        raise

    old_status = ticket.status
    now = datetime.now(UTC)
    ticket.status = "closed"
    ticket.closed_at = now
    ticket.closed_by = actor.id
    ticket.resolution_notes = notes
    ticket.close_notes = (close_notes or "").strip() or None
    ticket.category = category.strip()
    ticket.subcategory = subcategory.strip()
    ticket.item = item.strip()
    if not ticket.resolved_at:
        ticket.resolved_at = now

    await self._add_event(
        ticket_id,
        actor.id,
        "status_changed",
        f"Status changed from {old_status} to closed",
        old_value=old_status,
        new_value="closed",
    )
    return ticket

async def update_ticket_properties(
    self,
    ticket_id: uuid.UUID,
    actor: User,
    *,
    priority: str | None = None,
    urgency: str | None = None,
    impact: str | None = None,
    ticket_type: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    item: str | None = None,
    status: str | None = None,
    resolution_notes: str | None = None,
) -> Ticket:
    """Partial property update for IT staff. Cannot set status=closed."""
    roles = set(getattr(actor, "role_names", None) or [])
    if not roles & self._STAFF:
        raise PermissionError("Only IT staff can update ticket properties")

    ticket = await self._get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket not found")

    if status == "closed":
        raise ValueError("Use POST /tickets/{id}/close")

    if status is not None:
        if status not in (
            "new",
            "triaged",
            "in_progress",
            "waiting_for_user",
            "escalated",
            "resolved",
        ):
            raise ValueError(f"Invalid status '{status}'")
        old = ticket.status
        ticket.status = status
        if status == "resolved" and not ticket.resolved_at:
            ticket.resolved_at = datetime.now(UTC)
        await self._add_event(
            ticket_id,
            actor.id,
            "status_changed",
            f"Status changed from {old} to {status}",
            old_value=old,
            new_value=status,
        )

    if priority is not None:
        ticket.priority = priority
    if urgency is not None:
        ticket.urgency = urgency
    if impact is not None:
        ticket.impact = impact
    if ticket_type is not None:
        ticket.ticket_type = ticket_type
    if resolution_notes is not None:
        ticket.resolution_notes = resolution_notes

    # Classification: if any of the three provided, require full valid cascade
    if category is not None or subcategory is not None or item is not None:
        cat = category if category is not None else ticket.category
        sub = subcategory if subcategory is not None else ticket.subcategory
        itm = item if item is not None else ticket.item
        await validate_category_cascade(self.db, cat or "", sub or "", itm or "")
        ticket.category = (cat or "").strip()
        ticket.subcategory = (sub or "").strip()
        ticket.item = (itm or "").strip()

    return ticket
```

Use `self._STAFF` as a class attribute (or module constant) — fix the reference accordingly (`TicketService._STAFF` or module-level `_STAFF_ROLES`).

- [ ] **Step 5: Run unit tests — expect PASS**

Run: `cd backend && uv run pytest tests/unit/test_ticket_close.py -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/ticket_category_validation.py \
  backend/app/services/ticket_service.py backend/tests/unit/test_ticket_close.py
git commit -m "feat(tickets): enforce close_ticket with mandatory category cascade"
```

---

### Task 3: Wire close + PATCH ticket API + response fields

**Files:**
- Modify: `backend/app/api/v1/tickets.py`
- Test: `backend/tests/api/test_ticket_close_api.py`

**Interfaces:**
- Produces: `POST /tickets/{id}/close`, `PATCH /tickets/{id}`
- Extends `TicketResponse` with `subcategory`, `item`, `ticket_type`, `urgency`, `impact`, `close_notes`, `closed_by`, `closed_at`, `resolved_at`

- [ ] **Step 1: Extend `TicketResponse` and `_ticket_to_response`**

Add fields to `TicketResponse` in `tickets.py`:

```python
subcategory: str | None = None
item: str | None = None
ticket_type: str | None = None
urgency: str | None = None
impact: str | None = None
close_notes: str | None = None
closed_by: str | None = None
closed_at: str | None = None
resolved_at: str | None = None
```

Map them in `_ticket_to_response`.

- [ ] **Step 2: Add close + patch endpoints**

```python
@router.post("/{ticket_id}/close")
async def close_ticket(
    ticket_id: str,
    data: TicketCloseRequest,
    agent_user: ITAgentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketResponse:
    """Close ticket with mandatory resolution form (IT staff only)."""
    service = TicketService(db)
    try:
        ticket = await service.close_ticket(
            uuid.UUID(ticket_id),
            agent_user,
            resolution_notes=data.resolution_notes,
            category=data.category or "",
            subcategory=data.subcategory or "",
            item=data.item or "",
            close_notes=data.close_notes,
        )
        await db.commit()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        msg = str(exc)
        code = 404 if msg == "Ticket not found" else 409 if "already closed" in msg else 400
        if "Use POST" in msg:
            code = 409
        raise HTTPException(status_code=code, detail=msg) from exc
    return _ticket_to_response(ticket)


@router.patch("/{ticket_id}")
async def patch_ticket(
    ticket_id: str,
    data: TicketUpdateRequest,
    agent_user: ITAgentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketResponse:
    """Partial property update (IT staff). Cannot close via this endpoint."""
    service = TicketService(db)
    try:
        ticket = await service.update_ticket_properties(
            uuid.UUID(ticket_id),
            agent_user,
            priority=data.priority,
            urgency=data.urgency,
            impact=data.impact,
            ticket_type=data.ticket_type,
            category=data.category,
            subcategory=data.subcategory,
            item=data.item,
            resolution_notes=data.resolution_notes,
            # status lives on TicketUpdateRequest — add the field if missing
            status=getattr(data, "status", None),
        )
        await db.commit()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        msg = str(exc)
        code = 404 if msg == "Ticket not found" else 409 if "Use POST" in msg else 400
        raise HTTPException(status_code=code, detail=msg) from exc
    return _ticket_to_response(ticket)
```

Also update `TicketCloseRequest` so `category` / `subcategory` / `item` are **required** `str` (not optional):

```python
class TicketCloseRequest(BaseModel):
    resolution_notes: str
    category: str
    subcategory: str
    item: str
    close_notes: str | None = None
```

Add `status: str | None = None` to `TicketUpdateRequest`.

In `update_ticket_status` endpoint, catch the closed bypass:

```python
try:
    ticket = await service.update_status(...)
    await db.commit()
except ValueError as exc:
    if "Use POST" in str(exc):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc
```

(Confirm whether `update_status` currently commits — match existing pattern in the file.)

- [ ] **Step 3: API tests**

Create `backend/tests/api/test_ticket_close_api.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

TID = "00000000-0000-0000-0000-000000000123"


def _closed_ticket():
    t = MagicMock()
    t.id = TID
    t.ticket_number = "ITA-0001"
    t.title = "VPN"
    t.description = "down"
    t.status = "closed"
    t.priority = "medium"
    t.category = "Incident"
    t.subcategory = "Network Connectivity"
    t.item = "VPN"
    t.ticket_type = None
    t.source = "chat"
    t.urgency = None
    t.impact = None
    t.requester_id = "00000000-0000-0000-0000-000000000099"
    t.assigned_to = None
    t.created_at = MagicMock()
    t.created_at.isoformat.return_value = "2026-07-27T00:00:00+00:00"
    t.sla_response_target = None
    t.sla_resolution_target = None
    t.ai_summary = None
    t.resolution_notes = "Fixed"
    t.close_notes = None
    t.closed_by = "00000000-0000-0000-0000-000000000001"
    t.closed_at = MagicMock()
    t.closed_at.isoformat.return_value = "2026-07-27T01:00:00+00:00"
    t.resolved_at = t.closed_at
    return t


class TestCloseApi:
    async def test_employee_forbidden(self, employee_client: AsyncClient):
        resp = await employee_client.post(
            f"/api/v1/tickets/{TID}/close",
            json={
                "resolution_notes": "done",
                "category": "Incident",
                "subcategory": "Network Connectivity",
                "item": "VPN",
            },
        )
        assert resp.status_code == 403

    async def test_status_closed_rejected(self, agent_client: AsyncClient):
        with patch("app.api.v1.tickets.TicketService") as cls:
            cls.return_value.update_status = AsyncMock(
                side_effect=ValueError("Use POST /tickets/{id}/close")
            )
            resp = await agent_client.post(
                f"/api/v1/tickets/{TID}/status",
                json={"status": "closed"},
            )
        assert resp.status_code == 409

    async def test_close_ok(self, agent_client: AsyncClient):
        with patch("app.api.v1.tickets.TicketService") as cls:
            cls.return_value.close_ticket = AsyncMock(return_value=_closed_ticket())
            resp = await agent_client.post(
                f"/api/v1/tickets/{TID}/close",
                json={
                    "resolution_notes": "Fixed VPN profile",
                    "category": "Incident",
                    "subcategory": "Network Connectivity",
                    "item": "VPN",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "closed"
```

- [ ] **Step 4: Run tests**

Run: `cd backend && uv run pytest tests/api/test_ticket_close_api.py tests/unit/test_ticket_close.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/tickets.py backend/tests/api/test_ticket_close_api.py
git commit -m "feat(tickets): add close and properties PATCH endpoints"
```

---

### Task 4: Seed starter category tree

**Files:**
- Modify: `backend/scripts/seed_enterprise.py`
- Optional create: `backend/scripts/seed_ticket_categories.py` (called from seed_enterprise)

**Interfaces:**
- Produces: idempotent seed of L1/L2/L3 per spec §3.6

- [ ] **Step 1: Add seed helper**

Add to `seed_enterprise.py` (or a dedicated module imported by it):

```python
from app.models.ticket import TicketCategory
from app.services.ticket_category_service import TicketCategoryService

STARTER_TREE: dict[str, dict[str, list[str]]] = {
    "Incident": {
        "System Login Issue": ["Password Reset", "Account Locked"],
        "Network Connectivity": ["VPN", "Wi-Fi", "DNS"],
        "O365 Apps": ["Outlook", "Teams", "OneDrive"],
        "Laptop Not Booting": ["Hardware Diagnosis"],
        "Zoom Issue": ["Audio", "Video", "Sign-in"],
        "Laptop Performance Issue": ["Slow Performance"],
    },
    "Service Requests": {
        "DL Creation": ["New Distribution List"],
        "Application Access": ["Slack", "Webex", "Zoom"],
        "New Joiner Credential Creation": ["Standard Onboarding"],
        "Shared Mailbox Access": ["Grant Access"],
        "Hardware Request": ["Laptop", "Monitor", "Headset"],
        "License Request": ["Software License"],
    },
    "SPAM Email": {"General": ["Reported Spam"]},
    "Others": {"General": ["Uncategorized"]},
    "Freshworks": {"General": ["Freshworks Request"]},
}


async def seed_ticket_categories(db: AsyncSession) -> None:
    svc = TicketCategoryService(db)
    existing = await svc.list_all(active_only=False)
    if existing:
        return  # idempotent: skip if any categories exist
    for l1_name, subs in STARTER_TREE.items():
        l1 = await svc.create(name=l1_name, level=1)
        for l2_name, items in subs.items():
            l2 = await svc.create(name=l2_name, level=2, parent_id=l1.id)
            for item_name in items:
                await svc.create(name=item_name, level=3, parent_id=l2.id)
```

Call `await seed_ticket_categories(session)` from the main seed flow before commit.

- [ ] **Step 2: Manual verify (optional if DB up)**

Run: `cd backend && uv run python -m scripts.seed_enterprise`  
Then: `GET /api/v1/ticket-categories/tree` as agent → non-empty Incident/Service Requests.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/seed_enterprise.py
git commit -m "feat(tickets): seed starter Category → Sub-Category → Item tree"
```

---

### Task 5: Frontend API client

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Extend ticket types + methods**

Add to `TicketListItem` (and any detail type used by the workspace):

```typescript
subcategory?: string | null;
item?: string | null;
ticket_type?: string | null;
urgency?: string | null;
impact?: string | null;
close_notes?: string | null;
closed_by?: string | null;
closed_at?: string | null;
resolved_at?: string | null;
```

Add to `ticketsApi`:

```typescript
close: (
  id: string,
  body: {
    resolution_notes: string;
    category: string;
    subcategory: string;
    item: string;
    close_notes?: string;
  },
) =>
  apiRequest<TicketListItem>(`/tickets/${id}/close`, {
    method: "POST",
    body,
  }),

update: (
  id: string,
  body: {
    priority?: string;
    urgency?: string | null;
    impact?: string | null;
    ticket_type?: string | null;
    category?: string | null;
    subcategory?: string | null;
    item?: string | null;
    status?: string;
    resolution_notes?: string | null;
  },
) =>
  apiRequest<TicketListItem>(`/tickets/${id}`, {
    method: "PATCH",
    body,
  }),
```

- [ ] **Step 2: Add `ticketCategoriesApi`**

```typescript
export interface TicketCategoryNode {
  id: string;
  name: string;
  level: number;
  parent_id: string | null;
  is_active: boolean;
  sort_order: number;
  children?: TicketCategoryNode[];
}

export const ticketCategoriesApi = {
  tree: () =>
    apiRequest<{ categories: TicketCategoryNode[] }>("/ticket-categories/tree"),
  list: (params?: { level?: number; parent_id?: string; active_only?: boolean }) =>
    apiRequest<TicketCategoryNode[]>("/ticket-categories", { query: params }),
  create: (body: {
    name: string;
    level: number;
    parent_id?: string | null;
    sort_order?: number;
  }) =>
    apiRequest<TicketCategoryNode>("/ticket-categories", {
      method: "POST",
      body,
    }),
  update: (
    id: string,
    body: { name?: string; is_active?: boolean; sort_order?: number },
  ) =>
    apiRequest<TicketCategoryNode>(`/ticket-categories/${id}`, {
      method: "PATCH",
      body,
    }),
  remove: (id: string) =>
    apiRequest<void>(`/ticket-categories/${id}`, { method: "DELETE" }),
  reorder: (ordered_ids: string[]) =>
    apiRequest<void>("/ticket-categories/reorder", {
      method: "POST",
      body: { ordered_ids },
    }),
};
```

Adapt `query`/`body` to match existing `apiRequest` signature in this file.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(frontend): ticket close/update and category API clients"
```

---

### Task 6: Cascade fields + Close modal

**Files:**
- Create: `frontend/src/features/tickets/CategoryCascadeFields.tsx`
- Create: `frontend/src/features/tickets/CloseTicketModal.tsx`
- Create: `frontend/src/features/tickets/CloseTicketModal.test.tsx`

- [ ] **Step 1: `CategoryCascadeFields`**

Shared controlled cascade (loads active tree once via `ticketCategoriesApi.tree`):

```tsx
// Props: category, subcategory, item, onChange({category, subcategory, item}), disabled?
// On L1 change → clear L2+Item; on L2 change → clear Item
// Options: L1 = roots; L2 = selected L1.children; L3 = selected L2.children
// Labels: Category *, Sub-Category *, Item *
// If L2 selected and children.length === 0, show helper text:
//   "No items configured — ask an IT admin to add items before closing."
```

Keep under 300 lines; use existing form/select styles from Operations pages.

- [ ] **Step 2: `CloseTicketModal`**

```tsx
// Props: ticketId, open, onClose, onClosed, initialCategory/Sub/Item?
// Fields: resolution_notes (required textarea), CategoryCascadeFields, optional close_notes
// Confirm disabled unless notes.trim() && category && subcategory && item
// Submit → ticketsApi.close → onClosed()
```

- [ ] **Step 3: Vitest**

`CloseTicketModal.test.tsx`:

- Renders required labels
- Confirm disabled when empty
- Changing category clears subcategory/item (mock tree with 2 levels)

- [ ] **Step 4: Run**

Run: `cd frontend && npm test -- --run src/features/tickets/CloseTicketModal.test.tsx`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/tickets/
git commit -m "feat(frontend): Close ticket modal with cascading category fields"
```

---

### Task 7: Properties panel + upgrade TicketWorkspacePage

**Files:**
- Create: `frontend/src/features/tickets/TicketPropertiesPanel.tsx`
- Modify: `frontend/src/pages/operations/TicketWorkspacePage.tsx`
- Modify: `frontend/src/pages/operations/TicketWorkspacePage.test.tsx`

- [ ] **Step 1: Build `TicketPropertiesPanel`**

Right-rail form bound to ticket fields:

- Priority, Status (options **without** `closed`), Type, Urgency, Impact (editable)
- Source, Agent (read-only)
- `CategoryCascadeFields`
- Resolution notes textarea
- **Update** → `ticketsApi.update`

- [ ] **Step 2: Restructure workspace layout**

Two-column layout:

- Left: existing description / comments / handoff / timeline
- Right: `TicketPropertiesPanel`
- Header: add **Close** button (IT staff, hidden when `status === 'closed'`) opening `CloseTicketModal`
- Remove `closed` from any existing status dropdown / quick-status control that still offers it

- [ ] **Step 3: Update tests**

Extend `TicketWorkspacePage.test.tsx`:

- Close button present for `in_progress`
- Close button absent for `closed`
- Status control does not list `closed` (query by role/label)

- [ ] **Step 4: Run frontend checks**

Run:

```bash
cd frontend && npx tsc --noEmit && npm run lint && npm test -- --run src/pages/operations/TicketWorkspacePage.test.tsx src/features/tickets/
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/tickets/TicketPropertiesPanel.tsx \
  frontend/src/pages/operations/TicketWorkspacePage.tsx \
  frontend/src/pages/operations/TicketWorkspacePage.test.tsx
git commit -m "feat(frontend): ticket Properties panel and Close action on workspace"
```

---

### Task 8: Admin Manage Category page

**Files:**
- Create: `frontend/src/pages/admin/TicketCategoriesPage.tsx`
- Modify: `frontend/src/components/RouteGuard.tsx`
- Modify: `frontend/src/components/layouts/AdminLayout.tsx`
- Modify: `frontend/src/app/App.tsx`

- [ ] **Step 1: Add `ITAdminRoute`**

In `RouteGuard.tsx`:

```tsx
export function ITAdminRoute({ children }: { children: React.ReactNode }) {
  return (
    <RouteGuard allowedRoles={['it_admin']}>
      {children}
    </RouteGuard>
  );
}
```

- [ ] **Step 2: Build `TicketCategoriesPage`**

Admin page with:

1. Tree list (L1 → L2 → L3): add child, rename, activate/deactivate, delete leaf
2. Cascading preview (three dependent selects) labeled “Dropdown Choices – Preview”
3. Breadcrumbs + `PageHeader` titled “Manage Category”
4. Errors from 409 delete-with-children surfaced inline

Keep file focused; extract small helpers if >300 lines.

- [ ] **Step 3: Wire nav + route**

`AdminLayout.tsx` NAV item (it_admin only):

```tsx
{
  to: '/dashboard/ticket-categories',
  label: 'Ticket Categories',
  icon: Tags, // or FolderTree from lucide-react
  can: (u) => isAdmin(u),
},
```

`App.tsx` under `/dashboard`:

```tsx
<Route
  path="ticket-categories"
  element={
    <ITAdminRoute>
      <TicketCategoriesPage />
    </ITAdminRoute>
  }
/>
```

(If nested under existing `AdminRoute`, wrap with `ITAdminRoute` so leads cannot open it.)

- [ ] **Step 4: Lint/typecheck**

Run: `cd frontend && npx tsc --noEmit && npm run lint`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/admin/TicketCategoriesPage.tsx \
  frontend/src/components/RouteGuard.tsx \
  frontend/src/components/layouts/AdminLayout.tsx \
  frontend/src/app/App.tsx
git commit -m "feat(admin): Manage Category page for ticket hierarchy"
```

---

### Task 9: Domain model doc + final verification

**Files:**
- Modify: `memory/domain-model.md`

- [ ] **Step 1: Update domain model**

Under Support core, document:

- `TicketCategory` 3-level hierarchy; admin-managed; FK RESTRICT
- Close invariants: IT-only; mandatory notes + L1/L2/L3; status bypass forbidden
- New ticket fields: `item`, `ticket_type`, `close_notes`, `closed_by`

- [ ] **Step 2: Full verification**

```bash
cd backend && uv run ruff check app tests && uv run pytest \
  tests/unit/test_ticket_close.py \
  tests/unit/test_ticket_category_service.py \
  tests/api/test_ticket_close_api.py \
  tests/api/test_ticket_categories_api.py -v

cd frontend && npx tsc --noEmit && npm run lint && npm test -- --run src/features/tickets/ src/pages/operations/TicketWorkspacePage.test.tsx
```

Expected: all PASS. If `test_ticket_category_service.py` was not created in Task 1, add a minimal unit file covering create parent-level validation + delete-with-children (or fold those asserts into the API tests and skip the missing file).

- [ ] **Step 3: Commit**

```bash
git add memory/domain-model.md
git commit -m "docs: record ticket close and category hierarchy invariants"
```

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| Close modal with mandatory notes + L1/L2/L3 | 6, 7 |
| Item always required / empty L2 blocks close | 2, 6 |
| IT staff can close; employees cannot | 2, 3 |
| Status update cannot set closed | 2, 3, 7 |
| Properties panel on workspace | 7 |
| Manage Category admin-only | 1, 8 |
| Cascading carefully (clear children; server validate) | 2, 6 |
| Starter seed with ≥1 Item per L2 | 4 |
| Mount WIP category API / finish close schemas | 1, 3 |
| Domain model update | 9 |

No TBD/placeholder steps. Type names consistent: `validate_category_cascade`, `close_ticket`, `ticketCategoriesApi`, `CloseTicketModal`, `TicketPropertiesPanel`.
