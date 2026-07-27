"""Unit tests for validate_category_cascade."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ticket_category_validation import (
    CategoryCascadeError,
    validate_category_cascade,
)


def _cat(level: int, name: str, parent_id: uuid.UUID | None = None) -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.level = level
    c.name = name
    c.parent_id = parent_id
    c.is_active = True
    return c


@pytest.mark.asyncio
async def test_blank_names_raises_category_cascade_error():
    db = AsyncMock()
    with pytest.raises(CategoryCascadeError, match="all required"):
        await validate_category_cascade(db, "", "Sub", "Item")
    with pytest.raises(CategoryCascadeError, match="all required"):
        await validate_category_cascade(db, "Cat", "  ", "Item")
    with pytest.raises(CategoryCascadeError, match="all required"):
        await validate_category_cascade(db, "Cat", "Sub", "")


@pytest.mark.asyncio
async def test_missing_l1_raises():
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)

    with pytest.raises(CategoryCascadeError, match="Invalid category cascade"):
        await validate_category_cascade(db, "Incident", "Network", "VPN")


@pytest.mark.asyncio
async def test_missing_l2_raises():
    l1 = _cat(1, "Incident")
    call_count = 0

    async def execute(_stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar_one_or_none.return_value = l1
        else:
            result.scalar_one_or_none.return_value = None
        return result

    db = AsyncMock()
    db.execute = execute

    with pytest.raises(CategoryCascadeError, match="Invalid category cascade"):
        await validate_category_cascade(db, "Incident", "Network", "VPN")


@pytest.mark.asyncio
async def test_l2_zero_active_children_raises():
    l1 = _cat(1, "Incident")
    l2 = _cat(2, "Network", parent_id=l1.id)
    call_count = 0

    async def execute(_stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar_one_or_none.return_value = l1
        elif call_count == 2:
            result.scalar_one_or_none.return_value = l2
        else:
            result.scalars.return_value.all.return_value = []
        return result

    db = AsyncMock()
    db.execute = execute

    with pytest.raises(CategoryCascadeError, match="No items configured"):
        await validate_category_cascade(db, "Incident", "Network", "VPN")


@pytest.mark.asyncio
async def test_missing_l3_raises():
    l1 = _cat(1, "Incident")
    l2 = _cat(2, "Network", parent_id=l1.id)
    call_count = 0

    async def execute(_stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar_one_or_none.return_value = l1
        elif call_count == 2:
            result.scalar_one_or_none.return_value = l2
        elif call_count == 3:
            result.scalars.return_value.all.return_value = [_cat(3, "Other")]
        else:
            result.scalar_one_or_none.return_value = None
        return result

    db = AsyncMock()
    db.execute = execute

    with pytest.raises(CategoryCascadeError, match="Invalid category cascade"):
        await validate_category_cascade(db, "Incident", "Network", "VPN")


@pytest.mark.asyncio
async def test_happy_path_returns_l1_l2_l3():
    l1 = _cat(1, "Incident")
    l2 = _cat(2, "Network", parent_id=l1.id)
    l3 = _cat(3, "VPN", parent_id=l2.id)
    call_count = 0

    async def execute(_stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar_one_or_none.return_value = l1
        elif call_count == 2:
            result.scalar_one_or_none.return_value = l2
        elif call_count == 3:
            result.scalars.return_value.all.return_value = [l3]
        else:
            result.scalar_one_or_none.return_value = l3
        return result

    db = AsyncMock()
    db.execute = execute

    out = await validate_category_cascade(db, "Incident", "Network", "VPN")
    assert out == (l1, l2, l3)
