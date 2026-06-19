# IT Specialist Workflow

> What a live IT specialist sees and does when they pick up a chat the AI
> couldn't fully resolve. This document is the product contract behind the
> queue API + the Phase-2 specialist UI.

---

## 1. Daily flow

1. **Open the queue.** Specialist signs into Aditi IT Assist, navigates to
   "Live Support Queue". Sees prioritized list (critical first, oldest in
   tier first). Their own active claims appear at the top under
   "Mine".
2. **Open an entry.** One click → detail view with the typed
   `HandoffPackage`: one-line summary, slots, steps tried, KB sources,
   conversation history, and the supervisor's decision trace.
3. **Claim.** Single button. Atomic. If someone else got there first the UI
   surfaces "Already claimed by Priya P." (HTTP 409) instead of breaking.
4. **Connect.** The chat handoff thread opens with the user still attached.
   Specialist sees the same context the AI had, plus their own notes pane.
5. **Resolve.** Specialist enters resolution notes. Optional checkbox:
   "Send to KB Improvement queue for SME review". On submit, the ticket
   closes; the candidate (if checked) appears in the SME review queue.
6. **Release** (rare). If the specialist needs to hand off to a colleague,
   they release the claim; ticket returns to the queue at `triaged`.

---

## 2. What the Context pane shows

```
[ Handoff Package · schema v1.0 ]

Summary
  ▸ Issue: User's mailbox is full and unable to send mail
  ▸ System: Outlook            ▸ Subtype: mailbox-full
  ▸ Urgency: medium             ▸ AI confidence at handoff: 0.42
  ▸ User: Anita K. (anita.k@aditiconsulting.com)

Diagnostic context
  - normalized_system: outlook
  - exact_problem_statement: "My mailbox is full and I can't send"
  - failed_steps: [Empty Deleted Items, Empty Junk Email]

Steps the AI tried
  ✓ Checked mailbox size       (Outlook · Mailbox Cleanup)
  ✗ Empty Deleted Items folder (failed)
  ✗ Empty Junk Email folder    (failed)

KB sources consulted
  ▸ "Outlook mailbox full" (id: a3f9…)   relevance 0.81

Web sources consulted
  — (none for this category)

Conversation
  user      "Mailbox is full, can't send"
  assistant "Got it — just to make sure: your mailbox is full. …"
  user      "yes"
  assistant "It looks like your mailbox is full — let's start with…"
  user      "I tried that, didn't help"

Supervisor decision trace
  1. triage → CONTINUE (intent=continue, conf=0.5)
  2. supervisor → DELEGATE_SUB outlook → outlook.mailbox_full
  3. specialist → handled, steps=3
  4. resolution_feedback → NEGATIVE_FEEDBACK
  5. supervisor → ESCALATE (reason=exhausted_grounded_steps)
```

The trace lets the specialist see exactly *why* the AI handed off — no
guessing.

---

## 3. Atomic claim semantics

The claim endpoint runs:

```sql
UPDATE tickets
SET assigned_to = :me,
    status      = 'in_progress',
    first_response_at = COALESCE(first_response_at, now())
WHERE id = :ticket_id
  AND source = 'chat'
  AND (assigned_to IS NULL OR assigned_to = :me)
RETURNING *
```

If the row count is 0, the API responds **409 Conflict** with the current
assignee's name. The UI re-fetches the queue and shows a banner. We never
silently overwrite or duplicate.

---

## 4. Knowledge candidate on resolve

When the specialist ticks "Send to KB Improvement queue":

1. `SpecialistQueueService.resolve` calls
   `KnowledgeImprovementService.record_specialist_resolution(...)`.
2. A `KnowledgeCandidate` row is written with `state='proposed'`,
   `source='specialist_resolution'`, `source_ticket_id=<this ticket>`,
   `proposed_by_user_id=<specialist>`, `confidence=0.75`.
3. The candidate appears in the SME review queue ranked by confidence +
   times_seen.

The article is **not** auto-published. An SME with `knowledge:write` reviews
the candidate, optionally edits it, and either rejects, marks duplicate, or
promotes to a real article (which links back via `promoted_article_id`).

This means a specialist's hard-won fix can become reusable knowledge with
minimal additional effort — but only after a human says "yes, publish this".

---

## 5. Permissions

| Role | Can list queue | Can claim | Can release | Can resolve | Can promote candidates |
|---|---|---|---|---|---|
| `it_agent` | ✓ | ✓ | own | own | — |
| `it_lead` | ✓ | ✓ | any | any | ✓ |
| `it_admin` | ✓ | ✓ | any | any | ✓ |
| `security_auditor` | read-only audit view | — | — | — | — |
| `employee` | — | — | — | — | — |

---

## 6. Phase-2 UI acceptance criteria

The frontend specialist UI ships in Phase 2 (see
[rollout plan](../development/rollout-plan-multi-agent.md)). Acceptance:

- Queue list refreshes within 5s of a new escalation.
- Claim is atomic (verified by stress test: two specialists, one entry).
- Context pane fully renders the `HandoffPackage` v1.0 without truncation.
- Resolve form blocks submission when notes are empty.
- "Send to KB Improvement queue" preview shows what will be proposed.
- Release is single-click + undo banner.
