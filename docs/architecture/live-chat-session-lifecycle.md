# Live Chat Session Lifecycle

The state machine for a human-to-human specialist chat, after the AI handoff.

> Code: `app/models/specialist_chat.py`, `app/services/specialist_chat_service.py`,
> `app/api/v1/specialist_chat.py`. Companion docs:
> [live-specialist-chat.md](live-specialist-chat.md) (data model deep-dive),
> [idle-timeout-and-typing-indicators.md](idle-timeout-and-typing-indicators.md).

## States

| Status | Meaning |
|--------|---------|
| `active` | Live; either party can message. |
| `idle_warning` | No activity for `idle_warning_seconds`; a "still there?" system message was posted. Reverts to `active` on any message. |
| `ended_by_user` | The employee ended it (`user_left`). |
| `ended_by_specialist` | The specialist ended/resolved it (`specialist_ended` / `resolved`). |
| `ended_by_timeout` | Auto-ended after `idle_end_seconds` (`idle_timeout`). |
| `ended_by_system` | Error path (`session_error`). |

Typed **end reasons**: `resolved`, `user_left`, `specialist_ended`,
`idle_timeout`, `session_error`. Endings are explicit and one-way — the session
never silently flips back to active.

## Transitions

```
claim (queue)              POST /specialist-chat/start
   │                         (idempotent: unique partial index on ticket →
   ▼                          resume the existing active session on conflict)
 active ──message──────────► active            (last_activity_at bumped)
   │                           ▲
   ├──idle ≥ warning──► idle_warning ──message──┘
   │                           │
   │                           └──idle ≥ end──► ended_by_timeout
   ├──user end──────────────────────────────► ended_by_user
   ├──specialist end/resolve───────────────► ended_by_specialist
   └──error─────────────────────────────────► ended_by_system
```

Every transition writes an **audit event** (start, each message with role +
content hash, idle warning, end). The full transcript is persisted immutably in
`specialist_chat_messages` (roles: `user`, `specialist`, `system`); system
events (`session_started`, `idle_warning`, `session_ended_*`) render inline.

## Duplicate-claim prevention

Claiming is an atomic DB `UPDATE … WHERE assigned_to IS NULL … RETURNING`
(`SpecialistQueueService.claim`). A second specialist gets HTTP 409. Starting a
chat is guarded by a **unique partial index** on `(ticket_id) WHERE status IN
('active','idle_warning')`; a concurrent/duplicate start resumes the existing
session instead of creating a second one.

## Reconnect / resume

- The employee discovers an active session via `GET /specialist-chat/active`
  and is routed back into the same `sessionId`.
- A page refresh re-polls `GET /specialist-chat/{id}` (every 3s) and rehydrates
  the full transcript + current status.
- Re-`start` of an already-active ticket returns the existing session (resume),
  so a reconnecting specialist lands in the same room.

## Background sweeper

A pure-asyncio loop in the FastAPI lifespan (`app/services/scheduler.py`) runs
`sweep_idle()` every `IDLE_SWEEPER_INTERVAL_SECONDS` (default 30s) to apply idle
rules even when nobody is polling. The polling endpoint applies the same
`check_and_apply_idle` lazily, so a woken-up tab still sees the right state.
