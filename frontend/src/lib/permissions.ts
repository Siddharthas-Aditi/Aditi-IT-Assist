/**
 * Frontend RBAC mirror of `backend/app/core/permissions.py`.
 *
 * The backend remains the source of truth and enforces every action; this file
 * provides client-side gating so the UI only *shows* what a role may do. Keep
 * the permission codes and role→permission mapping in sync with the backend.
 */

export type UserRole =
  | 'employee'
  | 'it_agent'
  | 'it_lead'
  | 'it_admin'
  | 'security_auditor';

/** Canonical permission codes (subset relevant to the frontend, KB-focused). */
export const P = {
  // Knowledge — read & retrieval
  KNOWLEDGE_READ: 'knowledge:read',
  KNOWLEDGE_VIEW_INTERNAL: 'knowledge:view_internal',
  KNOWLEDGE_SUBMIT_FEEDBACK: 'knowledge:submit_feedback',
  KNOWLEDGE_SUGGEST: 'knowledge:suggest',
  // Knowledge — authoring & lifecycle
  KNOWLEDGE_CREATE: 'knowledge:create',
  KNOWLEDGE_UPDATE_OWN: 'knowledge:update_own',
  KNOWLEDGE_UPDATE_ALL: 'knowledge:update_all',
  KNOWLEDGE_SUBMIT_REVIEW: 'knowledge:submit_review',
  KNOWLEDGE_REVIEW: 'knowledge:review',
  KNOWLEDGE_APPROVE: 'knowledge:approve',
  KNOWLEDGE_PUBLISH: 'knowledge:publish',
  KNOWLEDGE_ARCHIVE: 'knowledge:archive',
  KNOWLEDGE_DELETE: 'knowledge:delete',
  // Knowledge — governance & ops
  KNOWLEDGE_MANAGE_CATEGORIES: 'knowledge:manage_categories',
  KNOWLEDGE_MANAGE_OWNERSHIP: 'knowledge:manage_ownership',
  KNOWLEDGE_REINDEX: 'knowledge:reindex',
  KNOWLEDGE_VIEW_ANALYTICS: 'knowledge:view_analytics',
  // Cross-cutting
  ADMIN_VIEW_AUDIT_LOG: 'admin:view_audit_log',
} as const;

// `string & Record<never, never>` preserves literal autocomplete on the known
// permission codes while still accepting any string (the lint-safe form of the
// classic `string & {}` idiom).
export type PermissionCode = (typeof P)[keyof typeof P] | (string & Record<never, never>);

/** Default landing route per role. */
export const DEFAULT_ROUTES: Record<UserRole, string> = {
  employee: '/support',
  it_agent: '/operations',
  it_lead: '/dashboard',
  it_admin: '/dashboard',
  security_auditor: '/audit',
};

/**
 * Effective knowledge permissions per role — mirrors backend
 * `get_effective_permissions` (inheritance pre-expanded). Used when the
 * AuthUser object does not carry an explicit permission list.
 */
const EMPLOYEE_PERMS: PermissionCode[] = [
  P.KNOWLEDGE_READ,
  P.KNOWLEDGE_SUBMIT_FEEDBACK,
];

const AGENT_PERMS: PermissionCode[] = [
  ...EMPLOYEE_PERMS,
  P.KNOWLEDGE_VIEW_INTERNAL,
  P.KNOWLEDGE_CREATE,
  P.KNOWLEDGE_UPDATE_OWN,
  P.KNOWLEDGE_SUBMIT_REVIEW,
  P.KNOWLEDGE_SUGGEST,
];

const LEAD_PERMS: PermissionCode[] = [
  ...AGENT_PERMS,
  P.KNOWLEDGE_UPDATE_ALL,
  P.KNOWLEDGE_REVIEW,
  P.KNOWLEDGE_APPROVE,
  P.KNOWLEDGE_PUBLISH,
  P.KNOWLEDGE_ARCHIVE,
  P.KNOWLEDGE_VIEW_ANALYTICS,
];

const ADMIN_PERMS: PermissionCode[] = [
  ...LEAD_PERMS,
  P.KNOWLEDGE_DELETE,
  P.KNOWLEDGE_MANAGE_CATEGORIES,
  P.KNOWLEDGE_MANAGE_OWNERSHIP,
  P.KNOWLEDGE_REINDEX,
  P.ADMIN_VIEW_AUDIT_LOG,
];

const AUDITOR_PERMS: PermissionCode[] = [
  P.KNOWLEDGE_READ,
  P.KNOWLEDGE_VIEW_INTERNAL,
  P.ADMIN_VIEW_AUDIT_LOG,
];

export const ROLE_PERMISSIONS: Record<UserRole, PermissionCode[]> = {
  employee: EMPLOYEE_PERMS,
  it_agent: AGENT_PERMS,
  it_lead: LEAD_PERMS,
  it_admin: ADMIN_PERMS,
  security_auditor: AUDITOR_PERMS,
};

interface RoleBearing {
  role?: UserRole;
  roles?: UserRole[];
  permissions?: PermissionCode[];
}

function rolesOf(user: RoleBearing | null | undefined): UserRole[] {
  if (!user) return [];
  if (user.roles?.length) return user.roles;
  return user.role ? [user.role] : [];
}

export function isITStaff(user: RoleBearing | null | undefined): boolean {
  return rolesOf(user).some((r) => r === 'it_agent' || r === 'it_lead' || r === 'it_admin');
}

export function isLeadOrAbove(user: RoleBearing | null | undefined): boolean {
  return rolesOf(user).some((r) => r === 'it_lead' || r === 'it_admin');
}

export function isAdmin(user: RoleBearing | null | undefined): boolean {
  return rolesOf(user).includes('it_admin');
}

/** Resolve the effective permission set for a user (explicit list or role-derived). */
export function effectivePermissions(user: RoleBearing | null | undefined): Set<PermissionCode> {
  if (user?.permissions?.length) return new Set(user.permissions);
  const perms = new Set<PermissionCode>();
  for (const role of rolesOf(user)) {
    for (const p of ROLE_PERMISSIONS[role] ?? []) perms.add(p);
  }
  return perms;
}

export function hasPermission(
  user: RoleBearing | null | undefined,
  code: PermissionCode,
): boolean {
  return effectivePermissions(user).has(code);
}

export function getDefaultRoute(user: RoleBearing | null | undefined): string {
  const roles = rolesOf(user);
  // Highest-privilege landing route wins.
  if (roles.includes('it_admin')) return DEFAULT_ROUTES.it_admin;
  if (roles.includes('it_lead')) return DEFAULT_ROUTES.it_lead;
  if (roles.includes('it_agent')) return DEFAULT_ROUTES.it_agent;
  if (roles.includes('security_auditor')) return DEFAULT_ROUTES.security_auditor;
  return DEFAULT_ROUTES.employee;
}

export function canAccessRoute(
  user: RoleBearing | null | undefined,
  allowedRoles: UserRole[],
): boolean {
  const roles = rolesOf(user);
  return allowedRoles.some((r) => roles.includes(r));
}
