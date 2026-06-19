# Admin Console — Product Guide

The Admin Console is the internal operations surface for IT leads, admins, and
(for audit) security auditors. It is purpose-built for IT support operations —
**not** a generic dashboard. Every screen is backed by real APIs; there is no
placeholder or dummy data in the core admin flow.

## Who can use it

| Section | Route | Required access |
|---------|-------|-----------------|
| Analytics | `/dashboard` | it_lead, it_admin |
| Team Queue | `/dashboard/team-queue` | it_lead, it_admin |
| Knowledge Base | `/dashboard/knowledge/*` | it_agent+ (per-action permissions) |
| User Management | `/dashboard/users`, `/dashboard/users/:id` | `admin:manage_users` (it_admin) |
| Audit Logs | `/audit`, `/audit/:eventId` | `admin:view_audit_log` (it_admin, security_auditor) |

The admin shell is **admin-focused**: it no longer offers cross-workspace
"profile switching." The sidebar footer is a clean account summary (name, email,
role) with a menu for Profile & settings and Sign out.

## Sections

### Analytics
Real KPIs over a selectable time range (7 / 30 / 90 days): total tickets, open
tickets, AI resolution rate, SLA compliance, escalation rate, SLA breached/at-risk,
priority and category distributions, and agent workload. Rates that cannot be
computed truthfully render **"No data"** instead of `NaN%`.

### Team Queue
Operational queue of all team tickets with status/priority filters and client-side
search (id, title, category). Each ticket links to the operations workspace
(`/operations/tickets/:id`) where claim / assign / reassign / resolve actions live.

### Knowledge Base
Full governance suite (already production-grade): Articles, Review Queue, Taxonomy,
Indexing, Analytics, Upload, plus article detail/edit, version history, and the
ingestion candidate review/edit flow. Deep pages carry breadcrumbs.

### User Management
List with search, role filter, status filter, and pagination. User detail shows
profile, role assignments (assign/revoke, gated by `admin:assign_roles`), and an
activate/suspend control (gated by `admin:manage_users`). A user always keeps at
least one role. Every mutation is audit-logged.

### Audit Logs
Filterable, paginated trail of security/governance events (severity, action,
actor email, free-text search). Event detail shows actor/context and the
before/after payload diff. Events are written automatically by the services for
high-risk actions (role changes, suspensions, publishing, ingestion, reindex…).

## Navigation conventions
Every sub-page, detail, edit, create, and review view renders a breadcrumb trail
(home icon → section → … → current page). Breadcrumbs complement — never replace —
browser back. See `docs/development/admin-qa-checklist.md` for the QA list.
