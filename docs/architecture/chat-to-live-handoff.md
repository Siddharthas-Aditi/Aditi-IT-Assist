# Chat → Live Specialist Handoff

How an AI support conversation becomes a live human chat — and the guardrails
that keep it from happening too early.

> Related: [escalation-and-live-agent-handoff.md](escalation-and-live-agent-handoff.md)
> (ticket-before-handoff invariant), [live-chat-session-lifecycle.md](live-chat-session-lifecycle.md),
> [human-handoff-and-queue.md](human-handoff-and-queue.md) (HandoffPackage).

## The default flow

```
1. User starts chat
2. User describes the problem
3. AI captures problem statement + intent/issue analysis (triage)
4. AI asks follow-up questions if the statement is incomplete
5. AI retrieves grounded knowledge and attempts resolution
6. Only if unresolved / low-confidence / human-only / explicit human request:
   → create (or reuse) a ticket
   → queue a handoff to a live IT specialist
   → tell the user: "Please wait while I connect you to a live IT specialist."
7. Specialist claims the ticket → gets the full HandoffPackage
8. Specialist takes over in the same chat window
9. Specialist resolves or updates the outcome
10. Session closes cleanly with an audit trail
```

## No-direct-connect policy

**Normal users cannot connect to a live specialist before a minimally-useful
problem statement is captured.** This is enforced at two points that share one
pure policy function:

- **Policy** — `app/services/agents/escalation_policy.py` ::
  `handoff_context_sufficient(diag)`. Sufficient = a known issue category **plus**
  a concrete symptom / problem / error / subtype (same bar as
  `DiagnosticContext.has_enough_context()`), **or** the AI has already presented
  or the user has already tried any troubleshooting step.
- **Triage gate** — `app/workflows/nodes/triage.py`. When intent classifies as
  `ESCALATE_REQUEST` but context is insufficient, triage calls
  `_gather_problem_before_handoff` — it asks for a short description and
  deliberately does **not** set `should_escalate` / `escalation_confirmed` /
  `live_agent_requested`. No ticket, no handoff.
- **Service gate (defense in depth)** — `ChatService.request_live_agent`. For a
  known session that never reached an escalation offer and lacks context, it
  returns the gather prompt with `ticket=None` instead of creating a ticket.
  (The "Connect with a specialist" CTA is only rendered by the UI *after* an
  offer, so this guard only trips on cold/direct API calls.)

The shared user-facing prompt is `escalation_policy.GATHER_PROBLEM_PROMPT`.

### Handoff triggers (when escalation IS allowed)

- AI exhausted grounded steps (KB coverage / loop / repeated failure)
- Confidence below the floor (see Confidence Scoring in CLAUDE.md)
- Explicit human request **after** a problem statement exists
- Policy/guardrail block or missing-data that only a human can resolve

## Ticket creation

A ticket is created **on escalation/handoff, never blindly at chat start**, and
only on explicit confirmation (typed "yes" after an offer, or the "Connect"
CTA). It carries the conversation summary + extracted issue context and is
queued for the specialist queue. Creation is **idempotent per session**
(`ChatService._session_tickets`) — repeated clicks reuse the same ticket.

## Same-window takeover

The handoff stays in the same browser window (SPA navigation), not a popup:

- Employee chat (`SupportChatPage`) polls `GET /specialist-chat/active` every 5s.
- While queued it shows **"Please wait while I connect you to a live IT
  specialist"** (amber waiting banner).
- When a specialist starts the session, the banner flips to **"An IT specialist
  has joined — continue in live chat"**, routing to `/support/live-chat/:id`.
- The live pane (`LiveChatPage`) is the same component used by the specialist
  (`/operations/live-chat/:id`); role is derived from `specialist_id`.
- Transcript continuity + resume-on-refresh come from the persisted
  `specialist_chat_messages` table and the one-active-session-per-ticket index.

## Fallbacks

- **No specialist available (timeout)** — after 15 minutes of waiting without
  a specialist claiming the ticket, the system surfaces a fallback message:
  "No specialist is available right now. Your ticket is still active and the
  team will follow up via email." The user can also cancel waiting at any time
  via the Cancel button (calls `POST /chat/cancel-waiting`). The waiting status
  is checked via `GET /chat/waiting-status/{session_id}` which returns
  `specialist_available: false` after `WAIT_TIMEOUT_SECONDS` (900s default).
- **Cancel waiting** — user can cancel the live-connection request at any time.
  The ticket remains open for async follow-up, but the user returns to the
  AI-assisted chat flow.
- **Specialist ends/resolves** — typed end reasons + an end-of-chat system
  message; resolution notes can seed a knowledge candidate (never auto-published).
