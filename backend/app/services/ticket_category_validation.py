"""Validate Category → Sub-Category → Item names against the active tree."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.ticket import TicketCategory

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


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
