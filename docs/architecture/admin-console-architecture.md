# Admin Console — Architecture

The Admin Console follows the project's clean-architecture rule: **routes →
services → models**, typed Pydantic contracts, RBAC via permission guards, and
audit logging in the service layer. The frontend mirrors this with typed React
Query hooks and permission-aware UI.

## Backend

### Routes — `app/api/v1/admin.py` (prefix `/api/v1/admin`)

| Method | Path | Permission | Purpose |
|--------|------|------------|---------|
| GET | `/stats` | role `it_admin` | Live system counters (users, tickets, KB, audit, sessions) |
| GET | `/users` | `admin:manage_users` | List users (search, role, status, pagination) |
| GET | `/users/{id}` | `admin:manage_users` | User detail with role provenance |
| PATCH | `/users/{id}` | `admin:manage_users` | Update profile / activation |
| POST | `/users/{id}/roles` | `admin:assign_roles` | Grant a role |
| DELETE | `/users/{id}/roles/{role}` | `admin:assign_roles` | Revoke a role (keeps ≥1 role) |
| GET | `/roles` | `admin:manage_users` | Assignable roles |
| GET | `/audit-log` | `admin:view_audit_log` | Filtered, paginated audit events |
| GET | `/audit-log/facets` | `admin:view_audit_log` | Distinct actions/resources/severities |
| GET | `/audit-log/{id}` | `admin:view_audit_log` | Event detail with payload diff |

### Services — `app/services/admin/`
- `AdminUserService` — list/get/update users, assign/revoke roles. Business rules
  live here (never strip the last role; role must exist). Audit-logs every
  mutation with before/after diffs via `AuditService`.
- `AuditQueryService` — read-side for the immutable `AuditEvent` log (filtering,
  pagination, single-event detail, filter facets). The write side stays in
  `AuditService`.
- `AdminStatsService` — live counters; every rate is divide-by-zero safe.

### Schemas — `app/schemas/admin.py`
`UserSummary`, `UserDetail`, `UserListResponse`, `UserUpdateRequest`,
`RoleSummary`, `RoleAssignRequest`, `AuditEventOut`, `AuditEventDetail`,
`AuditListResponse`, `AuditFacets`, `SystemStats`.

### Analytics hardening — `app/services/analytics_service.py`
`_sla_metrics` now returns a real `compliance_rate` (share of period-resolved
tickets that met their resolution target) plus `resolved_with_target` /
`resolved_on_time`; it is `None` when there is nothing to measure so the UI shows
"No data" instead of `NaN%`. `at_risk` / `breached` (open tickets) are retained.

### Testability
Endpoints construct services from `Depends(get_db)`, so API tests patch the
service class on the router module (`app.api.v1.admin.<Service>`) and patch
`AuthService.get_user_permissions` to resolve from the canonical registry — no DB
required. See `backend/tests/api/test_admin.py`.

## Frontend

### Feature module — `src/features/admin/`
- `types.ts` — TS mirror of the admin schemas + analytics types.
- `api.ts` — React Query hooks (`useUsers`, `useUser`, `useRoles`, `useUpdateUser`,
  `useAssignRole`, `useRevokeRole`, `useAuditEvents`, `useAuditEvent`,
  `useAuditFacets`, `useSystemStats`, `useDashboardMetrics`, `useAgentWorkload`).
  Mutations invalidate/patch the relevant query cache.
- `utils.ts` — pure presentation helpers (role labels/variants, `fmtDateTime`).
- `components/badges.tsx` — `RoleBadge`, `SeverityBadge`, `StatusBadge`.

### Shared shell — `src/components/admin/`
- `Breadcrumbs.tsx` — trail with configurable `homeTo` (default `/dashboard`;
  audit pages use `/audit`).
- `PageHeader.tsx` — breadcrumbs + title + description + actions, used on every
  admin page for consistent hierarchy.

### Shell — `src/components/layouts/AdminLayout.tsx`
Brand sidebar (Aditi `--sidebar` token), permission-filtered nav, no cross-workspace
switcher, and a clean account-summary footer with Profile/settings and Sign out.

### Routes (`src/app/App.tsx`)
`/dashboard` (AdminLayout) → Analytics, team-queue, knowledge/*, users, users/:id,
feedback/review. `/audit` (AdminLayout under AuditorRoute) → audit list + `/:eventId`.

## RBAC alignment
Frontend `src/lib/permissions.ts` mirrors the backend registry and now includes
`admin:manage_users` and `admin:assign_roles` (it_admin) so the UI gates actions
the same way the API enforces them. The backend remains the source of truth.
