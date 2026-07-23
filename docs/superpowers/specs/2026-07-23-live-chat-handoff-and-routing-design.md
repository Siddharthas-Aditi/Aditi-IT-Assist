# Reliable Live-Chat Handoff + Auto-Routing Assignment (Sub-project B)

**Date:** 2026-07-23
**Status:** Approved design — ready for implementation plan
**Scope:** One subsystem — the human handoff from AI chat to a live IT specialist, plus
the assignment/routing that feeds it. Chat-quality improvements (sub-project A) are a
separate spec/plan cycle to follow.

---

## 1. Problem

When an employee asks for a human (or the AI exhausts grounded help), the system creates a
ticket and drops it in a passive queue. A `specialist_chat_session` is born **only if a
specialist manually claims the ticket**. Nothing routes the request to a specific person,
notifies with accountability, or advances the request when no one responds. The employee
polls `GET /specialist-chat/active`, receives `{"session_id": null}` indefinitely, and sits
on "Please wait while I connect you to a live IT specialist" forever.

Observed in production data: ticket `ITA-000056` was created and auto-assigned to a lead at
status `triaged`, `specialist_chat_sessions` was empty, and the employee's active-session
poll returned null. The queue also holds ~39 stale "Live support request" rows and at least
one inconsistent record (`claimed_at` set with `claimed_by_name = null`).

### Goals

1. An employee who requests a human **always** reaches a terminal, honest state:
   connected to a specialist, or told the team will follow up — never an infinite wait.
2. Requests are **auto-routed** to the best-fit **Available** specialist, who is notified,
   while remaining claimable by others if the offer is not accepted in time.
3. Assignment is **production-grade**: presence-aware, load-balanced, category-informed,
   and resilient to restarts, multiple workers, and race conditions.

### Non-goals

- Chat/troubleshooting quality (sub-project A).
- WebSocket transport (HTTP polling stays; the API shape supports a later drop-in upgrade).
- Manual skill/category administration UI (category is a derived soft hint, not managed data).

---

## 2. Design decisions (agreed)

| Area | Decision |
|------|----------|
| Routing model | Auto-route to the best-fit Available specialist + notify; stays claimable by others on timeout. |
| Availability | Explicit **Available / Away** toggle per specialist, backed by a heartbeat. |
| Skill matching | Category as a **soft hint** — rank by load, boost specialists who recently handled that category (derived from ticket history; no manual upkeep). |
| Wait UX | Route → re-offer on timeout → broaden to all Available → graceful fallback. Interim "specialists busy" status while offers are in flight; honest terminal message when exhausted. |
| State storage | New DB-backed `live_handoff_offers` table + Alembic migration (not ticket fields). |
| Timeouts | `OFFER_TTL ≈ 30s` per specialist, ~2 re-offer rounds, then broaden; overall fallback if no accept within ~2 min. All config-driven. |

---

## 3. Architecture

Three cooperating units, each independently testable, plus a sweeper that drives the
lifecycle. Pure decision logic is separated from I/O so it can be unit-tested without a DB,
LLM, or network — matching the repo's existing pure-core + sweeper patterns
(`evaluate_idle`, `handoff_context_sufficient`, `rank()`).

### 3.1 Specialist Availability (presence layer)

- **Data:** `specialist_availability` — `user_id` (PK), `status` (`available` | `away`),
  `last_heartbeat_at`, `updated_at`. DB-backed → survives restarts, correct across workers.
- **Pure logic:** `is_available(record, now, ttl) -> bool` = `status == available` AND
  `now - last_heartbeat_at <= ttl` (default TTL 60s). A stale heartbeat auto-degrades to
  effectively-Away even if the toggle is still on (closed-tab safety).
- **Service:** `AvailabilityService.set_status()`, `heartbeat()`, `list_available()`.
- **API (under `/specialist-queue`):**
  - `PUT /availability` — set `available`/`away` (it_agent+).
  - `POST /availability/heartbeat` — refresh presence (it_agent+).
  - `GET /availability` — caller's current status (it_agent+).
- **Frontend:** Available/Away toggle in the `LiveQueuePage` header; the page's existing
  poll interval also sends a heartbeat.

### 3.2 Routing engine (pure function)

```
rank_candidates(
    ticket_category: str | None,
    available: list[SpecialistLoad],       # id, active_session_count, active_ticket_count
    recent_category_handlers: set[user_id], # resolved this category recently, from history
) -> list[user_id]                          # best first
```

- Primary sort: **lowest active load** (open live sessions + assigned open tickets).
- Boost: candidates in `recent_category_handlers` rank ahead at equal-ish load.
- Deterministic, no I/O. Returns an ordered candidate list so the lifecycle can walk it on
  re-offer.

