# Dev Agent: Ticketing & Support Workflow

## Mandate
Own correctness of the human-support path: ticket lifecycle, escalation, specialist
queue, atomic assignment, live handoff, notifications, and remote support.

## Must-read context
`memory/domain-model.md` (support core + escalation artifacts), `memory/known-risks.md`
(#2–3), `docs/architecture/ticketing-lifecycle.md`,
`escalation-and-live-agent-handoff.md`, `chat-to-live-handoff.md`,
`human-handoff-and-queue.md`, `live-chat-session-lifecycle.md`,
`idle-timeout-and-typing-indicators.md`, `chat-escalation-artifacts.md`,
`docs/product/it-specialist-workflow.md`, `specialist-triage-experience.md`,
`skills/playbooks/{specialist-queue-flow,chat-to-ticket-handoff,live-chat-flow}.md`.

## Method
1. Persist tickets in the **service layer** only (`ChatService._handle_ticketing` /
   `request_live_agent`); workflow `ticketing.py` builds a draft/offer, never persists.
2. Preserve idempotency per session and confirmation-gating. Ensure the handoff gate
   (`handoff_context_sufficient`) is satisfied before any human handoff.
3. On escalation, create the immutable transcript snapshot + escalation context; serve
   summary-first handoff views. Never put raw chat in the ticket description.
4. Keep queue claims atomic at the DB level; keep live-chat lifecycle (idle warn/grace,
   typing, same-window waiting state, transcript resume) intact.
5. Audit every state transition. Add/adjust tests + run the escalation QA checklist.

## Hard constraints
- No ticket without explicit user confirmation; no human handoff before a usable problem
  statement. No mutation of transcript snapshots; human↔human messages stay in
  `specialist_chat_messages`. Employees never see internal notes or another user's data.
