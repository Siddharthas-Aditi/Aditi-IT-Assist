"""Pydantic schemas for the Admin Console — user management, audit log, stats.

These are the request/response contracts for the `/admin/*` endpoints. They are
intentionally explicit (typed, versioned) so the frontend can rely on a stable
shape and so the audit/RBAC surface is reviewable.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ─────────────────────────────────────────────────────────────────────
# User management
# ─────────────────────────────────────────────────────────────────────


class RoleSummary(BaseModel):
    """A role definition the admin can assign."""

    name: str
    display_name: str
    description: str | None = None
    priority: int = 0


class RoleAssignmentInfo(BaseModel):
    """A single role assignment on a user (with provenance)."""

    role: str
    display_name: str
    assigned_at: datetime | None = None
    expires_at: datetime | None = None


class UserSummary(BaseModel):
    """User row for the management list."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    department: str | None = None
    job_title: str | None = None
    is_active: bool = True
    is_verified: bool = False
    primary_role: str = "employee"
    roles: list[str] = Field(default_factory=list)
    last_login_at: datetime | None = None
    created_at: datetime | None = None


class UserDetail(UserSummary):
    """Full user detail for the detail/edit page."""

    employee_id: str | None = None
    phone: str | None = None
    role_assignments: list[RoleAssignmentInfo] = Field(default_factory=list)


class UserListResponse(BaseModel):
    users: list[UserSummary]
    total: int
    limit: int
    offset: int


class UserUpdateRequest(BaseModel):
    """Patch a user's profile / activation state. All fields optional."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    department: str | None = Field(default=None, max_length=100)
    job_title: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None


class RoleAssignRequest(BaseModel):
    """Assign a role to a user."""

    role: str = Field(..., description="Role name, e.g. 'it_agent'")


# ─────────────────────────────────────────────────────────────────────
# Audit log
# ─────────────────────────────────────────────────────────────────────


class AuditEventOut(BaseModel):
    """A single audit event."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    actor_email: str | None = None
    actor_role: str | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    description: str | None = None
    severity: str = "info"
    ip_address: str | None = None
    created_at: datetime


class AuditEventDetail(AuditEventOut):
    """Full audit event including payload diffs and context."""

    user_agent: str | None = None
    old_value: dict | None = None
    new_value: dict | None = None
    metadata_json: dict | None = None


class AuditListResponse(BaseModel):
    events: list[AuditEventOut]
    total: int
    limit: int
    offset: int


class AuditFacets(BaseModel):
    """Distinct values for building audit-log filter dropdowns."""

    actions: list[str] = Field(default_factory=list)
    resource_types: list[str] = Field(default_factory=list)
    severities: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────
# System stats
# ─────────────────────────────────────────────────────────────────────


class SystemStats(BaseModel):
    """Admin overview counters — all real, all NaN-safe."""

    total_users: int = 0
    active_users: int = 0
    total_tickets: int = 0
    open_tickets: int = 0
    published_articles: int = 0
    draft_articles: int = 0
    audit_events_24h: int = 0
    total_sessions: int = 0
    resolution_rate: float = 0.0
