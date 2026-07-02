---
applyTo: "{backend/app/services/admin/**,backend/app/api/v1/admin.py,frontend/src/features/admin/**,frontend/src/components/admin/**,frontend/src/pages/admin/**}"
---
# Admin console instructions

Admin-focused shell (it_lead / it_admin; auditor for audit) — no cross-workspace
"profile switch". Sections: Analytics, Team Queue, Knowledge Base, User Management,
Audit Logs. Full docs: `docs/product/admin-console.md`,
`docs/architecture/admin-console-architecture.md`.

## Backend
- `app/api/v1/admin.py` → `app/services/admin/` (`AdminUserService`, `AuditQueryService`,
  `AdminStatsService`) + `app/schemas/admin.py`. No logic in the route.
- Gate with `require_permissions` (`admin:manage_users`, `admin:assign_roles`,
  `admin:view_audit_log`). **Audit-log every user/role mutation with before/after.**
- Invariant: a user always keeps **≥1 role**. Stats/analytics are real aggregation.

## Frontend
- `features/admin/` (typed React Query hooks, `utils.ts`, `components/badges.tsx`) +
  shared `components/admin/` (`Breadcrumbs`, `PageHeader`). Pure helpers live outside
  component files (react-refresh rule). Breadcrumbs on every detail/edit/review page.
- **Real data only** — no dummy cards. Uncomputable rates → "No data", never `NaN%`.
- Mirror backend permissions in `src/lib/permissions.ts`.

## Tests
- `backend/tests/api/test_admin.py`; frontend `Breadcrumbs.test.tsx`, `badges.test.tsx`.
- Manual: `docs/development/admin-qa-checklist.md`.

Reference: `skills/playbooks/frontend-admin-console.md`,
`skills/playbooks/audit-logging.md`, `agents/dev/frontend-admin-ux.md`.
