# Chat & Live Support — End-to-End Product Flow

The employee + specialist experience, from first message to a resolved live chat.

> Companion: [employee-chat-experience.md](employee-chat-experience.md),
> [it-specialist-workflow.md](it-specialist-workflow.md). Architecture:
> [chat-to-live-handoff.md](../architecture/chat-to-live-handoff.md).

## Principles

1. **AI first.** The assistant captures the problem, asks follow-ups, retrieves
   grounded knowledge, and tries to resolve before any human is involved.
2. **No cold transfers.** A user cannot jump straight to a live agent at chat
   start — we collect a minimal problem statement so routing + context are real.
3. **Honest state.** We never say "connecting you" unless a ticket is queued; we
   never claim a specialist joined until one actually did.
4. **Same window.** The live specialist takes over in the same conversation, not
   a popup; the transcript is continuous and survives refresh.

## Employee journey

| Step | What the employee sees |
|------|------------------------|
| Start | Welcome + category tiles; types or picks a topic. |
| Describe | AI confirms understanding, asks follow-ups if vague. |
| Troubleshoot | Grounded, step-by-step guidance (only relevant KB). |
| Ask for a human too early | "I can connect you — first, briefly describe the issue…" (no ticket yet). |
| Escalation offered | "Connect with a specialist" button appears after the AI exhausts grounded help. |
| Queued | **"Please wait while I connect you to a live IT specialist"** (amber waiting banner). |
| Specialist joins | Green **"An IT specialist has joined — continue in live chat"**. |
| Live chat | Same-window pane; sees "IT specialist is typing…"; idle warning if quiet. |
| Close | Specialist resolves/ends; typed end reason shown; optional feedback. |

## Specialist journey

| Step | What the specialist sees |
|------|--------------------------|
| New handoff | Queue row appears; **sound chime + desktop notification** on each new unclaimed request (toggle in header). |
| Claim | Atomic claim (409 if someone beat them); full **HandoffPackage** (summary, detected app, category/subtype, steps tried, KB sources, transcript, escalation reason, ticket id). |
| Live chat | Same pane as the employee; sees "User is typing…"; can message, resolve, or end. |
| Idle | Sees the shared idle warning; chat auto-ends after the grace window. |
| Resolve | "Resolve & end" → typed `resolved`; resolution notes can seed a knowledge candidate (review-gated, never auto-published). |

## Edge scenarios

- **Specialist unavailable / after-hours** — ticket waits in queue; user keeps
  the waiting banner; ticket/email follow-up is the fallback. After 15 minutes
  of waiting, the system surfaces a fallback message offering async resolution.
  No fake connection.
- **Cancel waiting** — user can click Cancel on the waiting banner at any time.
  The ticket remains open for async follow-up but the live-connection request is
  cleared. User returns to AI-assisted chat flow.
- **Repeated "still not working"** — the AI advances on failure and escalates
  once grounded help is exhausted (loop/repeated-failure triggers).
- **Refresh / reconnect** — both sides re-enter the same session; transcript
  rehydrates from the DB.
- **Duplicate claim** — prevented atomically; the loser sees a "already claimed"
  notice and the queue refreshes.
- **System events** — joined / waiting / idle-warning / ended / timeout /
  escalation all render cleanly in the transcript.
