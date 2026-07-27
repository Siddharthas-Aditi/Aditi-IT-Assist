# IT Ticket Close + Cascading Categories

**Date:** 2026-07-27  
**Status:** Approved design — ready for implementation plan  
**Scope:** IT-only ticket close with mandatory classification, cascading Category →
Sub-Category → Item hierarchy managed by IT admin, and a Freshservice-style Properties
panel on the existing Operations ticket workspace.

---

## 1. Problem

Today, tickets can reach `closed` through a generic status update on the Operations
ticket workspace, without forcing resolution notes or a governed classification. There
is no admin-managed cascading category vocabulary comparable to Freshservice
(Category → Sub-Category → Item). Employees must never close tickets; only IT staff
may close, and only after completing a mandatory close form.

Partial backend scaffolding already exists (migration `014`, `TicketCategory` model,
`TicketCategoryService`, `ticket_categories` API module, `TicketCloseRequest` schema)
but is incomplete: the category router is not mounted, `TicketService.close_ticket` is
missing, status-update can still set `closed`, and there is no Close UI / Manage
Category / Properties panel.

### Goals

1. **IT-only close** — `it_agent` / `it_lead` / `it_admin` can close; employees never can.
2. **Mandatory close form** — resolution notes + Category + Sub-Category + Item; Item
   is always required (even if a sub-category has no items configured → close blocked).
3. **Cascading dropdowns** — parent change clears children; server validates parent chain.
4. **Admin-managed vocabulary** — only `it_admin` creates/updates/deletes category options.
5. **Ticket workspace Properties panel** — IT can update classification and lifecycle
   fields without closing; Close is a separate header action + modal.
6. **Starter seed tree** — practical L1/L2/L3 data so Close works on day one.

### Non-goals

- Freshservice fields we do not model today: Group, Department, Location.
- WebSocket ticket updates (keep HTTP).
- Auto-learning or AI-authored category trees.
- Changing the employee ticket detail experience beyond “cannot close”.
- Drag-and-drop polish beyond basic reorder (up/down or ordered list is enough for v1).

---

## 2. Design decisions (agreed)

| Area | Decision |
|------|----------|
| Close UX | Modal on ticket workspace (Approach A) |
| Required on close | Resolution notes + Category + Sub-Category + Item |
| Empty Item list | Item stays required — Close blocked until admin adds Items (Option A) |
| Who can close | Any IT staff (`it_agent`, `it_lead`, `it_admin`) |
| Manage Category | Admin Console `/dashboard/ticket-categories`, `it_admin` only |
| Seed | Starter tree with ≥1 Item under every seeded Sub-Category |
| Scope | Close modal + Manage Category + Properties panel on existing workspace |
| Architecture | Extend `/operations/tickets/:id` (`TicketWorkspacePage`), not a new detail route |
| Close bypass | `POST /tickets/{id}/status` rejects `closed`; only `POST /tickets/{id}/close` |

---

## 3. Architecture

### 3.1 Category hierarchy

```
ticket_categories
  level 1  Category        (e.g. Incident, Service Requests)
  level 2  Sub-Category    (parent = L1)
  level 3  Item            (parent = L2)
```

Rules (service-enforced + FK `ON DELETE RESTRICT`):

- Level ∈ {1, 2, 3}; L2/L3 require parent exactly one level above.
- Unique name within `(level, parent_id)` scope.
- Cannot delete a node that still has children (active or inactive).
- Inactive nodes are hidden from Close/Properties cascading dropdowns (`active_only=true`).
- Deactivating a parent effectively hides its subtree from active lists.

Ticket stores denormalized string names at close/update time:

- `tickets.category` (L1 name)
- `tickets.subcategory` (L2 name)
- `tickets.item` (L3 name)
- `tickets.ticket_type` (separate Type tag: Incident / Service Request / Problem / Change / Other)

Names are stored (not FKs) so historical tickets remain readable if an admin renames or
deactivates a node later. Close/update validates the selected names against the **active**
tree and the parent/child chain at write time.

### 3.2 Close gate

