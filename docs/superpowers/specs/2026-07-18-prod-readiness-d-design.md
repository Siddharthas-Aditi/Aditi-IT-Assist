# Sub-project D — Reopened Tracking + Gap-Closure

**Date:** 2026-07-18
**Status:** Approved design (pending user spec review)
**Part of:** production-readiness engagement (final sub-project)

## Problem

The A–C feature work surfaced ~10 concrete follow-ups, and the one true product
gap in reporting — **no reopen action** — means C1's "Reopened" column always reads
0. D closes these loose ends so the platform is production-coherent.

## Goal (user-approved decisions)

Implement a **reopen action** so C1's Reopened column reflects reality
(**event-derived**, no new column), complete **status-change event logging** on all
ticket transitions, and close the carried-forward review follow-ups + retire dead
code. No deep infra audit (deferred by user); no schema churn beyond none needed.

## Non-goals

- No `reopen_count` column (event-derived is the single source of truth — C1 already
  derives from `status_changed` events).
- No deep deploy/CI/security audit (user chose the focused scope).
- No new features.

## Units of work

### 1. Reopen action (backend + minimal frontend)
- `TicketService.reopen_ticket(ticket_id, by_user, reason=None)`: allowed only from
  `resolved`/`closed` → an active status (`in_progress` or `triaged`; pick one and
  document); clears `resolved_at`/`closed_at` as appropriate; **logs a
  `status_changed` `TicketEvent`** (`old_value`=prior, `new_value`=active) via the
  existing `_add_event` — this is what C1's reopened derivation reads. RBAC:
  `ticket:reopen` (permission already exists). Rejects reopen from a non-resolved
  state.
- API: `POST /tickets/{id}/reopen` (require `ticket:reopen`), returns the updated
  ticket.
- Frontend: a **Reopen** button on the ticket detail page, shown for it_agent+ when
  the ticket is resolved/closed (gated via `permissions.ts`), calling the endpoint.

### 2. Complete status-change event logging
- `SpecialistQueueService.release()` and `.resolve()` currently mutate
  `ticket.status` directly with **no `TicketEvent`**. Add `status_changed` events on
  both (consistent with `TicketService.update_status`) so status history — and
  reopen derivation via the queue path — is complete. Reuse the existing event
  writer / follow its shape.

### 3. KB subcategory consistency (A follow-up)
- Add a test asserting every seeded article's `subcategory` ∈
  `known_subtypes(category)` for categories that have classifier rules (the invariant
  C1/A rely on for the grounding boost).
- Fix the ~18 pre-existing violators: map each to a valid existing subtype for its
  category; where no suitable subtype exists, either add a minimal subtype rule
  (only if clearly warranted) or set the closest valid one. Document each mapping.
  The camera monolithic-article content split is **out of scope** (note only).

### 4. Triage keyword alignment (A follow-up)
- Align `_keyword_classify`'s windows-update keyword list with the classifier's
  `_WINDOWS_UPDATE_RULES` so no-LLM-path phrases (`"windows won't update"`,
  `"update loop"`, `"update not installing"`) route to `software/windows-update`.
  Keep the ordering guarantees (password/access still wins for "update password").

### 5. Web-research specialist mapping (B2 follow-up)
- In `ChatService._maybe_run_web_research`, when `routed_specialist` is absent, map
  the issue `category` (slash form, e.g. `access/permissions`) to a real registry
  specialist name so unmatched-category escalations still get governed web research
  (instead of the current safe no-op). Use the registry's category→specialist
  lookup (`find_specialist_for` or equivalent). Still a safe no-op if truly no
  specialist matches.

### 6. Dead-code removal
- Delete `app/models/models.py` (unreferenced scaffold; confirm zero imports first).
- Remove the legacy `WebSearchService` class fallback path (now that B2 uses the
  provider abstraction) and its stdlib-logging-with-kwargs bug — update
  `ControlledWebResearchAgent`'s default so it no longer instantiates the legacy
  class (require an explicit provider, or default via `get_web_search_provider()`).
- Retire the unrouted `ChatBubble`/`ChatPanel`/`QuickReplies` chat feature module +
  `chat-store` + their tests (employee chat uses `SupportChatPage`; these are dead).
  Confirm no route/import references before deleting.

### 7. Exporter sanitize parity (C1 follow-up)
- Make `to_csv`/`to_pdf` sanitize only string cells (match `to_xlsx`), so a
  hypothetical negative number isn't spuriously quote-prefixed. Behavior-preserving
  today; correctness hardening.

### 8. Final whole-branch review + integration
- After all tasks: a final whole-branch review across the ENTIRE engagement branch
  (A–D), then present the integration decision (PR / merge) to the user.

## Error handling / guardrails

- Reopen is RBAC-gated (`ticket:reopen`) and state-guarded (only from
  resolved/closed); rejects otherwise.
- Dead-code deletions are verified zero-reference before removal; full suites must
  stay green.
- KB subcategory fixes must not break grounding tests; the new consistency test is
  the guard.
- No behavioral change to employee/specialist/admin runtime beyond the reopen
  affordance (`memory/known-risks.md` #4 RBAC, #9 no dummy data preserved).

## Testing

- **Reopen:** unit (resolved→reopen logs status_changed event, sets active status,
  RBAC rejects non-permitted, rejects reopen-from-open); API (permission 403/200);
  and a C1 report test proving a reopen now increments the report's Reopened count
  (ties #1 to C1's derivation).
- **Queue events:** release()/resolve() write status_changed events (unit).
- **KB consistency:** the full-corpus invariant test passes after fixes.
- **Triage:** the previously-missed windows-update phrases now classify correctly;
  password-update still routes to access.
- **Web-research mapping:** an unmatched-category escalation now resolves a valid
  specialist name (unit).
- **Dead-code:** full backend + frontend suites green after deletions (no dangling
  imports).
- **Exporters:** existing tests still pass; a negative-number cell isn't prefixed.

## Acceptance criteria

1. A resolved ticket can be reopened (RBAC-gated), logging a `status_changed` event;
   C1's Reopened count reflects it.
2. Queue release/resolve log status_changed events.
3. Every seeded article's subcategory is a known subtype (test-asserted).
4. No-LLM triage routes the windows-update phrases correctly.
5. Unmatched-category escalations get governed web research (specialist mapped).
6. Dead code removed; full backend `ruff`+`pytest` and frontend `lint`+`typecheck`+
   `vitest` green.
7. Final whole-branch (A–D) review done; integration decision presented.

## Risks (`memory/known-risks.md`)

- #4 RBAC — reopen is permission-gated + state-guarded.
- #1 grounding — KB subcategory fixes guarded by the new consistency test + existing
  grounding/retrieval evals.
- Dead-code removal — verify zero references; suites are the safety net.
- #11 scheduled-report claim — untouched by D.
