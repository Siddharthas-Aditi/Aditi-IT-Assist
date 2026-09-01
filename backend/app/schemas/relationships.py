"""Read-only contracts for persisted ITSM relationship tables."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class LinkedAssetOut(BaseModel):
    """The safe, compact asset representation returned from a relationship."""

    id: UUID
    asset_tag: str
    name: str
    status: str


class LinkedChangeOut(BaseModel):
    """The safe, compact change representation returned from an asset."""

    id: UUID
    change_number: str
    title: str
    status: str


class LinkedTicketOut(BaseModel):
    """The compact ticket representation returned to IT staff only."""

    id: UUID
    ticket_number: str
    title: str
    status: str
    priority: str


class ChangeAssetLinksResponse(BaseModel):
    items: list[LinkedAssetOut] = Field(default_factory=list)


class AssetChangeLinksResponse(BaseModel):
    items: list[LinkedChangeOut] = Field(default_factory=list)


class AssetTicketLinksResponse(BaseModel):
    items: list[LinkedTicketOut] = Field(default_factory=list)


class TicketAssetLinksResponse(BaseModel):
    items: list[LinkedAssetOut] = Field(default_factory=list)


__all__ = [
    "AssetChangeLinksResponse",
    "AssetTicketLinksResponse",
    "ChangeAssetLinksResponse",
    "LinkedAssetOut",
    "LinkedChangeOut",
    "LinkedTicketOut",
    "TicketAssetLinksResponse",
]
