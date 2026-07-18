# Reopened Tracking + Gap-Closure (D) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reopen action (event-derived, makes C1's Reopened column live) + complete status-change event logging, then close the carried-forward review follow-ups and retire dead code.

**Architecture:** Reopen is a state-guarded, RBAC-gated `TicketService` method + endpoint that logs a `status_changed` event; the specialist-queue paths gain the same event logging. The rest are targeted, independent fixes + dead-code deletions, each behind existing patterns.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy / pytest / Ruff (backend); React 18 / TypeScript / Vitest / ESLint (frontend).

## Global Constraints

- Backend line ≤100; `cd backend && uv run ruff check . && uv run ruff format --check .` clean. Frontend strict TS no `any`; `npm run lint` (max-warnings=0) + `npm run typecheck` clean.
- Reopen is RBAC-gated (`ticket:reopen`) + state-guarded (only from resolved/closed). No new column (event-derived — C1 already derives Reopened from `status_changed` events).
- Dead-code deletions must be grep-verified zero-reference first; full suites stay green.
- KB subcategory fixes must not break grounding/retrieval evals; the new consistency test is the guard; generic/monolithic articles are explicitly exempted (forcing a wrong subtype would create harmful false subtype-matches).
- Run backend cmds from `backend/` via `uv`; frontend from `frontend/` via `npm`.

---

### Task 1: Reopen action + complete status-change event logging (backend)

**Files:**
- Modify: `backend/app/services/ticket_service.py` (`reopen_ticket` method)
- Modify: `backend/app/api/v1/tickets.py` (`POST /{ticket_id}/reopen`)
- Modify: `backend/app/services/specialist_queue_service.py` (`release`/`resolve` log `status_changed`)
- Test: `backend/tests/api/test_ticket_reopen.py` (create), extend `backend/tests/unit/` for queue events

**Interfaces:**
- Consumes: `TicketService._add_event(ticket_id, actor_id, event_type, description, old_value=, new_value=)`, `require_permissions`, `P.TICKET_REOPEN` (`"ticket:reopen"`).
- Produces: `TicketService.reopen_ticket(ticket_id, actor, comment=None) -> Ticket`; `POST /tickets/{id}/reopen`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/api/test_ticket_reopen.py` following `backend/tests/api/test_admin.py`'s authed-client + role fixtures. Assert: reopening a resolved ticket returns 200 + status is active; a user without `ticket:reopen` → 403; reopening a non-resolved (e.g. `in_progress`) ticket → 409/400. Also add a unit test asserting `reopen_ticket` writes a `status_changed` `TicketEvent` (old_value=resolved) and clears `resolved_at`. (These run against the real test DB; seed a ticket via the ticket service.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/api/test_ticket_reopen.py -v`
Expected: FAIL — endpoint/method missing.

- [ ] **Step 3: Add `reopen_ticket`**

In `backend/app/services/ticket_service.py`, add (mirroring `update_status` at L117-151):

```python
    async def reopen_ticket(self, ticket_id: uuid.UUID, actor: User,
                            comment: str | None = None) -> Ticket:
        """Reopen a resolved/closed ticket back to active work.

        Logs a status_changed event (what the specialist report derives
        'reopened' from) and clears the resolution/closure timestamps.
        """
        ticket = await self.repo.get(ticket_id)
        if ticket is None:
            raise ValueError("Ticket not found")
        if ticket.status not in ("resolved", "closed"):
            raise ValueError(f"Cannot reopen a ticket in status '{ticket.status}'")
        old_status = ticket.status
        ticket.status = "in_progress"
        ticket.resolved_at = None
        ticket.closed_at = None
        await self._add_event(
            ticket_id, actor.id, "status_changed",
            f"Status changed from {old_status} to in_progress (reopened)",
            old_value=old_status, new_value="in_progress",
        )
        if comment:
            await self._add_event(ticket_id, actor.id, "comment", comment)
        await self.db.commit()
        await self.db.refresh(ticket)
        return ticket
```
Confirm `self.repo.get` / commit pattern matches the surrounding methods (read `update_status` + the repo usage; adapt if the service uses a different getter).

