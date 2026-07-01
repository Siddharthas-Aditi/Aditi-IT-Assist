# Chat-to-Ticket Handoff (Employee Experience)

When the AI can't resolve an issue, the handoff to a ticket + live specialist
should feel continuous and intentional — not like a bot abruptly handing off to a
disconnected ticketing system.

## What the employee sees

1. **Escalation offer.** After the AI exhausts grounded troubleshooting, it
   offers to raise a ticket and connect a specialist ("Connect with a
   specialist" CTA, or reply *yes*). No ticket is created until the employee
   confirms.
2. **Escalation confirmation.** On confirmation the AI replies with an explicit,
   reassuring message:
   > "✅ I've created support ticket **ITA-000042** and I'm sharing our full
   > conversation with the IT specialist — including what you asked, what I
   > understood, and the steps we already tried — so they can continue without
   > asking you to repeat everything."
   This is generated in `ChatService._format_response` whenever a real ticket
   ref exists.
3. **Ticket-created state.** An emerald confirmation card shows the ticket
   number, queued status and priority (`SupportChatPage`).
4. **Waiting state.** While queued, a banner reads "Please wait while I connect
   you to a live IT specialist," with a Cancel option. The ticket stays open for
   async follow-up if no one is available within the timeout.
5. **Specialist joined.** The chat flips to "An IT specialist has joined" and
   continues in the same window (`LiveChatPage`). The transcript persists and
   resumes on refresh.

## Why it's reassuring

The employee is told explicitly that their context is being carried forward, so
they don't fear having to re-explain. Behind the scenes this is true: a
transcript snapshot + structured escalation context are created at the same
moment the ticket is, and the specialist reads them on pickup
(see `specialist-triage-experience.md`).

## Guardrails preserved

* Ticket creation only on explicit confirmation (unchanged).
* Ticket-before-handoff invariant (unchanged).
* No-direct-connect policy — a minimally-useful problem statement is required
  before a human can be reached (unchanged).
* Idempotent per session — repeated "Connect" clicks reuse one ticket.