### 3.3 Handoff offer lifecycle + sweeper (reliability core)

- **Data:** `live_handoff_offers` — `id`, `ticket_id`, `offered_to`, `offered_at`,
  `expires_at`, `round`, `state` (`offered` | `accepted` | `expired`). The **request-level**
  status (derived / stored on the waiting record) is `queued → connecting → connected |
  fallback`.
- **Pure core:** `evaluate_offer(offer, request, available, now) -> NextAction`, where
  `NextAction ∈ { hold, reoffer(next_id), broaden, fallback }`. This is the unit-tested heart
  of the fix; the sweeper only applies the returned action.
- **Flow:**
  1. Request → `rank_candidates` → offer to top Available specialist
     (`expires_at = now + OFFER_TTL`) → notify that specialist (reuse existing chime /
     desktop notification for a new targeted offer).
  2. Specialist **accepts** (opens the live chat) → `specialist_chat_session` created via the
     **atomic claim** → request → `connected`; employee's `/active` flips to "specialist
     joined" in the same window.
  3. Offer **expires** unanswered → the existing 30s background sweeper calls
     `evaluate_offer` → `reoffer` to the next candidate (`round++`). After the round cap →
     `broaden`: open as claimable by any Available specialist and notify them.
  4. **Exhausted** (no Available specialists, or max rounds without accept) → `fallback`:
     employee shown the honest terminal message; waiting UI stops; ticket remains in the
     queue for async pickup.
- **Concurrency:** acceptance uses the existing atomic claim
  (`UPDATE ... WHERE assigned_to IS NULL` / `SELECT ... FOR UPDATE`), so a late accept cannot
  collide with a sweeper re-offer, and double-accept is impossible.

### 3.4 Frontend

- **Specialist (`LiveQueuePage`):** Available/Away toggle + heartbeat. A targeted **offer**
  surfaces distinctly ("You've been offered ITA-xxxx — Accept / Pass") above the general
  claimable queue. Accept opens `LiveChatPage`. Broadened offers appear in the normal
  claimable list.
- **Employee (waiting view in `LiveChatPage`):** the "Please wait…" panel gains real state:
  - `connecting` (offer in flight / re-offering): interim reassurance —
    *"Our IT specialists are busy at the moment — someone may join your chat shortly. Hang
    tight."*
  - `connected`: "An IT specialist has joined" — continues in the same window.
  - `fallback`: *"No specialist is free right now — I've logged ticket ITA-xxxx and the team
    will follow up."* Spinner stops.

### 3.5 Data cleanup (targeted, in-scope)

- One-off maintenance script to close/expire abandoned pre-fix "Live support request"
  handoff tickets so the queue reflects reality.
- Fix the root inconsistency where the claim path could write `claimed_at` without a coherent
  claimer/session, as part of hardening the atomic-claim path.

---

## 4. Error handling

- **Degrade, never hang.** Any availability/routing error falls back to the plain claimable
  queue (today's behavior) — but the employee still receives the graceful fallback path, so
  the infinite wait cannot recur.
- Sweeper actions are idempotent and transaction-safe (commit warning/transition per the
  existing sweeper conventions; row locks on the accept/claim path).

---

## 5. Testing

| Layer | Coverage |
|-------|----------|
| Unit (pure) | `is_available`, `rank_candidates`, `evaluate_offer` (hold / reoffer / broaden / fallback) with table-driven fixtures. |
| Service | accept, expire→reoffer, round-cap→broaden, exhaustion→fallback; atomic-claim race (late accept vs. sweeper re-offer; double-accept). |
| API | availability endpoints (set / heartbeat / get) with RBAC; offer accept path. |
| Frontend | employee waiting-state transitions (connecting → connected / fallback); specialist availability toggle + offer accept. |

Targets follow `CLAUDE.md`: 80%+ services, 100% happy path for the lifecycle core.

---

## 6. Config (new settings, all defaulted)

- `LIVE_OFFER_TTL_SECONDS` (default 30)
- `LIVE_OFFER_MAX_ROUNDS` (default 2, then broaden)
- `LIVE_HANDOFF_FALLBACK_SECONDS` (default 120 — overall cap before fallback)
- `SPECIALIST_PRESENCE_TTL_SECONDS` (default 60 — heartbeat freshness)

---

## 7. Migration & rollout

- One Alembic migration: `live_handoff_offers` + `specialist_availability` (next number
  after 009).
- No feature flag required; degrade-to-queue behavior means partial rollout is safe. Existing
  in-flight tickets are reconciled by the cleanup script.
