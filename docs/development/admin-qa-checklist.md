# Admin Console — QA Checklist

Run through this before shipping admin changes. Seeded dev users (see
`scripts/seed_enterprise.py`): `admin@aditi.com / admin123` (it_admin),
`lead@aditi.com / lead123` (it_lead), `auditor@aditi.com / auditor123`
(security_auditor), `employee@aditi.com / employee123`.

## Shell & navigation
- [ ] Admin sidebar shows Analytics, Team Queue, Knowledge Base, User Management,
      Audit Logs; Audit Logs hidden without `admin:view_audit_log`.
- [ ] No "Operations View" / profile-switch link in the admin sidebar.
- [ ] Account footer shows name + email; menu opens with Profile & settings + Sign out.
- [ ] Sign out clears session and redirects to /login.

## Breadcrumbs
- [ ] Every detail/edit/review page shows a breadcrumb trail.
- [ ] Parent crumbs navigate up; current crumb is plain text (`aria-current="page"`).
- [ ] Audit pages' home icon points to `/audit` (not `/dashboard`).

## Analytics
- [ ] Loads without `NaN%`; empty metrics show "No data".
- [ ] Time-range toggle (7/30/90) refetches; Refresh works.
- [ ] Priority/category/workload panels show real data or a clear empty state.

## Team Queue
- [ ] Status + priority filters refetch; search filters the visible list.
- [ ] Ticket cards open the operations workspace; claim/assign/resolve work there.
- [ ] Loading / error / empty states render correctly.

## User Management
- [ ] List: search, role filter, status filter, pagination all work.
- [ ] Detail: profile fields, role assignments, last login render.
- [ ] Assign role / revoke role update immediately (gated by `admin:assign_roles`).
- [ ] Cannot revoke a user's last role (409 surfaced as an error).
- [ ] Suspend / reactivate toggles status (gated by `admin:manage_users`).
- [ ] A lead (no `admin:manage_users`) gets 403 from the users API.

## Audit Logs
- [ ] List loads real events; severity/action/actor/search filters work.
- [ ] Pagination works; empty state only when genuinely empty.
- [ ] Event detail shows actor/context + before/after diff.
- [ ] Auditor and admin can view; agent/employee get 403.

## Automated gates
- [ ] `cd frontend && npx tsc --noEmit` → clean.
- [ ] `cd frontend && npm run lint` (`--max-warnings=0`) → clean.
- [ ] `cd frontend && npm run test` → admin component tests pass.
- [ ] Backend `pytest tests/api/test_admin.py` → RBAC + contract tests pass.
- [ ] Backend `ruff check app` → clean.
