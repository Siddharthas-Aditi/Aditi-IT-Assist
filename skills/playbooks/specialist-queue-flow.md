# Playbook: Specialist Queue & Assignment Flow

**When**: changing the specialist queue, ticket claim/assignment, or new-handoff
notifications.

## Key files
Backend: `services/specialist_queue_service.py`, `escalation_service.py`, API
`app/api/v1/specialist_queue.py`. Frontend: `pages/operations/` (`LiveQueuePage`,
`AssignedTicketsPage`), `features/specialist-chat/HandoffContextPanel.tsx`,
`lib/notification-sound.ts`. Docs: `docs/architecture/human-handoff-and-queue.md`.

## Approach & invariants
1. **Atomic claim**: claiming a ticket is a DB-level atomic operation — two specialists
   must never claim the same ticket. Don't move this to app-level check-then-set.
2. **Handoff package**: read the persisted `EscalationContext` first (survives restart);
   present **summary-first, transcript-second** via `build_handoff_package` /
   `get_handoff_view`. Never rebuild context from a raw chat blob.
3. **Notifications**: `LiveQueuePage` chimes + desktop-notifies **once per new**
   unclaimed handoff (track seen ticket ids; respect mute). Don't re-alert on poll.
4. **RBAC**: propose/claim = `it_agent+`; approvals/assignment = `it_lead+`. Audit
   transitions.

## Validate
`make test-backend` (queue + escalation service tests), `make test-frontend`, and the
manual `docs/development/live-chat-qa-checklist.md`. Trace: escalate → appears in queue
→ claim (once) → handoff view shows summary → live chat opens.

## Checklist
- [ ] Claim remains atomic; no double-claim window.
- [ ] Handoff view is summary-first from persisted context.
- [ ] Notification fires once per new handoff; mute respected.
- [ ] Transitions audited; RBAC correct.
