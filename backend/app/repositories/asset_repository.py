"""Repository for Asset management — all DB access goes through here."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.models.asset import Asset, AssetEvent, AssetStatus

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class AssetRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, asset: Asset) -> Asset:
        self._db.add(asset)
        await self._db.flush()
        return asset

    async def get(self, asset_id: uuid.UUID) -> Asset | None:
        result = await self._db.execute(select(Asset).where(Asset.id == asset_id))
        return result.scalar_one_or_none()

    async def get_by_tag(self, asset_tag: str) -> Asset | None:
        result = await self._db.execute(select(Asset).where(Asset.asset_tag == asset_tag))
        return result.scalar_one_or_none()

    async def is_tag_taken(self, asset_tag: str, exclude_id: uuid.UUID | None = None) -> bool:
        stmt = select(Asset.id).where(Asset.asset_tag == asset_tag)
        if exclude_id is not None:
            stmt = stmt.where(Asset.id != exclude_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def find_all(
        self,
        *,
        status: AssetStatus | None = None,
        assigned_to_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Asset], int]:
        stmt = select(Asset)
        if status is not None:
            stmt = stmt.where(Asset.status == status)
        if assigned_to_id is not None:
            stmt = stmt.where(Asset.assigned_to_id == assigned_to_id)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._db.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(Asset.created_at.desc()).limit(limit).offset(offset)
        rows = (await self._db.execute(stmt)).scalars().all()
        return list(rows), int(total)

    async def update(self, asset: Asset) -> Asset:
        asset.updated_at = datetime.now(UTC)
        self._db.add(asset)
        await self._db.flush()
        return asset

    async def delete(self, asset: Asset) -> None:
        await self._db.delete(asset)
        await self._db.flush()

    async def append_event(self, event: AssetEvent) -> AssetEvent:
        self._db.add(event)
        await self._db.flush()
        return event

    async def get_events(self, asset_id: uuid.UUID) -> list[AssetEvent]:
        result = await self._db.execute(
            select(AssetEvent)
            .where(AssetEvent.asset_id == asset_id)
            .order_by(AssetEvent.created_at.asc())
        )
        return list(result.scalars().all())


__all__ = ["AssetRepository"]
