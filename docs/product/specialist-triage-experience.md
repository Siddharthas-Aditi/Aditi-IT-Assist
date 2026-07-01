# Specialist Triage Experience

When a specialist picks up an escalated chat, they get a **warm handoff**: a
concise summary first, the full transcript second. They should be able to triage
in seconds and still inspect every detail when needed. We never dump raw JSON.

## The handoff context panel

Rendered at the top of `LiveChatPage` for the specialist
(`frontend/src/features/specialist-chat/HandoffContextPanel.tsx`), backed by
`GET /specialist-queue/{ticket_id}/handoff-view`. Sections, in order:

1. **Overview** — issue summary, category/subcategory, affected system, urgency,
   AI confidence, and the AI resolution status badge.
2. **AI Handoff Summary** — what the employee asked + why it was escalated.
3. **Troubleshooting Already Attempted** — each AI step with a worked/failed/
   skipped icon and its source KB article.
4. **KB Signals / Knowledge Gaps** — KB articles referenced + human-readable KB
   gap tags (e.g. "Article suggested but unresolved").
5. **Full Conversation Transcript** — collapsed by default in a `<details>`
   element; expands to show every turn with role-distinct bubbles (Employee, AI
   Assistant, System, Specialist).

Pre-escalation AI turns and post-escalation live-specialist messages are visually
distinct, so the specialist always knows which messages came from the AI leg vs
the human leg.

## Degraded mode

Older tickets without a persisted escalation context still render the panel —
built from ticket fields with a small "no structured context captured" note —
rather than showing an error.

## Navigation

Specialist live-chat pages now render breadcrumbs
(`Specialist Queue → My Assigned → <ticket>`) via the shared `Breadcrumbs`
component, consistent with the admin console.

## After resolution — capturing the comparison

When the specialist resolves the ticket, a baseline comparison (their resolution
notes + KB-candidate flag) is written onto the escalation context automatically.
A richer structured comparison (their actual steps, a final category, and an
explicit AI-vs-specialist gap note) can be submitted via
`POST /specialist-queue/{ticket_id}/resolution-comparison`. This data powers
human-reviewed AI/KB improvement — it is never used for uncontrolled
self-learning.
