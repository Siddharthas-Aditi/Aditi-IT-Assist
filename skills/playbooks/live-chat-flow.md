# Playbook: Live Specialist Chat Flow

**When**: changing live chat lifecycle, idle policy, typing indicators, or the
same-window handoff experience.

## Key files
Backend: `services/specialist_chat_service.py` (lifecycle, `evaluate_idle`,
`_typing_state`), API `app/api/v1/specialist_chat.py`, background sweeper in
`services/scheduler.py`. Frontend: `pages/operations/LiveChatPage.tsx`,
`features/specialist-chat/`. Docs: `docs/architecture/live-chat-session-lifecycle.md`,
`idle-timeout-and-typing-indicators.md`, `docs/product/chat-and-live-support-flow.md`.

## Invariants
1. **Same window**: employee polls `GET /specialist-chat/active`; shows "please wait"
   while queued, flips to "specialist has joined", continues in the same page — no popup.
   Transcript persists and resumes on refresh.
2. **Idle policy**: default 7-min warning + 2-min grace → auto-end (`ended_by_timeout`).
   Configurable via `LIVE_CHAT_IDLE_WARNING_SECONDS` / `LIVE_CHAT_IDLE_END_SECONDS` or
   per-`start` override. A **message** resets idle; typing does **not**. `evaluate_idle`
   is a pure function shared by the polling endpoint and the 30s sweeper.
3. **Typing**: ephemeral in-memory (8s TTL), no DB, no audit, no idle reset;
   `GET` returns roles typing excluding the caller.
4. Typed end reasons; lifecycle is a state machine — don't add ad-hoc transitions.

## Validate
`test_specialist_chat_*`, `make test-frontend`, and
`docs/development/live-chat-qa-checklist.md`. Trace: queue → wait → join → exchange →
idle warning → grace → auto-end; refresh mid-session resumes transcript.

## Checklist
- [ ] `evaluate_idle` stays pure + shared; message resets, typing doesn't.
- [ ] Typing state ephemeral (no DB/audit).
- [ ] Same-window waiting/joined states intact; transcript resumes.
- [ ] End reasons typed; lifecycle transitions valid.
