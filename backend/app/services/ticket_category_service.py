"""Ticket category service — admin-managed 3-level hierarchy.

Hierarchy: Level-1 (Category) → Level-2 (Sub-Category) → Level-3 (Item).
Admins manage the vocabulary; IT staff read it when working tickets.

Rules
-----
* A parent cannot be deleted while it has active children (FK RESTRICT +
  service-layer guard with a clear error message).
* Deactivating a parent implicitly hides its children in list endpoints
  (filter ``is_active=True`` at all levels).
* Sort order is user-controlled (drag-and-drop in the UI sends a batch
  sort update via ``reorder``).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

from app.models.ticket import TicketCategory

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class TicketCategoryError(ValueError):
    """Raised on invalid category operations."""


class TicketCategoryService:
    """CRUD for the ticket category hierarchy."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Read ───────────────────────────────────────────────────────────────

    async def list_all(self, *, active_only: bool = True) -> list[TicketCategory]:
        """Return all categories ordered by level then sort_order then name."""
        stmt = select(TicketCategory).order_by(
            TicketCategory.level, TicketCategory.sort_order, TicketCategory.name
        )
        if active_only:
            stmt = stmt.where(TicketCategory.is_active.is_(True))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_level(
        self, level: int, *, parent_id: uuid.UUID | None = None, active_only: bool = True
    ) -> list[TicketCategory]:
        """Return categories at a specific level, optionally filtered by parent."""
        stmt = (
            select(TicketCategory)
            .where(TicketCategory.level == level)
            .order_by(TicketCategory.sort_order, TicketCategory.name)
        )
        if active_only:
            stmt = stmt.where(TicketCategory.is_active.is_(True))
        if parent_id is not None:
            stmt = stmt.where(TicketCategory.parent_id == parent_id)
        elif level > 1:
            stmt = stmt.where(TicketCategory.parent_id.is_(None))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get(self, category_id: uuid.UUID) -> TicketCategory | None:
        return await self.db.get(TicketCategory, category_id)

    async def tree(self) -> dict:
        """Return the full hierarchy as a nested dict for the manager UI.

        Shape: ``{id, name, level, is_active, sort_order, children: [...]}``.
        """
        all_cats = await self.list_all(active_only=False)
        by_id: dict[uuid.UUID, dict] = {}
        roots: list[dict] = []

        for cat in all_cats:
            node: dict = {
                "id": str(cat.id),
                "name": cat.name,
                "level": cat.level,
                "is_active": cat.is_active,
                "sort_order": cat.sort_order,
                "parent_id": str(cat.parent_id) if cat.parent_id else None,
                "children": [],
            }
            by_id[cat.id] = node

        for cat in all_cats:
            node = by_id[cat.id]
            if cat.parent_id and cat.parent_id in by_id:
                by_id[cat.parent_id]["children"].append(node)
            else:
                roots.append(node)

        return {"categories": roots}

    # ── Write ──────────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        name: str,
        level: int,
        parent_id: uuid.UUID | None = None,
        sort_order: int = 0,
    ) -> TicketCategory:
        """Create a category node at the given level.

        Validates:
        * level ∈ {1, 2, 3}
        * parent_id required for level > 1
        * parent must exist and be exactly one level above
        * no duplicate name within the same parent/level scope
        """
        if level not in (1, 2, 3):
            raise TicketCategoryError("Level must be 1, 2, or 3")
        if level > 1 and parent_id is None:
            raise TicketCategoryError(f"Level-{level} categories require a parent_id")
        if level == 1 and parent_id is not None:
            raise TicketCategoryError("Top-level categories (level 1) cannot have a parent")

        if parent_id:
            parent = await self.db.get(TicketCategory, parent_id)
            if not parent:
                raise TicketCategoryError("Parent category not found")
            if parent.level != level - 1:
                raise TicketCategoryError(
                    f"Parent is level-{parent.level}; a level-{level} child requires "
                    f"a level-{level - 1} parent"
                )

        # Duplicate name check within scope
        stmt = select(TicketCategory).where(
            TicketCategory.level == level,
            TicketCategory.name == name,
            TicketCategory.parent_id == parent_id,
        )
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing:
            raise TicketCategoryError(f"A category named '{name}' already exists at this level")

        cat = TicketCategory(
            name=name,
            level=level,
            parent_id=parent_id,
            sort_order=sort_order,
            is_active=True,
        )
        self.db.add(cat)
        await self.db.flush()
        logger.info(
            "ticket_category_created",
            id=str(cat.id),
            name=name,
            level=level,
            parent_id=str(parent_id) if parent_id else None,
        )
        return cat

    async def update(
        self,
        category_id: uuid.UUID,
        *,
        name: str | None = None,
        is_active: bool | None = None,
        sort_order: int | None = None,
    ) -> TicketCategory:
        """Update mutable fields on a category node."""
        cat = await self.db.get(TicketCategory, category_id)
        if not cat:
            raise TicketCategoryError("Category not found")

        if name is not None:
            cat.name = name
        if is_active is not None:
            cat.is_active = is_active
        if sort_order is not None:
            cat.sort_order = sort_order

        await self.db.flush()
        logger.info("ticket_category_updated", id=str(category_id))
        return cat

    async def delete(self, category_id: uuid.UUID) -> None:
        """Delete a leaf category node.

        Raises ``TicketCategoryError`` if the category has children (even
        inactive ones) to prevent orphaning sub-trees. Admin must delete
        children first.
        """
        cat = await self.db.get(TicketCategory, category_id)
        if not cat:
            raise TicketCategoryError("Category not found")

        # Check for children (any active/inactive)
        child_stmt = select(TicketCategory).where(TicketCategory.parent_id == category_id).limit(1)
        child = (await self.db.execute(child_stmt)).scalar_one_or_none()
        if child:
            raise TicketCategoryError(
                f"Cannot delete '{cat.name}' — it still has child categories. "
                "Remove all children first."
            )

        await self.db.delete(cat)
        await self.db.flush()
        logger.info("ticket_category_deleted", id=str(category_id), name=cat.name)

    async def reorder(self, ordered_ids: list[uuid.UUID]) -> None:
        """Batch update sort_order for a list of category IDs (position = index)."""
        for idx, cat_id in enumerate(ordered_ids):
            cat = await self.db.get(TicketCategory, cat_id)
            if cat:
                cat.sort_order = idx
        await self.db.flush()


__all__ = ["TicketCategoryService", "TicketCategoryError"]
