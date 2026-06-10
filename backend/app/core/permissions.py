"""
RBAC Permission Constants & Registry.

Single source of truth for all permission definitions, scopes, roles,
and metadata (audit flags, consent requirements).
"""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple

# ─── Role Definitions ──────────────────────────────────────────────────────────


class UserRole(StrEnum):
    """System roles ordered by priority."""

    EMPLOYEE = "employee"
    SECURITY_AUDITOR = "security_auditor"
    IT_AGENT = "it_agent"
    IT_LEAD = "it_lead"
    IT_ADMIN = "it_admin"


ROLE_PRIORITY: dict[UserRole, int] = {
    UserRole.EMPLOYEE: 10,
    UserRole.SECURITY_AUDITOR: 15,
    UserRole.IT_AGENT: 20,
    UserRole.IT_LEAD: 30,
    UserRole.IT_ADMIN: 40,
}

ROLE_INHERITANCE: dict[UserRole, list[UserRole]] = {
    UserRole.EMPLOYEE: [],
    UserRole.SECURITY_AUDITOR: [],
    UserRole.IT_AGENT: [],
    UserRole.IT_LEAD: [UserRole.IT_AGENT],
    UserRole.IT_ADMIN: [UserRole.IT_LEAD, UserRole.IT_AGENT],
}


# ─── Resource & Scope Enums ───────────────────────────────────────────────────


class Resource(StrEnum):
    TICKET = "ticket"
    CHAT = "chat"
    REMOTE = "remote"
    KNOWLEDGE = "knowledge"
    ANALYTICS = "analytics"
    ADMIN = "admin"