- [ ] **Step 4: Add the endpoint**

In `backend/app/api/v1/tickets.py`, add (mirroring `update_ticket_status` at L252-267; use permission gating):

```python
from app.core.permissions import Permission as P  # if not already imported; else use the existing import
from app.services.auth.dependencies import require_permissions

ReopenUser = Annotated[User, Depends(require_permissions("ticket:reopen"))]


@router.post("/{ticket_id}/reopen", response_model=TicketResponse)
async def reopen_ticket(
    ticket_id: str,
    reopen_user: ReopenUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    data: TicketReopenRequest | None = None,
) -> TicketResponse:
    service = TicketService(db)
    try:
        ticket = await service.reopen_ticket(
            uuid.UUID(ticket_id), reopen_user, comment=(data.comment if data else None)
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _ticket_to_response(ticket)
```
Add a `TicketReopenRequest(BaseModel)` with `comment: str | None = None` near the other request schemas (L22-78). Match the real permission-dependency import style in this file (read the top imports; if `require_permissions` isn't imported, add it; confirm `P.TICKET_REOPEN` constant name — it's `"ticket:reopen"`).

- [ ] **Step 5: Log status_changed in queue release/resolve**

In `backend/app/services/specialist_queue_service.py`:
- In `release()` (~L212-229), before/after setting `ticket.status = "triaged"`, write an event. This service has no `_add_event`; instantiate one: `from app.services.ticket_service import TicketService` then `await TicketService(self.db)._add_event(ticket.id, by_user.id, "status_changed", f"Status changed from {old} to triaged", old_value=old, new_value="triaged")` (capture `old = ticket.status` before mutating). Do the same in `resolve()` (~L252-255) with `new_value="resolved"`.
- Add/extend a unit test asserting both write a `status_changed` event. (If a direct `_add_event` call feels wrong, replicate the `TicketEvent(...)` insert inline — but reuse is preferred.)

- [ ] **Step 6: Run tests + lint + commit**

Run: `cd backend && uv run pytest tests/api/test_ticket_reopen.py tests/unit/test_specialist_queue*.py -v && uv run ruff check app/services/ticket_service.py app/api/v1/tickets.py app/services/specialist_queue_service.py && uv run ruff format --check app/services/ticket_service.py app/api/v1/tickets.py app/services/specialist_queue_service.py`
Expected: PASS + clean.
```bash
git add backend/app/services/ticket_service.py backend/app/api/v1/tickets.py backend/app/services/specialist_queue_service.py backend/tests/api/test_ticket_reopen.py backend/tests/unit
git commit -m "feat(tickets): reopen action + status_changed events on queue release/resolve"
```

---

### Task 2: Reopen button (frontend)

**Files:**
- Read then Modify: the ticket detail page (find it — `frontend/src/pages/**/TicketDetailPage.tsx`) + its API layer
- Modify: `frontend/src/lib/permissions.ts` if a reopen gate helper is needed
- Test: co-located test

**Interfaces:** Produces a Reopen button on the ticket detail page (it_agent+ with `ticket:reopen`), calling `POST /tickets/{id}/reopen`, shown only when the ticket is resolved/closed.

- [ ] **Step 1: Read the page + API pattern**

Read the ticket detail page + the ticket API client (`frontend/src/lib/api.ts` ticket calls). Find how status/assign actions are triggered + how permissions gate buttons (`hasPermission`/role helpers in `permissions.ts`).

- [ ] **Step 2: Write the failing test**

Add a test: given a resolved ticket + a user with reopen permission, the Reopen button renders and clicking it calls the reopen API (mock it); given a non-resolved ticket or a user without permission, no button. Match the real component props.

- [ ] **Step 3: Implement**

