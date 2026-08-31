"""Pydantic schemas for the Asset management domain."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.asset import AssetCondition, AssetHardwareType, AssetStatus, AssetUsageType


class AssetCreate(BaseModel):
    asset_tag: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    asset_type: str = ""
    impact: str = "low"
    description: str = ""
    hardware_type: AssetHardwareType = AssetHardwareType.PHYSICAL
    usage_type: AssetUsageType = AssetUsageType.PERMANENT
    condition: AssetCondition = AssetCondition.GOOD
    physical_subtype: str | None = None
    virtual_subtype: str | None = None
    product: str | None = None
    model: str | None = None
    vendor: str | None = None
    serial_number: str | None = None
    classification: str | None = None
    cost: float | None = None
    currency: str | None = None
    warranty_info: str | None = None
    acquisition_date: date | None = None
    warranty_expiry: date | None = None
    invoice_number: str | None = None
    po_number: str | None = None
    contract: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    location: str | None = None
    department: str | None = None
    managed_by_group: str | None = None
    source: str | None = None
    end_of_life: date | None = None
    parent_asset_id: uuid.UUID | None = None


class AssetUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    asset_type: str | None = None
    impact: str | None = None
    description: str | None = None
    hardware_type: AssetHardwareType | None = None
    usage_type: AssetUsageType | None = None
    condition: AssetCondition | None = None
    physical_subtype: str | None = None
    virtual_subtype: str | None = None
    product: str | None = None
    model: str | None = None
    vendor: str | None = None
    serial_number: str | None = None
    classification: str | None = None
    cost: float | None = None
    currency: str | None = None
    warranty_info: str | None = None
    acquisition_date: date | None = None
    warranty_expiry: date | None = None
    invoice_number: str | None = None
    po_number: str | None = None
    contract: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    location: str | None = None
    department: str | None = None
    managed_by_group: str | None = None
    end_of_life: date | None = None
    parent_asset_id: uuid.UUID | None = None


class AssetAssignRequest(BaseModel):
    assigned_to_id: uuid.UUID
    assigned_date: date | None = None


class AssetRetireRequest(BaseModel):
    status: AssetStatus  # retired or disposed
    retirement_reason: str = Field(..., min_length=1)
    retirement_date: date


class AssetEventResponse(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    actor_id: uuid.UUID | None = None
    event_type: str
    from_status: str | None = None
    to_status: str | None = None
    detail: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AssetResponse(BaseModel):
    id: uuid.UUID
    asset_tag: str
    name: str
    asset_type: str
    impact: str
    description: str
    status: str
    hardware_type: str
    usage_type: str
    condition: str
    physical_subtype: str | None = None
    virtual_subtype: str | None = None
    product: str | None = None
    model: str | None = None
    vendor: str | None = None
    serial_number: str | None = None
    classification: str | None = None
    cost: float | None = None
    currency: str | None = None
    warranty_info: str | None = None
    acquisition_date: date | None = None
    warranty_expiry: date | None = None
    invoice_number: str | None = None
    po_number: str | None = None
    contract: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    location: str | None = None
    department: str | None = None
    managed_by_group: str | None = None
    assigned_to_id: uuid.UUID | None = None
    assigned_date: date | None = None
    end_of_life: date | None = None
    retirement_reason: str | None = None
    retirement_date: date | None = None
    source: str | None = None
    parent_asset_id: uuid.UUID | None = None
    events: list[AssetEventResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AssetListResponse(BaseModel):
    items: list[AssetResponse]
    total: int
