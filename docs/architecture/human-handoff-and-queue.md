# Warm Handoff + IT Specialist Queue

> What the assistant hands a live IT specialist when AI can't fully resolve
> an issue, and how specialists pick up and close those conversations safely.

---

## 1. Invariants

1. **Ticket-before-handoff.** A ticket is persisted *before* the user is told
   a specialist is taking over. We never tell the user "I've connected you"
   without a ticket row existing.
2. **Explicit consent.** A ticket is only created when the user's intent
   classifies as `ESCALATE_REQUEST` or `CONFIRM` after an offer. The chat
   service runs a defense-in-depth intent guard
   (`_user_intent_authorizes_ticket`) on top of `escalation_confirmed`. See
   [`conversation-intents.md`](./conversation-intents.md) and
   [`escalation-and-live-agent-handoff.md`](./escalation-and-live-agent-handoff.md).
3. **No duplicate claims.** Two specialists must not pick up the same chat.
   Enforced by a single atomic `UPDATE` with a `WHERE assigned_to IS NULL OR
   assigned_to=:me` guard; the service surfaces the conflict as HTTP 409.
4. **Structured context, not raw history.** Specialists receive a typed
   `HandoffPackage`, not a chat-log dump.
5. **Knowledge candidates on close, never auto-publish.** A resolving
   specialist may opt to send the resolution to the Knowledge Improvement
   review queue. SMEs promote separately; the model is never edited silently.

---

## 2. Handoff package contract

`backend/app/schemas/specialist_queue.py`:`HandoffPackage`

```
HandoffPackage
├── schema_version: "1.0"
├── session_id
├── ticket_id?
├── summary: HandoffSummary
│   ├── issue_one_liner
│   ├── affected_system?
│   ├── issue_category?, issue_subtype?
│   ├── urgency?
│   ├── user_name?, user_email?
│   └── ai_confidence_at_handoff
├── diagnostic_slots: {slot: value}
├── steps_attempted: [{instruction, outcome, source_kb_title?}]
├── kb_sources_consulted: [{article_id, title, relevance?}]
├── web_sources_consulted: [{url, title, trust_tier, snippet?}]
├── conversation: [{role, content, timestamp?}]
├── handoff_reason
├── handoff_triggered_by: enum
│   {user_request | ai_low_confidence | exhausted_grounded_steps
|    loop_detected | repeated_failure | policy_block | missing_data}
└── supervisor_decision_trace: [SupervisorDecision...]
```

The package is the contract the specialist UI renders. It's versioned —
bumping `schema_version` requires updating the frontend pane.

---

## 3. Queue lifecycle

Backing storage: existing `tickets` table, filtered to `source='chat'` and
the active statuses below.

```
            ┌──────┐
   chat ─▶  │ new  │ ───────────────┐
            └───┬──┘                 │
                ▼                    ▼
          ┌─────────┐         ┌────────────┐
          │ triaged │ ◀──────│ in_progress │  ◀── claim
          └────┬────┘         └─────┬──────┘
               │  release          │  resolve
               ▼                    ▼
          back to queue       ┌──────────┐
                              │ resolved │
                              └──────────┘
                                    │
                                    ▼
                              ┌────────┐
                              │ closed │ (admin / SLA)
                              └────────┘
```

`waiting_for_user` and `escalated` are also queue-visible — included so a
specialist can pick a paused conversation back up.

Ordering: priority desc (critical first), then oldest first within a
priority tier (FIFO).

---

## 4. API

Base path: `/api/v1/specialist-queue`. All routes require the
`ticket:assign` permission (`it_agent`, `it_lead`, `it_admin`).

| Method | Path | Body | Returns | Notes |
|---|---|---|---|---|
| `GET` | `/` | — | `QueueListResponse` | `?only_unclaimed=&include_mine=&limit=` |
| `GET` | `/{ticket_id}` | — | `HandoffPackage` | Full context; pulls session state if still in memory. |
| `POST` | `/claim` | `ClaimRequest` | `ClaimResponse` | Atomic; 409 if already claimed. |
| `POST` | `/release` | `ClaimRequest` | `{ticket_id, status}` | Only the claimer (or admin) may release. |
| `POST` | `/resolve` | `ResolveRequest` | `ResolveResponse` | Optional `propose_knowledge_candidate` flag. |

The atomic claim is the most important detail:

```python
UPDATE tickets
SET assigned_to = :me, status = 'in_progress',
    first_response_at = COALESCE(first_response_at, now())
WHERE id = :ticket_id
  AND source = 'chat'
  AND (assigned_to IS NULL OR assigned_to = :me)
RETURNING *
```

If the `RETURNING` row is empty, the service reads the row and tells the
caller whether it was already taken (`PermissionError` → HTTP 409) or
doesn't exist (`LookupError` → HTTP 404).

---

## 5. Specialist UI flow (Phase 2)

Phase 1 ships only the API. The Phase 2 UI:

1. **Queue page** — table of entries, columns: ticket #, requester, subtype,
   priority, age. Click → opens detail.
2. **Detail page** — header (issue one-liner), tabs:
   - "Conversation" (chronological turns)
   - "Context" (diagnostic slots + steps_attempted)
   - "Sources" (KB + web)
   - "Supervisor trace" (replayable decisions for audit)
3. **Claim CTA** — single button. After claim, page swaps to *active*
   state with the chat handoff thread.
4. **Resolve** — modal: resolution notes textarea + checkbox "Send to KB
   Improvement queue". Submits to `/resolve`.

Acceptance criteria for Phase 2 sit in
[`it-specialist-workflow.md`](../product/it-specialist-workflow.md).

---

## 6. Audit trail

Every claim/release/resolve writes:
- A `TicketEvent` row (existing model).
- A structlog line (`specialist_queue_claimed` / `_released` / `_resolved`)
  with `ticket_id`, `actor_id`, and the handoff package version.
- An `AuditEvent` for security review (claim is a permission-sensitive
  action).

When a resolution proposes a knowledge candidate, the candidate row carries
`source_ticket_id` so the chain `chat session → ticket → candidate →
article` is fully traversable.

---

## 7. Related docs

- [`escalation-and-live-agent-handoff.md`](./escalation-and-live-agent-handoff.md)
  — the pre-existing escalation rules; this doc layers the queue on top.
- [`knowledge-improvement-loop.md`](./knowledge-improvement-loop.md) — what
  happens to specialist resolutions after closure.
- [`ticketing-lifecycle.md`](./ticketing-lifecycle.md) — the underlying
  ticket model + SLA fields.