Add a `reopenTicket(id, comment?)` API call + a Reopen button on the detail page, gated on `ticket.status in (resolved, closed)` AND the user having `ticket:reopen` (mirror backend). Invalidate the ticket query on success. No `any`.

- [ ] **Step 4: Run test + gates + commit**

Run: `cd frontend && npx vitest run <the new test> && npm run lint && npm run typecheck`
```bash
git add frontend/src
git commit -m "feat(tickets): reopen button on ticket detail (gated on ticket:reopen)"
```

---

### Task 3: KB subcategory consistency (test + fixes)

**Files:**
- Modify: `backend/app/knowledge_base/structured_seed.py` (fix specific violators)
- Test: `backend/tests/unit/test_kb_subcategory_consistency.py` (create)

**Interfaces:** Produces a test asserting every seeded article's `subcategory` ∈ `known_subtypes(category)` OR its slug is in a documented `GENERIC_EXEMPT` set; and corrected subcategories for the mappable violators.

- [ ] **Step 1: Write the consistency test**

Create `backend/tests/unit/test_kb_subcategory_consistency.py`:

```python
"""D: every seeded article's subcategory is a known subtype for its category,
except a small documented set of intentionally-generic/fallback articles."""

from app.knowledge_base.structured_seed import ARTICLES
from app.services.agents.subtype_classifier import known_subtypes

# Intentionally-generic / monolithic / cross-category fallback articles that
# should NOT force a (wrong) subtype match — documented exemptions.
GENERIC_EXEMPT = {
    "aditi-email-outlook-issues",
    "outlook-general-troubleshooting",
    "email-alias-shared-mailbox",
    "alias-shared-mailbox-access",
    "alias-update-add-remove",
    "network-no-internet",
    "hardware-peripheral-not-working",
    "software-installation-or-crash",
}


def test_article_subcategories_are_known_subtypes_or_exempt():
    bad = []
    for art in ARTICLES:
        cat = art.get("category")
        sub = art.get("subcategory")
        subs = known_subtypes(cat)
        if not subs:  # category has no classifier rules → nothing to enforce
            continue
        if art["slug"] in GENERIC_EXEMPT:
            continue
        if sub not in subs:
            bad.append((art["slug"], cat, sub))
    assert not bad, f"articles with unknown subcategory: {bad}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_kb_subcategory_consistency.py -v`
Expected: FAIL — lists the specific (non-exempt) violators.

- [ ] **Step 3: Fix the mappable violators**

In `backend/app/knowledge_base/structured_seed.py`, change these `subcategory` values (apply in BOTH `ARTICLES` and `_YAML_ARTICLES` where the slug appears):

| slug | new subcategory |
|---|---|
| outlook-not-receiving-or-slow | `not-receiving-emails` |
| zoom-no-audio-or-video | `no-audio` |
| zoom-audio-issues | `no-audio` |
| zoom-sign-in-issues | `sign-in-issue` |
| vpn-disconnects-frequently | `vpn-not-connecting` |
| intune-device-not-compliant | `non-compliant` |
| account-locked-or-password-reset | `account-locked` |
| new-joiner-onboarding-it | `new-joiner-setup` |
| ruddr-account-access-issues | `access-denied-app` |
| license-tool-access-request | `license-request` |

(The `GENERIC_EXEMPT` slugs are left as-is by design.) Verify each new value is in `known_subtypes(category)` for that article's category (e.g. `no-audio` ∈ zoom rules; `new-joiner-setup`/`access-denied-app`/`license-request` ∈ `_ACCESS_RULES` which `software/other` maps to).

- [ ] **Step 4: Run consistency + grounding regressions + commit**