```
IT clicks Close
  → CloseTicketModal
  → POST /tickets/{id}/close
       body: { resolution_notes, category, subcategory, item, close_notes? }
  → TicketService.close_ticket
       1. Actor must be IT staff
       2. Ticket not already closed
       3. resolution_notes non-empty (trimmed)
       4. Validate L1→L2→L3 active chain; Item always required
       5. Persist classification + notes; status=closed; closed_at; closed_by
       6. Emit ticket event + audit
```

`POST /tickets/{id}/status` with `status=closed` returns **409** with detail directing
clients to the close endpoint. UI removes `closed` from the Properties status dropdown.

### 3.3 Properties panel (non-closing updates)

Upgrade `/operations/tickets/:id` to a two-column layout: main content left; Properties
rail right. Header actions include **Close** (opens modal; hidden when already closed),
Assign/Claim, and Reopen when terminal.

| Field | Editable | Notes |
|-------|----------|-------|
| Priority | Yes | Existing enum |
| Status | Yes | All lifecycle statuses **except** `closed` |
| Source | No | Set at create |
| Type | Yes | `ticket_type` |
| Urgency / Impact | Yes | Existing fields |
| Agent | No (display) | Assign via header action |
| Category / Sub-Category / Item | Yes | Cascading; Item required when saving classification |
| Resolution notes | Yes | Draft; Close still requires non-empty notes |

Out of scope: Group, Department, Location.

`PATCH /tickets/{id}` (IT staff) accepts partial updates:

- `priority`, `urgency`, `impact`, `ticket_type`
- `category`, `subcategory`, `item` (if any of the three is provided, validate cascade;
  Item required whenever Category/Sub-Category are being set)
- `status` — allowed values exclude `closed`
- `resolution_notes` — draft allowed; Close still requires non-empty notes at close time

Assignment stays on the existing **Assign / Claim** header actions and
`POST /tickets/{id}/assign` — the Properties panel shows Agent as read-only display
(name/id) to avoid two write paths.

Source remains read-only on the panel (set at ticket create).

**Note on Type vs Category:** `ticket_type` is a coarse tag (Incident / Service Request /
…). Category L1 is the admin-managed hierarchy root and may reuse similar labels
(e.g. L1 name “Incident”). They are independent fields; Close does not require Type.

### 3.4 Manage Category (admin)

Route: `/dashboard/ticket-categories`  
Nav: Admin Console, visible only when `user.role === 'it_admin'` (same pattern as User
Management). Route guard: admin-only (stricter than lead-level `AdminRoute` if needed —
use an `it_admin`-only guard or inline role check).

UI:

1. Tree editor — list L1; expand to L2/L3; add / rename / activate-deactivate / delete leaf.
2. Cascading preview — dependent dropdowns mirroring Freshservice “Dropdown Choices –
   Preview” so admins can verify the hierarchy agents will see on Close.

API (mount under `/api/v1/ticket-categories`):

| Method | Path | Who |
|--------|------|-----|
| GET | `/` or `/tree` | IT staff read |
| GET | `?level=&parent_id=` | IT staff (cascading) |
| POST | `/` | `it_admin` |
| PATCH | `/{id}` | `it_admin` |
| DELETE | `/{id}` | `it_admin` (409 if children) |
| POST | `/reorder` | `it_admin` — expose `TicketCategoryService.reorder` if not already routed |

### 3.5 Frontend composition

Split `TicketWorkspacePage` into focused pieces (keep page orchestration thin):

| Component | Responsibility |
|-----------|----------------|
| `TicketWorkspacePage` | Load ticket, header actions, layout |
| `TicketPropertiesPanel` | Right-rail form + Update |
| `CloseTicketModal` | Mandatory close form + cascade |
| `CategoryCascadeFields` | Shared L1→L2→L3 selects (Properties + Close) |
| `TicketCategoriesPage` | Admin manage + preview |

API client: extend `frontend/src/lib/api.ts` with `ticketsApi.close`, `ticketsApi.update`,
and `ticketCategoriesApi` (tree / flat / CRUD).

### 3.6 Seed starter tree

Seeded idempotently by `scripts/seed_enterprise.py` (or a dedicated seed helper it calls).
Every seeded L2 must have ≥1 active L3 Item.

Practical starter (extendable by admin; not a full Freshservice dump):

**Incident**