class Action(StrEnum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    ASSIGN = "assign"
    REASSIGN = "reassign"
    ESCALATE = "escalate"
    CLOSE = "close"
    REOPEN = "reopen"
    EXPORT = "export"
    APPROVE = "approve"
    TRANSFER = "transfer"
    START = "start"
    END = "end"
    GRANT = "grant"
    REVOKE = "revoke"
    REQUEST = "request"
    MANAGE = "manage"
    VIEW = "view"
    IMPERSONATE = "impersonate"


class Scope(StrEnum):
    OWN = "own"
    ASSIGNED = "assigned"
    TEAM = "team"
    ALL = "all"
    NONE = "none"  # No scope qualifier (global action)


# ─── Permission Entry ──────────────────────────────────────────────────────────


class PermissionDef(NamedTuple):
    """Full definition for a permission."""

    code: str
    name: str
    resource: Resource
    action: Action
    scope: Scope
    audit_required: bool = False
    high_risk: bool = False
    consent_required: bool = False


# ─── Permission Codes ──────────────────────────────────────────────────────────


class P(StrEnum):
    """
    Canonical permission codes.

    Usage in guards:
        require_permissions(P.TICKET_CREATE)
    """

    # ── Tickets ────────────────────────────────────────────
    TICKET_CREATE = "ticket:create"
    TICKET_READ_OWN = "ticket:read_own"
    TICKET_READ_ASSIGNED = "ticket:read_assigned"
    TICKET_READ_TEAM = "ticket:read_team"
    TICKET_READ_ALL = "ticket:read_all"
    TICKET_UPDATE_ASSIGNED = "ticket:update_assigned"
    TICKET_UPDATE_ALL = "ticket:update_all"
    TICKET_ASSIGN = "ticket:assign"
    TICKET_REASSIGN = "ticket:reassign"
    TICKET_ESCALATE = "ticket:escalate"
    TICKET_CLOSE = "ticket:close"
    TICKET_REOPEN = "ticket:reopen"
    TICKET_DELETE = "ticket:delete"
    TICKET_ADD_COMMENT = "ticket:add_comment"
    TICKET_ADD_INTERNAL_NOTE = "ticket:add_internal_note"
    TICKET_VIEW_INTERNAL_NOTES = "ticket:view_internal_notes"
    TICKET_BULK_UPDATE = "ticket:bulk_update"
    TICKET_EXPORT = "ticket:export"

    # ── Chat / Live Support ────────────────────────────────
    CHAT_START = "chat:start"
    CHAT_READ_OWN = "chat:read_own"
    CHAT_READ_ASSIGNED = "chat:read_assigned"
    CHAT_READ_ALL = "chat:read_all"
    CHAT_ACCEPT_HANDOFF = "chat:accept_handoff"
    CHAT_TRANSFER = "chat:transfer"
    CHAT_END_SESSION = "chat:end_session"
    CHAT_REQUEST_LIVE_AGENT = "chat:request_live_agent"

    # ── Remote Support ─────────────────────────────────────
    REMOTE_REQUEST_VIEW = "remote:request_view"
    REMOTE_REQUEST_CONTROL = "remote:request_control"
    REMOTE_GRANT_CONSENT = "remote:grant_consent"
    REMOTE_REVOKE_CONSENT = "remote:revoke_consent"
    REMOTE_START_SESSION = "remote:start_session"
    REMOTE_END_SESSION = "remote:end_session"
    REMOTE_READ_OWN_SESSIONS = "remote:read_own_sessions"
    REMOTE_READ_ALL_SESSIONS = "remote:read_all_sessions"

    # ── Knowledge Base ─────────────────────────────────────
    KNOWLEDGE_READ = "knowledge:read"
    KNOWLEDGE_CREATE = "knowledge:create"
    KNOWLEDGE_UPDATE_OWN = "knowledge:update_own"
    KNOWLEDGE_UPDATE_ALL = "knowledge:update_all"
    KNOWLEDGE_APPROVE = "knowledge:approve"
    KNOWLEDGE_DELETE = "knowledge:delete"
    KNOWLEDGE_MANAGE_CATEGORIES = "knowledge:manage_categories"

    # ── Analytics ──────────────────────────────────────────
    ANALYTICS_VIEW_OWN = "analytics:view_own"
    ANALYTICS_VIEW_TEAM = "analytics:view_team"
    ANALYTICS_VIEW_ALL = "analytics:view_all"
    ANALYTICS_EXPORT = "analytics:export"
    ANALYTICS_VIEW_AGENT_PERF = "analytics:view_agent_perf"

    # ── Administration ─────────────────────────────────────
    ADMIN_MANAGE_USERS = "admin:manage_users"
    ADMIN_MANAGE_ROLES = "admin:manage_roles"
    ADMIN_ASSIGN_ROLES = "admin:assign_roles"
    ADMIN_MANAGE_GROUPS = "admin:manage_groups"
    ADMIN_MANAGE_SETTINGS = "admin:manage_settings"
    ADMIN_MANAGE_INTEGRATIONS = "admin:manage_integrations"
    ADMIN_MANAGE_SLA_POLICIES = "admin:manage_sla_policies"
    ADMIN_VIEW_AUDIT_LOG = "admin:view_audit_log"
    ADMIN_EXPORT_AUDIT_LOG = "admin:export_audit_log"
    ADMIN_IMPERSONATE_USER = "admin:impersonate_user"


# ─── Permission Registry ───────────────────────────────────────────────────────
#
# Authoritative list with metadata. Drives seed scripts, documentation,
# and runtime permission checks.
#

PERMISSION_REGISTRY: list[PermissionDef] = [
    # ── Tickets ──
    PermissionDef(P.TICKET_CREATE, "Create Ticket", Resource.TICKET, Action.CREATE, Scope.OWN),
    PermissionDef(P.TICKET_READ_OWN, "Read Own Tickets", Resource.TICKET, Action.READ, Scope.OWN),
    PermissionDef(P.TICKET_READ_ASSIGNED, "Read Assigned Tickets", Resource.TICKET, Action.READ, Scope.ASSIGNED),
    PermissionDef(P.TICKET_READ_TEAM, "Read Team Tickets", Resource.TICKET, Action.READ, Scope.TEAM),
    PermissionDef(P.TICKET_READ_ALL, "Read All Tickets", Resource.TICKET, Action.READ, Scope.ALL),
    PermissionDef(P.TICKET_UPDATE_ASSIGNED, "Update Assigned Tickets", Resource.TICKET, Action.UPDATE, Scope.ASSIGNED, audit_required=True),
    PermissionDef(P.TICKET_UPDATE_ALL, "Update Any Ticket", Resource.TICKET, Action.UPDATE, Scope.ALL, audit_required=True),
    PermissionDef(P.TICKET_ASSIGN, "Assign Ticket", Resource.TICKET, Action.ASSIGN, Scope.TEAM, audit_required=True),
    PermissionDef(P.TICKET_REASSIGN, "Reassign Ticket", Resource.TICKET, Action.REASSIGN, Scope.ALL, audit_required=True),
    PermissionDef(P.TICKET_ESCALATE, "Escalate Ticket", Resource.TICKET, Action.ESCALATE, Scope.ASSIGNED, audit_required=True),
    PermissionDef(P.TICKET_CLOSE, "Close Ticket", Resource.TICKET, Action.CLOSE, Scope.TEAM, audit_required=True),
    PermissionDef(P.TICKET_REOPEN, "Reopen Ticket", Resource.TICKET, Action.REOPEN, Scope.OWN, audit_required=True),
    PermissionDef(P.TICKET_DELETE, "Delete Ticket", Resource.TICKET, Action.DELETE, Scope.ALL, audit_required=True, high_risk=True),
    PermissionDef(P.TICKET_ADD_COMMENT, "Add Comment", Resource.TICKET, Action.CREATE, Scope.OWN),
    PermissionDef(P.TICKET_ADD_INTERNAL_NOTE, "Add Internal Note", Resource.TICKET, Action.CREATE, Scope.ASSIGNED),
    PermissionDef(P.TICKET_VIEW_INTERNAL_NOTES, "View Internal Notes", Resource.TICKET, Action.READ, Scope.ASSIGNED),
    PermissionDef(P.TICKET_BULK_UPDATE, "Bulk Update Tickets", Resource.TICKET, Action.UPDATE, Scope.TEAM, audit_required=True),
    PermissionDef(P.TICKET_EXPORT, "Export Tickets", Resource.TICKET, Action.EXPORT, Scope.ALL, audit_required=True),
    # ── Chat ──
    PermissionDef(P.CHAT_START, "Start Chat", Resource.CHAT, Action.START, Scope.OWN),
    PermissionDef(P.CHAT_READ_OWN, "Read Own Chats", Resource.CHAT, Action.READ, Scope.OWN),
    PermissionDef(P.CHAT_READ_ASSIGNED, "Read Assigned Chats", Resource.CHAT, Action.READ, Scope.ASSIGNED),
    PermissionDef(P.CHAT_READ_ALL, "Read All Chats", Resource.CHAT, Action.READ, Scope.ALL),
    PermissionDef(P.CHAT_ACCEPT_HANDOFF, "Accept Handoff", Resource.CHAT, Action.ASSIGN, Scope.TEAM, audit_required=True),
    PermissionDef(P.CHAT_TRANSFER, "Transfer Chat", Resource.CHAT, Action.TRANSFER, Scope.ASSIGNED, audit_required=True),
    PermissionDef(P.CHAT_END_SESSION, "End Chat Session", Resource.CHAT, Action.END, Scope.ASSIGNED),
    PermissionDef(P.CHAT_REQUEST_LIVE_AGENT, "Request Live Agent", Resource.CHAT, Action.REQUEST, Scope.OWN),
    # ── Remote Support ──
    PermissionDef(P.REMOTE_REQUEST_VIEW, "Request Screen View", Resource.REMOTE, Action.REQUEST, Scope.NONE, audit_required=True),
    PermissionDef(P.REMOTE_REQUEST_CONTROL, "Request Screen Control", Resource.REMOTE, Action.REQUEST, Scope.NONE, audit_required=True, high_risk=True),
    PermissionDef(P.REMOTE_GRANT_CONSENT, "Grant Remote Consent", Resource.REMOTE, Action.GRANT, Scope.OWN, audit_required=True, consent_required=True),
    PermissionDef(P.REMOTE_REVOKE_CONSENT, "Revoke Remote Consent", Resource.REMOTE, Action.REVOKE, Scope.OWN, audit_required=True),
    PermissionDef(P.REMOTE_START_SESSION, "Start Remote Session", Resource.REMOTE, Action.START, Scope.NONE, audit_required=True, high_risk=True),
    PermissionDef(P.REMOTE_END_SESSION, "End Remote Session", Resource.REMOTE, Action.END, Scope.NONE, audit_required=True),
    PermissionDef(P.REMOTE_READ_OWN_SESSIONS, "Read Own Remote Sessions", Resource.REMOTE, Action.READ, Scope.OWN),
    PermissionDef(P.REMOTE_READ_ALL_SESSIONS, "Read All Remote Sessions", Resource.REMOTE, Action.READ, Scope.ALL),
    # ── Knowledge ──
    PermissionDef(P.KNOWLEDGE_READ, "Read Knowledge Base", Resource.KNOWLEDGE, Action.READ, Scope.ALL),
    PermissionDef(P.KNOWLEDGE_CREATE, "Create KB Article", Resource.KNOWLEDGE, Action.CREATE, Scope.NONE),
    PermissionDef(P.KNOWLEDGE_UPDATE_OWN, "Update Own KB Articles", Resource.KNOWLEDGE, Action.UPDATE, Scope.OWN),
    PermissionDef(P.KNOWLEDGE_UPDATE_ALL, "Update Any KB Article", Resource.KNOWLEDGE, Action.UPDATE, Scope.ALL, audit_required=True),
    PermissionDef(P.KNOWLEDGE_APPROVE, "Approve KB Article", Resource.KNOWLEDGE, Action.APPROVE, Scope.ALL, audit_required=True),
    PermissionDef(P.KNOWLEDGE_DELETE, "Delete KB Article", Resource.KNOWLEDGE, Action.DELETE, Scope.ALL, audit_required=True, high_risk=True),
    PermissionDef(P.KNOWLEDGE_MANAGE_CATEGORIES, "Manage KB Categories", Resource.KNOWLEDGE, Action.MANAGE, Scope.ALL, audit_required=True),
    # ── Analytics ──
    PermissionDef(P.ANALYTICS_VIEW_OWN, "View Own Stats", Resource.ANALYTICS, Action.VIEW, Scope.OWN),
    PermissionDef(P.ANALYTICS_VIEW_TEAM, "View Team Analytics", Resource.ANALYTICS, Action.VIEW, Scope.TEAM),
    PermissionDef(P.ANALYTICS_VIEW_ALL, "View Global Analytics", Resource.ANALYTICS, Action.VIEW, Scope.ALL),
    PermissionDef(P.ANALYTICS_EXPORT, "Export Reports", Resource.ANALYTICS, Action.EXPORT, Scope.ALL, audit_required=True),
    PermissionDef(P.ANALYTICS_VIEW_AGENT_PERF, "View Agent Performance", Resource.ANALYTICS, Action.VIEW, Scope.TEAM),
    # ── Administration ──
    PermissionDef(P.ADMIN_MANAGE_USERS, "Manage Users", Resource.ADMIN, Action.MANAGE, Scope.ALL, audit_required=True, high_risk=True),
    PermissionDef(P.ADMIN_MANAGE_ROLES, "Manage Roles", Resource.ADMIN, Action.MANAGE, Scope.ALL, audit_required=True, high_risk=True),
    PermissionDef(P.ADMIN_ASSIGN_ROLES, "Assign Roles to Users", Resource.ADMIN, Action.ASSIGN, Scope.ALL, audit_required=True, high_risk=True),
    PermissionDef(P.ADMIN_MANAGE_GROUPS, "Manage Groups", Resource.ADMIN, Action.MANAGE, Scope.ALL, audit_required=True),
    PermissionDef(P.ADMIN_MANAGE_SETTINGS, "Manage System Settings", Resource.ADMIN, Action.MANAGE, Scope.ALL, audit_required=True, high_risk=True),
    PermissionDef(P.ADMIN_MANAGE_INTEGRATIONS, "Manage Integrations", Resource.ADMIN, Action.MANAGE, Scope.ALL, audit_required=True, high_risk=True),
    PermissionDef(P.ADMIN_MANAGE_SLA_POLICIES, "Manage SLA Policies", Resource.ADMIN, Action.MANAGE, Scope.ALL, audit_required=True),
    PermissionDef(P.ADMIN_VIEW_AUDIT_LOG, "View Audit Log", Resource.ADMIN, Action.VIEW, Scope.ALL),
    PermissionDef(P.ADMIN_EXPORT_AUDIT_LOG, "Export Audit Log", Resource.ADMIN, Action.EXPORT, Scope.ALL, audit_required=True),
    PermissionDef(P.ADMIN_IMPERSONATE_USER, "Impersonate User", Resource.ADMIN, Action.IMPERSONATE, Scope.ALL, audit_required=True, high_risk=True, consent_required=True),
]


# ─── Role → Permission Mapping ─────────────────────────────────────────────────

ROLE_PERMISSIONS: dict[UserRole, list[P]] = {
    UserRole.EMPLOYEE: [
        P.TICKET_CREATE,
        P.TICKET_READ_OWN,
        P.TICKET_REOPEN,
        P.TICKET_ADD_COMMENT,
        P.CHAT_START,
        P.CHAT_READ_OWN,
        P.CHAT_REQUEST_LIVE_AGENT,
        P.REMOTE_GRANT_CONSENT,
        P.REMOTE_REVOKE_CONSENT,
        P.REMOTE_END_SESSION,
        P.REMOTE_READ_OWN_SESSIONS,
        P.KNOWLEDGE_READ,
        P.ANALYTICS_VIEW_OWN,
    ],
    UserRole.SECURITY_AUDITOR: [
        P.TICKET_READ_ALL,
        P.TICKET_VIEW_INTERNAL_NOTES,
        P.REMOTE_READ_ALL_SESSIONS,
        P.ANALYTICS_VIEW_ALL,
        P.ADMIN_VIEW_AUDIT_LOG,
    ],
    UserRole.IT_AGENT: [
        # Inherited from no one, explicit grants:
        P.TICKET_CREATE,
        P.TICKET_READ_OWN,
        P.TICKET_READ_ASSIGNED,
        P.TICKET_UPDATE_ASSIGNED,
        P.TICKET_ASSIGN,
        P.TICKET_ESCALATE,
        P.TICKET_REOPEN,
        P.TICKET_ADD_COMMENT,
        P.TICKET_ADD_INTERNAL_NOTE,
        P.TICKET_VIEW_INTERNAL_NOTES,
        P.CHAT_START,
        P.CHAT_READ_OWN,
        P.CHAT_READ_ASSIGNED,
        P.CHAT_ACCEPT_HANDOFF,
        P.CHAT_TRANSFER,
        P.CHAT_END_SESSION,
        P.REMOTE_REQUEST_VIEW,
        P.REMOTE_START_SESSION,
        P.REMOTE_END_SESSION,
        P.REMOTE_READ_OWN_SESSIONS,
        P.KNOWLEDGE_READ,
        P.KNOWLEDGE_CREATE,
        P.KNOWLEDGE_UPDATE_OWN,
        P.ANALYTICS_VIEW_OWN,
    ],
    UserRole.IT_LEAD: [
        # Inherits all IT_AGENT permissions, plus:
        P.TICKET_READ_TEAM,
        P.TICKET_UPDATE_ALL,
        P.TICKET_REASSIGN,
        P.TICKET_CLOSE,
        P.TICKET_BULK_UPDATE,
        P.TICKET_EXPORT,
        P.CHAT_READ_ALL,
        P.REMOTE_READ_ALL_SESSIONS,
        P.KNOWLEDGE_UPDATE_ALL,
        P.KNOWLEDGE_APPROVE,
        P.ANALYTICS_VIEW_TEAM,
        P.ANALYTICS_VIEW_ALL,
        P.ANALYTICS_VIEW_AGENT_PERF,
    ],
    UserRole.IT_ADMIN: [
        # Inherits all IT_LEAD permissions, plus:
        P.TICKET_READ_ALL,
        P.TICKET_DELETE,
        P.REMOTE_REQUEST_CONTROL,
        P.KNOWLEDGE_DELETE,
        P.KNOWLEDGE_MANAGE_CATEGORIES,
        P.ANALYTICS_EXPORT,
        P.ADMIN_MANAGE_USERS,
        P.ADMIN_MANAGE_ROLES,
        P.ADMIN_ASSIGN_ROLES,
        P.ADMIN_MANAGE_GROUPS,
        P.ADMIN_MANAGE_SETTINGS,
        P.ADMIN_MANAGE_INTEGRATIONS,
        P.ADMIN_MANAGE_SLA_POLICIES,
        P.ADMIN_VIEW_AUDIT_LOG,
        P.ADMIN_EXPORT_AUDIT_LOG,
        P.ADMIN_IMPERSONATE_USER,
    ],
}


# ─── Helpers ───────────────────────────────────────────────────────────────────


def get_effective_permissions(role: UserRole) -> set[P]:
    """
    Return the full set of permissions for a role,
    including inherited permissions from lower roles.
    """
    perms: set[P] = set(ROLE_PERMISSIONS.get(role, []))
    for inherited_role in ROLE_INHERITANCE.get(role, []):
        perms |= set(ROLE_PERMISSIONS.get(inherited_role, []))
    return perms


def get_permission_def(code: str) -> PermissionDef | None:
    """Look up full definition for a permission code."""
    for perm in PERMISSION_REGISTRY:
        if perm.code == code:
            return perm
    return None


def is_high_risk(code: str) -> bool:
    """Check if a permission code is flagged as high-risk."""
    defn = get_permission_def(code)
    return defn.high_risk if defn else False


def requires_audit(code: str) -> bool:
    """Check if a permission action requires audit logging."""
    defn = get_permission_def(code)
    return defn.audit_required if defn else False


def requires_consent(code: str) -> bool:
    """Check if a permission action requires user consent."""
    defn = get_permission_def(code)
    return defn.consent_required if defn else False


# ── High-risk codes (convenience set for middleware / decorators) ──
HIGH_RISK_PERMISSIONS: frozenset[str] = frozenset(
    p.code for p in PERMISSION_REGISTRY if p.high_risk
)

# ── Consent-required codes ──
CONSENT_REQUIRED_PERMISSIONS: frozenset[str] = frozenset(
    p.code for p in PERMISSION_REGISTRY if p.consent_required
)

# ── Auditable codes ──
AUDIT_REQUIRED_PERMISSIONS: frozenset[str] = frozenset(
    p.code for p in PERMISSION_REGISTRY if p.audit_required
)
