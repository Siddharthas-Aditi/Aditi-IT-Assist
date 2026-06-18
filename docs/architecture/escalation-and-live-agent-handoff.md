# Escalation & Live-Agent Handoff

How the chat agent moves from self-serve troubleshooting to a human IT
specialist, and **why a real support ticket is always created before the
handoff**.

## Principles

1. **Never promise what didn't happen.** The agent must not claim a ticket
   exists unless one was actually persisted. (The previous implementation said
   "I've drafted a support ticket… IT will follow up" while creating nothing.)
2. **Ticket before handoff.** A live-agent connection always has a system-of-
   record ticket behind it, carrying the conversation context and attempted
   steps. The ticket is the unit the IT queue works from.
3. **Explicit confirmation.** A ticket is created only when the employee
   explicitly confirms ("Connect with a specialist" / replies *yes*) — not on a
   bare escalation offer.
4. **Nodes stay pure; the service layer persists.** Workflow nodes prepare a
   *draft* and decide intent; `ChatService` performs the DB writes.

## Flow

```
exhausted grounded help  OR  user asks for a human
            │
            ▼
      escalation_node            ← sets should_escalate, escalation_confirmed
            │                       (confirmed = typed "yes" / live_agent_requested)
            ▼
      draft_ticket (ticket_node) ← builds ticket_draft (data) + OFFER message
            │                       ticket_offered=True, ticket_created=False
            ▼
        ChatService
        ├─ offer only (not confirmed) → response.escalation_offered=True,
        │                                requires_escalation=True, ticket=None
        │                                → UI shows "Connect with a specialist"
        └─ confirmed                  → create_ticket() → request_live_agent()
                                         → commit → response.ticket={number,…}
```

The **"Connect with a specialist"** button calls `POST /chat/request-live-agent`,
which is the deterministic, explicit-confirm path. It:

1. Reuses an existing ticket for the session if present (**idempotent**).
2. Otherwise creates a ticket from the session's `ticket_draft` (or a minimal
   draft if none), then queues it for a human — **create first, queue second**.

## Where it lives

| Concern | Location |
|--------|----------|
| Escalation decision + confirmation signal | `app/workflows/nodes/escalation.py` (`escalation_confirmed`) |
| Ticket *draft* (data + offer message) | `app/workflows/nodes/ticketing.py` (no persistence) |
| Ticket persistence + handoff + idempotency | `app/services/agents/chat_service.py` (`_handle_ticketing`, `request_live_agent`, `_persist_and_queue`) |
| Queue-for-human on the ticket | `app/services/ticket_service.py` (`request_live_agent`) |
| API | `app/api/v1/chat.py` (`POST /chat/message`, `POST /chat/request-live-agent`) |
| Response contract | `app/schemas/chat.py` (`TicketRef`, `escalation_offered`, `ticket`, `LiveAgentRequest/Response`) |
| UI | `frontend/src/pages/employee/SupportChatPage.tsx` (Connect button + ticket chip) |

## Queueing semantics

`TicketService.request_live_agent(ticket_id, actor)`:

- moves `new → triaged` (enters the live ops queue),
- raises priority to at least `high`,
- records a `live_agent_requested` event + an internal note with context.

It does **not** mark the ticket `in_progress` (no agent has picked it up yet).

## Idempotency

`ChatService` keeps a per-session `session_id → TicketRef` map, so multi-turn
escalation and repeated "Connect" clicks reuse the **same** ticket instead of
spawning duplicates. (In-memory today; persist alongside sessions in production.)

## Known limitations / follow-ups

- **Chat sessions are in-memory.** Tickets are therefore created with
  `session_id=None` (the `tickets.session_id` FK points at a persisted
  `chat_sessions` row that doesn't exist yet). When sessions are persisted, set
  `session_id` on the ticket for first-class linkage. Context is currently
  preserved in the ticket description / `ai_summary`.
- **No real-time live chat.** "Live agent" means the ticket is queued for a
  human in IT Operations; there is no synchronous chat bridge yet. See
  `AGENT_COLLABORATION_ARCHITECTURE.md` for the future Teams/real-time handoff.
- **Premature escalation (separate issue).** If retrieval returns no grounded
  article for a confirmed subtype, the agent escalates without showing steps.
  Tracked separately from this handoff work.

## Related

- `docs/architecture/troubleshooting-state-machine.md`
- `docs/architecture/ticketing-lifecycle.md`
- `docs/architecture/workflows.md`
