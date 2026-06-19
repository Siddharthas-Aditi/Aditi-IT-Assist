# Admin Console Redesign — Iteration Log

> Status: in progress. Owner: platform/admin. Last updated: 2026-06-19.

## Goal
Make the full Admin flow production-grade: real backend data everywhere, breadcrumbs,
no profile-switch in the admin shell, working User Management + Audit Logs, hardened
Analytics, consistent enterprise theme, tests + docs.

## Audit (current state)
- 14/16 admin pages already backend-connected (all Knowledge Base subpages, Team Queue,
  Analytics dashboard, Feedback review).
- **Stubs:** `UserManagementPage` ("coming soon"), `AuditLogPage` (placeholder UI, no API).
- **Backend gaps:** no User Management API (models/permissions/service helpers exist),
  `/admin/audit-log` returns empty (TODO), `/admin/stats` returns hardcoded zeros.
- Analytics: `avg_confidence`/`avg_quality` can be `None`/NaN at the edges.
- "Profile switch" = cross-workspace nav links in layout footers (`← Operations View`).
- No breadcrumb component anywhere.

## Decisions
- Full sweep across all admin areas.
- Remove cross-workspace nav from the admin shell; replace footer with clean account area.

## Plan / checklist — all complete
1. [x] Admin shell: removed profile-switch, clean account area, breadcrumb + page-header framework.
2. [x] Backend: User Management API (list/get/update/activate-suspend/assign-revoke role, list roles).
3. [x] Backend: Audit Log query API (+ facets + detail) + real `/admin/stats`.
4. [x] Frontend: User Management list + detail (role mgmt, suspend/reactivate, breadcrumbs).
5. [x] Frontend: Audit Logs list + detail (filters, pagination, payload diff, breadcrumbs).
6. [x] Analytics: real SLA compliance + NaN guards (backend + frontend), refresh, time-range.
7. [x] Team Queue modernized + breadcrumbs on key KB detail/edit/review pages.
8. [x] Visual/theme consistency pass (brand sidebar, PageHeader, StatCards, tables).
9. [x] Tests: backend RBAC/contract (`tests/api/test_admin.py`) + frontend component tests; tsc + lint clean.
10. [x] Docs: admin-console product/architecture/QA + CLAUDE/AGENTS/copilot.

## Iteration 2 — non-admin flows (employee + operations)
Audited the Employee (`/support`) and IT Operations (`/operations`) workspaces.
- **Critical fix:** `TicketWorkspacePage` (`/operations/tickets/:id`) was a placeholder stub —
  the page the admin Team Queue links into. Implemented it for real: backend
  `GET /tickets/{id}` staff endpoint (`TicketService.get_ticket_for_agent`, it_agent+,
  includes internal notes + events) + a full workspace UI (description, AI summary,
  merged activity timeline, add comment w/ internal toggle, assign-to-me, status change),
  breadcrumbs, brand theme.
- **Redesign:** `EmployeeLayout` + `OperationsLayout` rebuilt on the Aditi brand sidebar
  token (were hardcoded white/indigo and slate/emerald), clean account footer, styled
  cross-workspace quick-links.
- **Bug fixes:** `MyTicketsPage` now shows a real error state (was a silent catch →
  misleading "No tickets yet"); both ticket pages moved to `apiRequest` (401/refresh
  handling); `ProfilePage` shows all roles + title-cased, status reflects the signed-in
  user; date rendering is NaN-safe across pages.
- **Theme:** employee pages (MyTickets, Profile, TicketDetail) converted to design tokens.
- **Tests:** `backend/tests/api/test_tickets_staff.py` (RBAC + 404 for the new endpoint).

## Iteration 3 — live-chat handoff flow
- **Root-cause bug (claim failed for every agent):** `SpecialistQueueService.claim`
  built invalid SQL — `Ticket.first_response_at.op("COALESCE")(now)` renders
  `first_response_at COALESCE :param` (COALESCE is a function, not a binary operator),
  so the atomic UPDATE 500'd → the agent saw "error to fetch". Fixed to
  `func.coalesce(Ticket.first_response_at, now)`.
- **Missing employee join:** when a specialist started the live chat, the employee had
  no way in. Added `GET /specialist-chat/active` (`SpecialistChatService.get_active_for_participant`)
  and an employee-side poll in `SupportChatPage` that surfaces a "An IT specialist has
  joined — Join live chat" banner routing to `/support/live-chat/:id`. Completes the
  escalate → claim → start → join → converse → end loop.
- **Tests:** `backend/tests/api/test_specialist_chat_active.py` (auth + no-session path).

## Verification status
- Frontend `tsc --noEmit` and `eslint . --max-warnings=0`: **pass** (executed in sandbox).
- Backend new files + tests: ruff-clean + `py_compile` pass (executed). Full `pytest`/`uv`
  could not run in-sandbox (no project Python interpreter; uv blocked from fetching one).
  Backend tests mirror the proven `tests/api/test_knowledge_admin.py` pattern exactly.
- vitest could not execute in-sandbox (node_modules built for macOS; linux rollup binary
  unavailable, registry unreachable). Tests authored to the existing RTL pattern.

## Conventions
- Backend: routes → services → models; Pydantic v2 schemas; RBAC via `require_permissions`;
  audit-log every high-risk mutation; service classes patchable for tests.
- Frontend: typed API hooks (React Query), `PageHeader` + `Breadcrumbs` on every admin page,
  loading/empty/error states, permission-aware actions.
