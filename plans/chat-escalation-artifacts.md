# Plan: Chat → Ticket → Specialist Escalation Artifacts

> Status: **backend + frontend slice complete; DB/e2e validation pending in Docker**
> owner: Principal Eng / Support Workflow Architect — 2026-06-27

Production-grade, context-preserving handoff from unresolved AI chat to ticketing +
live specialist support. Two linked, immutable artifacts created at escalation time:
a **Transcript Snapshot** and a structured **Escalation Context**.

---

## 1. Current-state audit (what exists vs. what's missing)

### Root cause
The AI chat transcript is **never persisted**. `ChatService` keeps all session state
in module-level in-memory dicts (`_sessions`, `_session_tickets`, `_waiting_since` in
`backend/app/services/agents/chat_service.py:32-44`) that die on process restart. The
DB schema already has the right *bones* but they are starved of data:

| Asset | Schema exists? | Populated at runtime? |
|-------|----------------|-----------------------|
| `tickets.session_id` FK → `support_sessions` | ✅ | ❌ always NULL (explicit note `chat_service.py:561-565`) |
| `specialist_chat_sessions.ai_session_id` FK | ✅ | ❌ never set |
| `HandoffPackage` typed schema (rich) | ✅ | ⚠️ rebuilt on the fly from the always-empty `_sessions` lookup → specialist sees only title/ai_summary |
| Immutable AI transcript snapshot | ❌ | ❌ |
| Structured escalation-context record | ❌ | ❌ (flattened into ticket `description`/`ai_summary` text only) |
| KB gap tags | ❌ | ⚠️ `mismatch_reason` computed, logged, not stored as tags |
| Resolution comparison (AI vs specialist) | ❌ | ❌ |

### Where escalation happens today
1. `workflows/nodes/resolution.py` exhausts grounded steps → sets `escalation_reason`.
2. `workflows/nodes/escalation.py::_build_handoff_summary` builds an **in-memory**
   handoff dict (last-10-turn conversation, steps_attempted, diagnostic_summary).
3. `workflows/nodes/ticketing.py::ticket_node` builds a `ticket_draft` and **offers** —
   side-effect free, does NOT persist.
4. `chat_service.py::_handle_ticketing` → `_persist_and_queue` creates the ticket on
   explicit confirmation, calls `TicketService.request_live_agent`, caches a `TicketRef`
   in memory. **`ticket.session_id` left NULL; no structured artifacts created.**
5. Specialist queue (`specialist_queue_service.py`) is a view over `tickets`
   (`source='chat'`); `build_handoff_package` tries `_sessions.get(str(ticket.session_id))`
   which is always `None` → empty package.

### Frontend
- `pages/employee/SupportChatPage.tsx` already shows an escalation offer + a
  "Ticket created" card + waiting/joined banners (raw indigo styling, not Aditi tokens;
  only `user`/`assistant` roles).
- `pages/operations/LiveQueuePage.tsx` discards the `handoff_package` from `claim()` and
  navigates straight to live chat — the rich package is **never rendered**.
- `lib/api.ts` defines the full `HandoffPackage` type + `getHandoffPackage()` but **no
  component renders it**. No collapsible transcript, no summary-first specialist view.

---

## 2. Design — chosen approach

**Snapshot-at-escalation** (decided with stakeholder): leave the broader in-memory chat
refactor as a separate follow-up; at escalation time, capture the in-memory transcript
into two new immutable, linked records.

### Linked artifact model
```
            ┌────────────────────┐
            │      tickets        │  (parent operational object)
            └─────────┬──────────┘
                      │ 1
          ┌───────────┴─────────────┐
          │ 1                       │ 1
┌─────────▼──────────┐   ┌──────────▼─────────────┐
│ transcript_snapshots│◄──│  escalation_contexts   │
│ (immutable ordered  │ 1 │ (structured handoff +  │
│  AI↔employee msgs)  │   │  resolution comparison)│
└─────────────────────┘   └────────────────────────┘
```
- `escalation_contexts.ticket_id` (unique) and `transcript_snapshot_id` (FK) are the
  links. We do **not** set `tickets.session_id` (FK → unused `support_sessions`); the
  string chat-session id lives on both new records as `chat_session_id`.
- Post-escalation specialist messages stay in the separate `specialist_chat_messages`
  table — the AI-leg snapshot is never mixed with them.

### New components
| Layer | File | Purpose |
|-------|------|---------|
| Models | `app/models/escalation.py` | `TranscriptSnapshot`, `EscalationContext` |
| Migration | `alembic/versions/009_chat_escalation_artifacts.py` | tables + indexes |
| Vocabulary | `app/services/agents/kb_gap_tags.py` | typed KB-gap tags + pure derivation |
| Schemas | `app/schemas/escalation.py` | DTOs incl. `SpecialistHandoffView` |
| Service | `app/services/escalation_service.py` | create artifacts, build view, record comparison |
| Wiring | `chat_service.py`, `specialist_queue_service.py`, `specialist_queue.py` API | create + consume |
| Frontend | `features/specialist-chat/`, `features/chat/` | summary-first + collapsible transcript, role bubbles, confirmation |

### Immutability contract
`TranscriptSnapshot` is write-once: the service exposes no update path, the messages
JSONB is captured at creation, and later session mutations cannot reach it (it's a copy,
not a reference). Documented in the model docstring; mirrors the existing
`specialist_chat_messages` "immutable by design" convention.

---

## 3. Iteration log

- **Iter 0 — audit (done).** Mapped backend + frontend, identified in-memory root cause,
  confirmed schema bones + starved data. Stakeholder chose snapshot-at-escalation,
  backend-first, code-complete + checklist.
- **Iter 1 — backend data layer (done).** models + migration 009 + KB-gap vocab + schemas.
- **Iter 2 — service + wiring (done).** EscalationService; ChatService creates artifacts atomically; queue `build_handoff_package` reads persisted context; resolve() records comparison; 3 new API endpoints.
- **Iter 3 — tests (done).** `test_kb_gap_tags.py`, `test_escalation_artifacts.py` (extract/immutability/handoff-view/comparison/wiring), `test_specialist_queue_handoff.py` (API+RBAC), `HandoffContextPanel.test.tsx`.
- **Iter 4 — frontend (done).** `HandoffContextPanel` (summary-first + collapsible transcript + role bubbles) in `LiveChatPage`; breadcrumbs; typed API; employee confirmation message.
- **Iter 5 — docs (done).** 5 new docs + CLAUDE.md + AGENTS.md + copilot-instructions.
- **Iter 6 — DB/e2e validation (pending in Docker).** alembic upgrade, full pytest, vitest — see QA checklist. Sandbox verified: py_compile, pure-logic unit checks, frontend `tsc` + `eslint`.

## 4. Validation checklist (run in Docker — see docs/development/chat-escalation-qa-checklist.md)
- `docker compose exec backend uv run alembic upgrade head`
- `make test-backend` (new: `test_escalation_artifacts.py`, `test_kb_gap_tags.py`, `test_chat_escalation_e2e.py`)
- `make test-frontend`
- `make lint`
