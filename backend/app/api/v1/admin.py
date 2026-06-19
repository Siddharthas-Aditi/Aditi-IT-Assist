"""Admin Console endpoints — system stats, user management, audit log.

RBAC: all routes are permission-gated against the canonical registry
(`app.core.permissions`). User-management routes require `admin:manage_users`
(profile/activation) or `admin:assign_roles` (role grants); the audit log
requires `admin:view_audit_log` (held by it_admin and security_auditor).

Every mutation is audit-logged in the service layer with before/after diffs.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import P
from app.models.auth import User
from app.schemas.admin import (
    AuditEventDetail,
    AuditFacets,
    AuditListResponse,
    RoleAssignRequest,
    RoleSummary,
    SystemStats,
    UserDetail,
    UserListResponse,
    UserUpdateRequest,
)
from app.services.admin import AdminStatsService, AdminUserService, AuditQueryService
from app.services.admin.user_service import AdminUserError
from app.services.auth.dependencies import AdminUser, require_permissions

router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]

# Permission-gated actors (the dependency returns the authenticated User).
ManageUsers = Annotated[User, Depends(require_permissions(P.ADMIN_MANAGE_USERS))]
AssignRoles = Annotated[User, Depends(require_permissions(P.ADMIN_ASSIGN_ROLES))]
ViewAudit = Annotated[User, Depends(require_permissions(P.ADMIN_VIEW_AUDIT_LOG))]


def _uuid(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid id format") from exc


def _handle(exc: AdminUserError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


# ─────────────────────────────────────────────────────────────────────
# System stats
# ─────────────────────────────────────────────────────────────────────


@router.get("/stats", response_model=SystemStats)
async def get_system_stats(admin_user: AdminUser, db: DbDep) -> SystemStats:
    """Live admin overview counters. Requires: it_admin role."""
    return await AdminStatsService(db).get_system_stats()


# ─────────────────────────────────────────────────────────────────────
# User management
# ─────────────────────────────────────────────────────────────────────


@router.get("/users", response_model=UserListResponse)
async def list_users(
    actor: ManageUsers,
    db: DbDep,
    search: str | None = None,
    role: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> UserListResponse:
    """List users with search / role / status filters. Requires: admin:manage_users."""
    users, total = await AdminUserService(db).list_users(
        search=search, role=role, status=status_filter, limit=limit, offset=offset
    )
    return UserListResponse(users=users, total=total, limit=limit, offset=offset)


@router.get("/roles", response_model=list[RoleSummary])
async def list_roles(actor: ManageUsers, db: DbDep) -> list[RoleSummary]:
    """List assignable roles. Requires: admin:manage_users."""
    return await AdminUserService(db).list_roles()


@router.get("/users/{user_id}", response_model=UserDetail)
async def get_user(actor: ManageUsers, db: DbDep, user_id: str) -> UserDetail:
    """Fetch a single user with role provenance. Requires: admin:manage_users."""
    detail = await AdminUserService(db).get_user(_uuid(user_id))
    if detail is None:
        raise HTTPException(status_code=404, detail="User not found")
    return detail


@router.patch("/users/{user_id}", response_model=UserDetail)
async def update_user(
    actor: ManageUsers,
    db: DbDep,
    user_id: str,
    data: UserUpdateRequest,
) -> UserDetail:
    """Update profile fields and/or activation state. Requires: admin:manage_users."""
    try:
        return await AdminUserService(db).update_user(
            _uuid(user_id),
            full_name=data.full_name,
            department=data.department,
            job_title=data.job_title,
            phone=data.phone,
            is_active=data.is_active,
            actor=actor,
        )
    except AdminUserError as exc:
        raise _handle(exc) from exc


@router.post("/users/{user_id}/roles", response_model=UserDetail)
async def assign_role(
    actor: AssignRoles,
    db: DbDep,
    user_id: str,
    data: RoleAssignRequest,
) -> UserDetail:
    """Grant a role to a user. Requires: admin:assign_roles."""
    try:
        return await AdminUserService(db).assign_role(_uuid(user_id), data.role, actor=actor)
    except AdminUserError as exc:
        raise _handle(exc) from exc


@router.delete("/users/{user_id}/roles/{role_name}", response_model=UserDetail)
async def revoke_role(
    actor: AssignRoles,
    db: DbDep,
    user_id: str,
    role_name: str,
) -> UserDetail:
    """Revoke a role from a user. Requires: admin:assign_roles."""
    try:
        return await AdminUserService(db).revoke_role(_uuid(user_id), role_name, actor=actor)
    except AdminUserError as exc:
        raise _handle(exc) from exc


# ─────────────────────────────────────────────────────────────────────
# Audit log
# ─────────────────────────────────────────────────────────────────────


@router.get("/audit-log", response_model=AuditListResponse)
async def get_audit_log(
    actor: ViewAudit,
    db: DbDep,
    severity: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    audit_actor: str | None = Query(default=None, alias="actor_email"),
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AuditListResponse:
    """Filtered, paginated audit events. Requires: admin:view_audit_log."""
    events, total = await AuditQueryService(db).list_events(
        severity=severity,
        action=action,
        resource_type=resource_type,
        actor=audit_actor,
        search=search,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return AuditListResponse(events=events, total=total, limit=limit, offset=offset)


@router.get("/audit-log/facets", response_model=AuditFacets)
async def get_audit_facets(actor: ViewAudit, db: DbDep) -> AuditFacets:
    """Distinct filter values for the audit log. Requires: admin:view_audit_log."""
    return await AuditQueryService(db).facets()


@router.get("/audit-log/{event_id}", response_model=AuditEventDetail)
async def get_audit_event(actor: ViewAudit, db: DbDep, event_id: str) -> AuditEventDetail:
    """Single audit event with payload diffs. Requires: admin:view_audit_log."""
    detail = await AuditQueryService(db).get_event(_uuid(event_id))
    if detail is None:
        raise HTTPException(status_code=404, detail="Audit event not found")
    return detail
