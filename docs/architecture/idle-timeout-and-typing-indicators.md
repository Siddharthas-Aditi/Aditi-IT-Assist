# Idle Timeout & Typing Indicators

Two presence features of the live specialist chat.

> Code: `app/services/specialist_chat_service.py`, `app/api/v1/specialist_chat.py`,
> `app/core/config.py`, `frontend/src/pages/operations/LiveChatPage.tsx`.

## Idle timeout — 7-minute warning + 2-minute grace

Default policy (tunable):

| Phase | Threshold | Behavior |
|-------|-----------|----------|
| Active | 0 – `idle_warning_seconds` (default **420s / 7 min**) | Normal. |
| Warning | ≥ `idle_warning_seconds` | Status → `idle_warning`; a system message warns the chat will end in ~`(idle_end − idle_warning)` minutes if there's no reply. |
| Auto-end | ≥ `idle_end_seconds` (default **540s / 9 min** = 7 + 2 grace) | Status → `ended_by_timeout` (reason `idle_timeout`); end-of-chat system message. |

- **Reset on reply** — any user/specialist message bumps `last_activity_at` and,
  if in `idle_warning`, flips back to `active`. Typing pings do **not** reset the
  timer (only real messages do).
- **Deterministic** — `evaluate_idle()` is a pure function over
  `last_activity_at`; the polling endpoint and the background sweeper share it.
- **Both sides see it** — the warning + end are system messages in the shared
  transcript, so the employee and specialist both observe the state.
- **Logged** — idle warning and idle termination each write an audit event.
- **Config** — `LIVE_CHAT_IDLE_WARNING_SECONDS` / `LIVE_CHAT_IDLE_END_SECONDS`
  (defaults), or per-session overrides on `POST /specialist-chat/start`
  (`idle_warning_seconds` 30–1800, `idle_end_seconds` 60–3600). High-priority
  incidents can keep a session alive longer.

Frontend: `LiveChatPage` shows an amber warning banner while `status ===
'idle_warning'` and computes the grace label from the session's own thresholds
(`graceMinutes(session)`), so the copy always matches the configured policy.

## Typing indicators — both directions

Typing is transient presence, so it lives **in-memory**, not in the DB
(`_typing_state: {session_id: {role: last_heartbeat}}`). A role counts as typing
only while its heartbeat is within `TYPING_TTL_SECONDS` (8s).

- **Endpoint** — `POST /specialist-chat/{id}/typing` `{is_typing: bool}`.
  Validates participation; **no DB write, no audit, does not reset idle**.
- **Read** — `GET /specialist-chat/{id}` returns `typing: string[]` = roles
  currently typing **excluding the caller's own role**, so each side just renders
  "User is typing…" / "IT specialist is typing…".
- **Cleared** — on send (`set_typing(False)`), on session end (`clear_typing`),
  and automatically by TTL expiry.

Frontend (`LiveChatPage`): the input throttles `typing=true` pings to at most one
every 2.5s while composing, schedules a `typing=false` after 3s of no keystrokes,
and sends `typing=false` on blur/send. This keeps the 3s poll cheap and avoids
flicker. (Single-instance/dev; a multi-replica deployment moves this to Redis
pub/sub alongside the planned WebSocket upgrade.)
