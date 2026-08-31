"""Asset management service — lifecycle enforcement and business rules."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

from app.models.asset import (
    ASSET_TERMINAL_STATUSES,
    Asset,
    AssetEvent,
    AssetEventType,
    AssetStatus,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.asset import AssetAssignRequest, AssetCreate, AssetRetireRequest, AssetUpdate


class AssetError(Exception):
    """Raised when a business rule prevents an asset operation."""


class AssetService:
    """Service layer for Asset management — no direct DB queries."""

    def __init__(self, db: AsyncSession) -> None:
        from app.repositories.asset_repository import AssetRepository

        self._db = db
        self._repo = AssetRepository(db)

    async def create(self, data: AssetCreate, actor_id: uuid.UUID) -> Asset:
        if await self._repo.is_tag_taken(data.asset_tag):
            raise AssetError(f"Asset tag '{data.asset_tag}' is already in use")
        asset = Asset(
            id=uuid.uuid4(),
            asset_tag=data.asset_tag,
            name=data.name,
            asset_type=data.asset_type,
            impact=data.impact,
            description=data.description,
            hardware_type=data.hardware_type,
            usage_type=data.usage_type,
            condition=data.condition,
            status=AssetStatus.IN_STOCK,
            physical_subtype=data.physical_subtype,
            virtual_subtype=data.virtual_subtype,
            product=data.product,
            model=data.model,
            vendor=data.vendor,
            serial_number=data.serial_number,
            classification=data.classification,
            cost=data.cost,
            currency=data.currency,
            warranty_info=data.warranty_info,
            acquisition_date=data.acquisition_date,
            warranty_expiry=data.warranty_expiry,
            invoice_number=data.invoice_number,
            po_number=data.po_number,
            contract=data.contract,
            ip_address=data.ip_address,
            mac_address=data.mac_address,
            location=data.location,
            department=data.department,
            managed_by_group=data.managed_by_group,
            source=data.source,
            end_of_life=data.end_of_life,
            parent_asset_id=data.parent_asset_id,
        )
        await self._repo.create(asset)
        await self._repo.append_event(
            AssetEvent(
                id=uuid.uuid4(),
                asset_id=asset.id,
                actor_id=actor_id,
                event_type=AssetEventType.CREATED,
                to_status=AssetStatus.IN_STOCK,
                detail=f"Asset {data.asset_tag} created",
            )
        )
        await self._db.commit()
        return asset

    async def get(self, asset_id: uuid.UUID) -> Asset:
        asset = await self._repo.get(asset_id)
        if asset is None:
            raise AssetError(f"Asset {asset_id} not found")
        return asset

    async def list(
        self,
        *,
        status: AssetStatus | None = None,
        assigned_to_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Asset], int]:
        return await self._repo.find_all(
            status=status, assigned_to_id=assigned_to_id, limit=limit, offset=offset
        )

    async def update(self, asset_id: uuid.UUID, data: AssetUpdate, actor_id: uuid.UUID) -> Asset:
        asset = await self.get(asset_id)
        if asset.status in ASSET_TERMINAL_STATUSES:
            raise AssetError(f"Cannot update a {asset.status} asset")
        patch: dict[str, Any] = data.model_dump(exclude_unset=True)
        if "asset_tag" in patch:
            new_tag = patch["asset_tag"]
            if await self._repo.is_tag_taken(new_tag, exclude_id=asset_id):
                raise AssetError(f"Asset tag '{new_tag}' is already in use")
        for field, value in patch.items():
            setattr(asset, field, value)
        await self._repo.update(asset)
        await self._repo.append_event(
            AssetEvent(
                id=uuid.uuid4(),
                asset_id=asset_id,
                actor_id=actor_id,
                event_type=AssetEventType.FIELD_UPDATED,
                detail=f"Fields updated: {', '.join(patch.keys())}",
            )
        )
        await self._db.commit()
        return asset

    async def assign(
        self, asset_id: uuid.UUID, req: AssetAssignRequest, actor_id: uuid.UUID
    ) -> Asset:
        asset = await self.get(asset_id)
        if asset.status in ASSET_TERMINAL_STATUSES:
            raise AssetError(f"Cannot assign a {asset.status} asset; return to stock first")
        old_status = asset.status
        asset.assigned_to_id = req.assigned_to_id
        asset.assigned_date = req.assigned_date or date.today()
        asset.status = AssetStatus.ASSIGNED
        await self._repo.update(asset)
        await self._repo.append_event(
            AssetEvent(
                id=uuid.uuid4(),
                asset_id=asset_id,
                actor_id=actor_id,
                event_type=AssetEventType.ASSIGNED,
                from_status=old_status,
                to_status=AssetStatus.ASSIGNED,
                detail=f"Assigned to user {req.assigned_to_id}",
            )
        )
        await self._db.commit()
        return asset

    async def retire(
        self, asset_id: uuid.UUID, req: AssetRetireRequest, actor_id: uuid.UUID
    ) -> Asset:
        asset = await self.get(asset_id)
        if req.status not in ASSET_TERMINAL_STATUSES:
            raise AssetError(
                f"Status {req.status!r} is not terminal; "
                "use assign() for assignment changes"
            )
        if not req.retirement_reason.strip():
            raise AssetError("Retirement reason is required")
        old_status = asset.status
        asset.status = req.status
        asset.retirement_reason = req.retirement_reason
        asset.retirement_date = req.retirement_date
        asset.assigned_to_id = None
        await self._repo.update(asset)
        await self._repo.append_event(
            AssetEvent(
                id=uuid.uuid4(),
                asset_id=asset_id,
                actor_id=actor_id,
                event_type=AssetEventType.RETIRED,
                from_status=old_status,
                to_status=req.status,
                detail=req.retirement_reason,
            )
        )
        await self._db.commit()
        return asset

    async def transfer(
        self, asset_id: uuid.UUID, new_assigned_to_id: uuid.UUID, actor_id: uuid.UUID
    ) -> Asset:
        asset = await self.get(asset_id)
        if asset.status in ASSET_TERMINAL_STATUSES:
            raise AssetError(f"Cannot transfer a {asset.status} asset")
        old_assignee = str(asset.assigned_to_id) if asset.assigned_to_id else "unassigned"
        asset.assigned_to_id = new_assigned_to_id
        asset.assigned_date = date.today()
        await self._repo.update(asset)
        await self._repo.append_event(
            AssetEvent(
                id=uuid.uuid4(),
                asset_id=asset_id,
                actor_id=actor_id,
                event_type=AssetEventType.TRANSFERRED,
                detail=f"Transferred from {old_assignee} to {new_assigned_to_id}",
            )
        )
        await self._db.commit()
        return asset

    async def delete(self, asset_id: uuid.UUID) -> None:
        asset = await self.get(asset_id)
        if asset.status not in (AssetStatus.IN_STOCK, *ASSET_TERMINAL_STATUSES):
            raise AssetError("Only in-stock, retired, or disposed assets may be deleted")
        await self._repo.delete(asset)
        await self._db.commit()


__all__ = ["AssetError", "AssetService"]
