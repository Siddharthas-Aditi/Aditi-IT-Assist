"""Schemas for the Device Execution API (Phase 9)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ── Catalog (read) ────────────────────────────────────────────────────────────


class CatalogEntryOut(BaseModel):
    id: str
    kind: str  # install_app | remediation | device_action
    display_name: str
    risk_tier: str
    reversible: bool
    description: str = ""


class DeviceCatalogResponse(BaseModel):
    catalog_version: str
    policy_version: str
    autonomous_enabled: bool
    autonomous_medium_allowed: bool
    apps: list[CatalogEntryOut]
    remediations: list[CatalogEntryOut]
    device_actions: list[CatalogEntryOut]


# ── Request an action ─────────────────────────────────────────────────────────


class DeviceActionRequest(BaseModel):
    tool_name: str = Field(
        ..., description="install_win32_app | run_remediation_script | device_action"
    )
    action_ref: str = Field(
        ..., description="Catalog id (e.g. 'python-3.12', 'flush-dns', 'sync')."
    )
    device_id: str = Field(..., min_length=2, description="Target Intune managed device id.")
    employee_id: str = Field(..., description="Target employee id (consent is checked for them).")
    idempotency_key: str = Field(..., min_length=8, description="Caller-generated dedupe key.")
    justification: str = Field("", description="Why this action is needed (scanned, never run).")
    reason: str = Field("", description="Free-text note recorded on any queued approval.")


class DeviceActionOutcomeResponse(BaseModel):
    status: str  # executed | pending_approval | denied | rejected | error
    decision: str  # autonomous | human_approval | deny
    tool_name: str
    action_ref: str
    device_id: str
    risk_tier: str | None = None
    reason: str = ""
    approval_id: str | None = None
    result: dict[str, Any] | None = None
    policy_signals: list[str] = Field(default_factory=list)
    policy_version: str


# ── Approve / reject a parked device action ───────────────────────────────────


class DeviceApprovalDecision(BaseModel):
    employee_id: str = Field(..., description="Target employee (consent re-checked at approval).")


__all__ = [
    "CatalogEntryOut",
    "DeviceActionOutcomeResponse",
    "DeviceActionRequest",
    "DeviceApprovalDecision",
    "DeviceCatalogResponse",
]
