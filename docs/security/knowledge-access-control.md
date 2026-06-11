# Knowledge Access Control

> Last updated: 2026-06-11

Authorization is enforced at **two layers**: the API (permission-gated FastAPI
dependencies) and the UI (role-derived gating in `lib/permissions.ts`). The
backend is always the source of truth; the UI only hides what a role may not do.

## Permission codes (`knowledge:*`)

Defined in `backend/app/core/permissions.py` with audit/high-risk metadata.

| Code | Purpose | High-risk | Audited |
|------|---------|:---------:|:-------:|
| `knowledge:read` | Read published KB | | |
| `knowledge:view_internal` | Retrieve internal/unpublished + admin reads | | ✓ |
| `knowledge:submit_feedback` | Submit article feedback | | |
| `knowledge:suggest` | Suggest improvements / draft suggestions | | |
| `knowledge:create` | Create draft articles | | |
| `knowledge:update_own` / `update_all` | Edit articles | | ✓ (all) |
| `knowledge:submit_review` | Submit for review | | ✓ |
| `knowledge:review` | Review / request changes / reject | | ✓ |
| `knowledge:approve` | Approve articles | | ✓ |
| `knowledge:publish` | Publish (agent-retrievable) | ✓ | ✓ |
| `knowledge:archive` | Archive / restore | | ✓ |
| `knowledge:manage_categories` | Manage taxonomy | | ✓ |
| `knowledge:manage_ownership` | Manage ownership groups | | ✓ |
| `knowledge:reindex` | Trigger reindex | | ✓ |
| `knowledge:view_analytics` | View KB analytics | | |
| `knowledge:delete` | Delete article | ✓ | ✓ |

## Role → capability matrix

| Capability | Employee | IT Agent | IT Lead | IT Admin | Auditor |
|------------|:--------:|:--------:|:-------:|:--------:|:-------:|
| Read published | ✓ | ✓ | ✓ | ✓ | ✓ |
| Internal / unpublished read | | ✓ | ✓ | ✓ | ✓ (read-only) |
| Submit feedback | ✓ | ✓ | ✓ | ✓ | |
| Suggest improvements | | ✓ | ✓ | ✓ | |
| Create / edit drafts | | ✓ | ✓ | ✓ | |
| Submit for review | | ✓ | ✓ | ✓ | |
| Review / approve | | | ✓ | ✓ | |
| Publish / archive | | | ✓ | ✓ | |
| Taxonomy / ownership | | | | ✓ | |
| Reindex | | | | ✓ | |
| View analytics | | | ✓ | ✓ | |
| Version & audit history | | ✓ | ✓ | ✓ | ✓ |

(IT Lead inherits Agent; IT Admin inherits Lead — see `get_effective_permissions`.)

## API-level enforcement

- Public read/feedback: `app/api/v1/knowledge.py`.
- Admin/governance: `app/api/v1/knowledge_admin.py`, every route gated by
  `require_permissions(...)`. The **lifecycle transition** endpoint is gated
  coarsely by `knowledge:view_internal`, then enforces the *specific* per-action
  permission inside `KnowledgeManagementService.transition` — so an agent calling
  `publish` receives `403` even though they can reach the endpoint.

## Retrieval boundaries

- **Employee chat is published-only.** `KnowledgeRetrievalService` filters on
  `status == 'published'` and `audience == 'employee'` for employee-facing calls.
- **Internal scope is opt-in** and requires `knowledge:view_internal`; it widens
  the audience set, never bypasses publication for employees.
- Drafts and archived content are never returned to employee chat. Archiving
  removes an article from the retrieval index immediately.

## Audit & traceability

- Every create, update, lifecycle transition, review note, and reindex is logged
  via the central `AuditService` (`resource_type = "knowledge_article"`), with
  old/new status, actor, and severity (publish is `notice`).
- Immutable **version snapshots** provide content history; **review notes** capture
  the human decision trail. Auditors have read-only access to both.

## Data protection notes

- Feedback may contain user-entered text; treat as user data. `user_id` is stored
  for attribution but feedback can be submitted with `was_helpful`/`rating` only.
- Audit payloads are sanitized (`AuditService._sanitize_payload`) to redact secret-
  like keys.

See also: [../security/rbac-matrix.md](rbac-matrix.md),
[../architecture/retrieval-and-indexing.md](../architecture/retrieval-and-indexing.md).
