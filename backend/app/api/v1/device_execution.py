"""Device Execution API (Phase 9).

Human/agent surface for catalog-bound Intune actions:

* ``GET  /device-execution/catalog``        — what the agent may run + current autonomy config
                                               (it_agent+).
* ``POST /device-execution/actions``         — request an action; the service routes it to
                                               autonomous execution, the approval queue, or denial
                                               (it_agent+).
* ``POST /device-execution/approvals/{id}/approve`` — carry out a parked action, re-checking
                                               consent + eligibility first (it_lead+).
* ``POST /device-execution/approvals/{id}/reject``  — reject a parked action (it_lead+).

Handlers stay thin: build a ``ToolContext`` from the authenticated user and
delegate to :class:`DeviceExecutionService`. RBAC for *executing* is enforced by
the runtime against the caller's ``integration:device_execute`` permission; the
request endpoint itself is open to it_agent+ because an unauthorized requester's
autonomous action gracefully falls back to the approval queue.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.auth import User
from app.schemas.device_execution import (
    CatalogEntryOut,
    DeviceActionOutcomeResponse,
    DeviceActionRequest,
    DeviceApprovalDecision,
    DeviceCatalogResponse,
)
from app.services.agents.device_actions import catalog as cat
from app.services.agents.device_actions.catalog import APP_CATALOG
from app.services.agents.device_actions.policy import AUTONOMY_POLICY_VERSION
from app.services.agents.device_actions.service import DeviceExecOutcome, DeviceExecutionService
from app.services.agents.device_actions.tools import DEVICE_TOOL_BINDINGS
from app.services.agents.tools.base import ToolContext
from app.services.audit_service import AuditService
from app.services.auth.dependencies import require_roles
from app.services.auth.service import AuthService

router = APIRouter()

DBDep = Annotated[AsyncSession, Depends(get_db)]
ITStaff = Annotated[User, Depends(require_roles("it_agent", "it_lead", "it_admin"))]
Lead = Annotated[User, Depends(require_roles("it_lead", "it_admin"))]


async def _ctx(user: User, db: AsyncSession) -> ToolContext:
    perms = await AuthService(db).get_user_permissions(user)
    return ToolContext(
        user_id=str(user.id),
        permissions=frozenset(perms),
        roles=tuple(user.role_names),
    )


def _service(db: AsyncSession) -> DeviceExecutionService:
    return DeviceExecutionService(db, audit_service=AuditService(db))


def _outcome_response(o: DeviceExecOutcome) -> DeviceActionOutcomeResponse:
    return DeviceActionOutcomeResponse(
        status=o.status.value,
        decision=o.decision,
        tool_name=o.tool_name,
        action_ref=o.action_ref,
        device_id=o.device_id,
        risk_tier=o.risk_tier,
        reason=o.reason,
        approval_id=o.approval_id,
        result=o.result,
        policy_signals=o.policy_signals,
        policy_version=o.policy_version,
    )


def _require_device_execution_enabled() -> None:
    """Guard the mutating device-execution endpoints on the master build gate.

    Applied to both action submission and approval: without it, actions queued
    while the feature was on could still be approved (and executed) after it was
    turned off, defeating the kill-switch. Rejecting a parked action stays
    allowed so operators can drain the queue after disabling.
    """
    if not settings.FEATURE_DEVICE_EXECUTION:
        raise HTTPException(status_code=403, detail="Device execution is disabled")


# ── Catalog ────────────────────────────────────────────────────────────────


@router.get("/catalog", response_model=DeviceCatalogResponse)
async def get_catalog(_user: ITStaff) -> DeviceCatalogResponse:
    def apps() -> list[CatalogEntryOut]:
        return [
            CatalogEntryOut(
                id=e.app_id,
                kind="install_app",
                display_name=e.display_name,
                risk_tier=e.risk_tier.value,
                reversible=e.reversible,
                description=e.description,
            )
            for e in APP_CATALOG.values()
        ]

    def remediations() -> list[CatalogEntryOut]:
        return [
            CatalogEntryOut(
                id=e.remediation_id,
                kind="remediation",
                display_name=e.display_name,
                risk_tier=e.risk_tier.value,
                reversible=e.reversible,
                description=e.description,
            )
            for e in cat.REMEDIATION_CATALOG.values()
        ]

    def device_actions() -> list[CatalogEntryOut]:
        return [
            CatalogEntryOut(
                id=e.action_id,
                kind="device_action",
                display_name=e.display_name,
                risk_tier=e.risk_tier.value,
                reversible=e.reversible,
                description=e.description,
            )
            for e in cat.DEVICE_ACTION_CATALOG.values()
        ]

    return DeviceCatalogResponse(
        catalog_version=cat.CATALOG_VERSION,
        policy_version=AUTONOMY_POLICY_VERSION,
        autonomous_enabled=settings.FEATURE_DEVICE_EXECUTION
        and settings.DEVICE_EXECUTION_AUTONOMOUS,
        autonomous_medium_allowed=settings.DEVICE_EXECUTION_AUTONOMOUS_MEDIUM,
        apps=apps(),
        remediations=remediations(),
        device_actions=device_actions(),
    )


# ── Request an action ──────────────────────────────────────────────────────


@router.post("/actions", response_model=DeviceActionOutcomeResponse)
async def request_action(
    body: DeviceActionRequest, user: ITStaff, db: DBDep
) -> DeviceActionOutcomeResponse:
    _require_device_execution_enabled()
    binding = DEVICE_TOOL_BINDINGS.get(body.tool_name)
    if binding is None:
        raise HTTPException(status_code=400, detail=f"Unknown device tool {body.tool_name!r}")
    args = {
        binding.id_field: body.action_ref,
        "device_id": body.device_id,
        "idempotency_key": body.idempotency_key,
        "justification": body.justification,
    }
    outcome = await _service(db).request_action(
        tool_name=body.tool_name,
        args=args,
        requester=await _ctx(user, db),
        employee_id=body.employee_id,
        reason=body.reason,
    )
    return _outcome_response(outcome)


# ── Approve / reject ───────────────────────────────────────────────────────


@router.post("/approvals/{approval_id}/approve", response_model=DeviceActionOutcomeResponse)
async def approve_action(
    approval_id: str, body: DeviceApprovalDecision, user: Lead, db: DBDep
) -> DeviceActionOutcomeResponse:
    _require_device_execution_enabled()
    service = _service(db)
    try:
        record = await service.approve(
            approval_id, approver=await _ctx(user, db), employee_id=body.employee_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Approval not found") from exc
    return DeviceActionOutcomeResponse(
        status="executed" if record.status.value == "approved" else record.status.value,
        decision="human_approval",
        tool_name=record.tool_name,
        action_ref=record.raw_args.get(DEVICE_TOOL_BINDINGS[record.tool_name].id_field, "")
        if record.tool_name in DEVICE_TOOL_BINDINGS
        else "",
        device_id=record.raw_args.get("device_id", ""),
        reason=record.error or "",
        approval_id=record.id,
        result=record.result,
        policy_version=AUTONOMY_POLICY_VERSION,
    )


@router.post("/approvals/{approval_id}/reject", response_model=DeviceActionOutcomeResponse)
async def reject_action(approval_id: str, user: Lead, db: DBDep) -> DeviceActionOutcomeResponse:
    service = _service(db)
    if service._queue.get(approval_id) is None:  # noqa: SLF001
        raise HTTPException(status_code=404, detail="Approval not found")
    record = service.reject(approval_id, str(user.id))
    return DeviceActionOutcomeResponse(
        status=record.status.value,
        decision="human_approval",
        tool_name=record.tool_name,
        action_ref="",
        device_id=record.raw_args.get("device_id", ""),
        approval_id=record.id,
        policy_version=AUTONOMY_POLICY_VERSION,
    )


__all__ = ["router"]