Run: `cd backend && uv run pytest tests/unit/test_kb_subcategory_consistency.py tests/unit/test_grounding.py tests/unit/test_subtype_classifier.py tests/unit/test_retrieval_eval.py tests/unit/test_seed_grounding_consistency.py -v`
Expected: PASS (consistency passes; no grounding regressions).
```bash
git add backend/app/knowledge_base/structured_seed.py backend/tests/unit/test_kb_subcategory_consistency.py
git commit -m "fix(kb): correct article subcategories to known subtypes; add consistency test"
```

---

### Task 4: Small review follow-ups (triage keywords + web-research mapping + exporter parity)

**Files:**
- Modify: `backend/app/workflows/nodes/triage.py` (windows-update keywords)
- Modify: `backend/app/services/agents/chat_service.py` (`_maybe_run_web_research` specialist mapping)
- Modify: `backend/app/services/reporting/exporters.py` (sanitize only strings in csv/pdf)
- Test: extend `test_triage_categories.py`, `test_web_research_trigger.py`, `test_report_exporters.py`

**Interfaces:** three independent behavior-preserving/correctness fixes.

- [ ] **Step 1: Triage keyword alignment**

In `_keyword_classify`'s windows-update branch (`triage.py` ~L1475-1484), add the 4 missing keywords so it matches `_WINDOWS_UPDATE_RULES`: `"won't update"`, `"update not installing"`, `"stuck installing update"`, `"update loop"`. Extend `test_triage_categories.py` asserting `"windows won't update"` and `"update loop"` → `software/windows-update`, and `"update my password"` still → `access/permissions`.

- [ ] **Step 2: Web-research specialist mapping**

In `ChatService._maybe_run_web_research`, when the routed specialist name isn't a valid registry name, resolve it via `find_specialist_for(category=state.get("issue_category") or diag.get("issue_category"))` and use its `.name` (still safe no-op if that returns None). Import `find_specialist_for` from `app.services.agents.registry`. Extend `test_web_research_trigger.py` with a case where only `issue_category` (e.g. `email/outlook`) is set and assert the research agent is called with `specialist_name="outlook"`.

- [ ] **Step 3: Exporter sanitize parity**

In `exporters.py`, make `to_csv`/`to_pdf` route only `str` cell values through `_sanitize` (numbers pass through untouched), matching `to_xlsx`. Extend `test_report_exporters.py`: a row with a negative number (construct a `SpecialistReportRow` with `avg_resolution_hours=-1.0`) is NOT quote-prefixed in CSV, while a formula-injection string still is.

- [ ] **Step 4: Run tests + lint + commit**

Run: `cd backend && uv run pytest tests/unit/test_triage_categories.py tests/unit/test_web_research_trigger.py tests/unit/test_report_exporters.py -v && uv run ruff check app/workflows/nodes/triage.py app/services/agents/chat_service.py app/services/reporting/exporters.py && uv run ruff format --check app/workflows/nodes/triage.py app/services/agents/chat_service.py app/services/reporting/exporters.py`
```bash
git add backend/app/workflows/nodes/triage.py backend/app/services/agents/chat_service.py backend/app/services/reporting/exporters.py backend/tests/unit/test_triage_categories.py backend/tests/unit/test_web_research_trigger.py backend/tests/unit/test_report_exporters.py
git commit -m "fix: triage windows-update keywords; web-research specialist mapping; exporter sanitize parity"
```

---

### Task 5: Dead-code removal

**Files:**
- Delete: `backend/app/models/models.py`
- Modify: `backend/app/services/web_research.py` (drop the `WebSearchService()` default) + delete the legacy `WebSearchService` class from `backend/app/services/web_search_service.py`
- Delete (frontend): `frontend/src/pages/ChatPage.tsx`, `frontend/src/features/chat/ChatBubble.tsx`(+test), `ChatPanel.tsx`, `QuickReplies.tsx`, `frontend/src/stores/chat-store.ts` — **only after grep-confirming zero references**

**Interfaces:** removes confirmed-dead code; suites stay green.

- [ ] **Step 1: Re-verify zero references (do NOT skip)**