| Sub-Category | Item(s) |
|--------------|---------|
| System Login Issue | Password Reset, Account Locked |
| Network Connectivity | VPN, Wi-Fi, DNS |
| O365 Apps | Outlook, Teams, OneDrive |
| Laptop Not Booting | Hardware Diagnosis |
| Zoom Issue | Audio, Video, Sign-in |
| Laptop Performance Issue | Slow Performance |

**Service Requests**

| Sub-Category | Item(s) |
|--------------|---------|
| DL Creation | New Distribution List |
| Application Access | Slack, Webex, Zoom |
| New Joiner Credential Creation | Standard Onboarding |
| Shared Mailbox Access | Grant Access |
| Hardware Request | Laptop, Monitor, Headset |
| License Request | Software License |

**Also seed L1 with one placeholder Sub + Item each:** `SPAM Email`, `Others`, `Freshworks`
(so Level-1 options from the reference screenshots exist and remain closeable).

---

## 4. Error handling

| Condition | HTTP | Behavior |
|-----------|------|----------|
| Missing/blank resolution notes on close | 400 | Field error |
| Missing category / subcategory / item on close | 400 | Field error |
| Names not in active tree or wrong parent chain | 400 | “Invalid category cascade” |
| Sub-category has zero active items | 400 | “No items configured for this sub-category; ask an IT admin to add items” |
| Ticket already closed | 409 | Idempotent-safe reject |
| Non-IT close attempt | 403 | |
| Employee any close path | 403 | |
| `status` update to `closed` | 409 | “Use POST /tickets/{id}/close” |
| Category delete with children | 409 | Existing message |
| Non-admin category write | 403 | |

Frontend: Close Confirm disabled until all required fields valid; show inline errors from API.

---

## 5. Permissions matrix

| Action | employee | it_agent | it_lead | it_admin |
|--------|----------|----------|---------|----------|
| View ticket (own) | ✅ | ✅ | ✅ | ✅ |
| View any ticket (ops) | ❌ | ✅ | ✅ | ✅ |
| Update properties | ❌ | ✅ | ✅ | ✅ |
| Close ticket | ❌ | ✅ | ✅ | ✅ |
| Read category tree | ❌ | ✅ | ✅ | ✅ |
| Manage categories | ❌ | ❌ | ❌ | ✅ |

---

## 6. Testing

**Backend**

- `close_ticket` requires notes + L1/L2/L3; rejects invalid cascade; rejects empty-item parent.
- `update_status(..., "closed")` raises / API returns 409.
- Employee cannot close (403).
- Category CRUD: admin ok; agent write 403; delete-with-children 409.
- Cascade list by `parent_id` returns only children of that parent.

**Frontend**

- Close modal: submit disabled until required fields filled; changing L1 clears L2/Item.
- Status dropdown does not offer `closed`.
- Manage Category nav/page hidden for non-`it_admin`.
- Properties Update does not set status to closed.

---

## 7. Implementation notes (WIP to finish)

Already present (reuse, do not rewrite):

- `backend/alembic/versions/014_ticket_categories_and_close_fields.py`
- `TicketCategory` model + ticket columns `item`, `ticket_type`, `close_notes`, `closed_by`
- `TicketCategoryService` + `backend/app/api/v1/ticket_categories.py` (mount + reorder if missing)
- `TicketCloseRequest` / `TicketUpdateRequest` schemas in `tickets.py` (wire endpoints)

Must add/complete:

- Mount category router in `api/v1/router.py`
- `TicketService.close_ticket` + cascade validation helper
- Block closed via `update_status`
- Extend `_ticket_to_response` with new fields
- Seed starter tree
- Frontend: Properties panel, Close modal, Admin Manage Category page + route/nav
- Tests + short product/architecture doc touch (`memory/domain-model.md`)

---

## 8. Success criteria

1. An IT agent cannot close a ticket without resolution notes and a full Category →
   Sub-Category → Item selection.
2. An employee has no Close affordance and receives 403 if calling the close API.
3. Setting status to `closed` via the generic status API fails.
4. Only `it_admin` can add/edit/delete category options; agents still see cascading options.
5. Seeded tree allows closing immediately after migrate + seed.
6. Ticket workspace shows a Properties rail with Update, and a Close button that opens
   the mandatory modal.
`)