Run each and confirm empty (excluding the file itself + its own tests):
```
cd backend && grep -rn "app.models.models\|from app.models import models" app/ scripts/ alembic/
grep -rn "WebSearchService" app/ tests/    # note remaining refs
cd ../frontend && grep -rn "ChatPage\|from '@/features/chat'\|features/chat'" src/ --include=*.tsx --include=*.ts | grep -v "features/chat/"
grep -rn "chat-store\|stores/chat" src/ | grep -v "stores/chat-store"
```
For `features/chat/`: `ChatBubble`/`ChatPanel`/`QuickReplies` are used only by `ChatPage`; other components in that dir (e.g. `MessageFeedbackControls`, `WelcomeCategories`) ARE used by `SupportChatPage` — **delete only the three dead components + ChatPage + chat-store**, not the whole dir. Verify `chat-store` has no other importer before deleting.

- [ ] **Step 2: Backend deletions**

Delete `app/models/models.py`. In `web_research.py`, change `self.search = search or WebSearchService()` so it no longer references the legacy class — either require `search` (raise if None) or default to `get_web_search_provider()`. Then delete the `WebSearchService` class from `web_search_service.py` (keep `DomainTrust`, `WebSearchResult`, the trust helpers, the providers, and `get_web_search_provider`). Update any test that did `ControlledWebResearchAgent()` no-arg or referenced `WebSearchService` to pass a fake provider instead.

- [ ] **Step 3: Frontend deletions**

Delete the confirmed-dead files. Remove any now-dangling exports from `frontend/src/features/chat/index.ts` (only the deleted components).

- [ ] **Step 4: Full suites (deletions must not break anything)**

Run: `cd backend && uv run ruff check . && uv run pytest -q` and `cd frontend && npm run lint && npm run typecheck && npx vitest run`
Expected: green. Fix any dangling import surfaced (that's the point of running full suites here).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove dead code (models.py scaffold, legacy WebSearchService, unrouted chat module)"
```

---

### Task 6: Full gate + final whole-branch review

- [ ] **Step 1: Full backend + frontend gate**

Run: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest -q` and `cd frontend && npm run lint && npm run typecheck && npx vitest run`
Expected: all green. Record counts.

- [ ] **Step 2: Reopen→report end-to-end sanity**

Confirm (via the Task 1 test that reopens a ticket + the C1 report test) that a reopen increments the report's Reopened count — closing the C1 loop.

- [ ] **Step 3: Hand back to the controller for the final whole-branch (A–D) review + integration decision.**

---

## Self-Review

**Spec coverage:**
- Reopen action + queue events (spec §1,§2) → Task 1; frontend button → Task 2. ✓
- KB consistency test + fixes, generic exemptions (spec §3) → Task 3. ✓
- Triage keywords (spec §4), web-research mapping (spec §5), exporter parity (spec §7) → Task 4. ✓
- Dead-code removal (spec §6) → Task 5. ✓
- Final review + integration (spec §8) → Task 6. ✓
- Acceptance criteria 1-7 → Tasks 1-6. ✓

**Placeholder scan:** Task 2 (ticket detail page path/props), Task 1 Step 3 (repo getter/commit pattern), Task 5 (exact dead files) are read-then-verify against real code, each naming the file + grep to run. The reopen service/endpoint code, KB mapping table, consistency test, and the three small fixes are complete. No TBD/TODO.

**Type consistency:** `reopen_ticket(ticket_id, actor, comment=None) -> Ticket` consistent between service, endpoint, tests. `status_changed` event shape reused from `_add_event`. `GENERIC_EXEMPT` slugs match the violators the explorer found. KB mapping values verified against the explorer's `known_subtypes` lists.

**Note for implementer:** the reopen target status is `in_progress` (documented choice). The KB `GENERIC_EXEMPT` set is intentional — do NOT force subtypes on those (it would create harmful false subtype-matches that outrank focused articles); only the 10 mapped slugs change.
