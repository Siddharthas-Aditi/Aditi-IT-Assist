# Live IT-Specialist Chat

> The human-to-human leg after AI handoff: claim a ticket, open a live chat
> with the employee, exchange messages, and end with a typed reason (with
> auto-timeout on idleness). Every transition is audited; every message is
> persisted verbatim for review, learning, and compliance.

---

## 1. Why a separate live-chat layer

The AI conversation (`SupportSession` + `Message`) and the human-to-human
follow-up share a user, a ticket, and a context window — but they have
materially different concerns:

| Concern | AI chat | Live specialist chat |
|---|---|---|
| Retention policy | shorter; analytics-tier | longer; compliance-tier |
| Audit granularity | per-turn observable | per-keystroke privileged |
| Lifecycle | turn-by-turn statelessness | session with idle timeout |
| Authoring | AI + workflow nodes | two named humans |
| Knowledge feedback | retrieval signals | specialist resolutions |

Splitting them into `SpecialistChatSession` + `SpecialistChatMessage`
avoids `SupportSession` becoming a god-table and keeps the audit/retention
boundaries clean.

---

## 2. Data model

`backend/app/models/specialist_chat.py`

### `specialist_chat_sessions`

| Column | Purpose |
|---|---|
| `id`, `created_at`, `updated_at` | base |
| `ticket_id` | FK → `tickets.id`; one active session per ticket (unique partial index) |
| `user_id`, `user_email`, `user_name` | the employee on the other end |
| `specialist_id`, `specialist_email`, `specialist_name` | the assigned specialist |
| `ai_session_id` | FK → `support_sessions.id`; full audit chain |
| `status` | `active` / `idle_warning` / `ended_by_user` / `ended_by_specialist` / `ended_by_timeout` / `ended_by_system` |
| `started_at`, `last_activity_at`, `idle_warning_at`, `ended_at` | lifecycle timestamps |
| `end_reason` | `resolved` / `user_left` / `specialist_ended` / `idle_timeout` / `session_error` |
| `ended_by` | FK → `users.id` (null when system ended) |
| `resolution_notes`, `sent_to_knowledge_review`, `knowledge_candidate_id` | post-close hooks into the KB-improvement loop |
| `idle_warning_seconds`, `idle_end_seconds` | per-session tunable thresholds (defaults 120 / 180 = 2 min warning, 3 min end) |
| `final_snapshot` | JSONB snapshot for export / learning |

Indexes:

* `ix_specialist_chat_active_per_ticket` — unique partial index on
  `(ticket_id) WHERE status IN ('active', 'idle_warning')`. Enforces the
  one-active-session-per-ticket invariant at the database layer.
* `ix_specialist_chat_specialist_active` — composite on
  `(specialist_id, status)` for fast "My Assigned" lookups.

### `specialist_chat_messages`

One row per turn. Immutable. Columns:

`id`, `session_id` (FK CASCADE), `sender_id` (null for system),
`role` (`user` / `specialist` / `system`), `content`, `system_event` (e.g.
`"idle_warning"`, `"session_started"`, `"session_ended_by_timeout"`),
`metadata_json`, `created_at`.

System messages are how the bot speaks inside the live chat: "You're now
connected with…", "It's been quiet for a couple of minutes…", "The chat
ended automatically due to inactivity." The `system_event` column lets the
frontend style them differently without parsing the content.

---

## 3. Lifecycle

```
                    ┌──────────────────┐
   ticket           │      START       │  ← POST /specialist-chat/start
   claimed ──────▶  │  status=active   │     after queue claim
                    └────────┬─────────┘
                             │
         message activity ──▶│◀── user / specialist sends message
                             │    (last_activity_at = now)
                             │
              no activity for idle_warning_seconds (default 120)
                             │
                             ▼
                    ┌──────────────────┐
                    │  IDLE_WARNING    │  ← system message:
                    │ status=idle_…    │    "Are you still there?"
                    └────────┬─────────┘
                             │
            ┌── reply ──────►│◀── no activity for idle_end_seconds (180)
            │   back to      │
            │   active       │
            │                ▼
            │       ┌──────────────────┐
            │       │ ENDED_BY_TIMEOUT │ ← end_reason=idle_timeout
            │       └──────────────────┘
            ▼
       ╔══════════════════════════════════════════════╗
       ║   Explicit end (any time before timeout):    ║
       ║                                              ║
       ║   user clicks End  → ended_by_user           ║
       ║   specialist ends  → ended_by_specialist     ║
       ║   resolve+notes    → ended_by_specialist     ║
       ║                       + optional KnowledgeCandidate
       ║   system error     → ended_by_system         ║
       ╚══════════════════════════════════════════════╝
```

Service: `app/services/specialist_chat_service.py`.
`SpecialistChatService.check_and_apply_idle(session)` is the single source
of truth for idle math. The polling endpoint calls it lazily on every GET;
a background sweeper (Phase 2) can call it from cron without duplicating
the rule.

---

## 4. API

Base: `/api/v1/specialist-chat` + `/api/v1/specialist-queue`. All require
the `ticket:assign` permission (typically `it_agent`, `it_lead`,
`it_admin`); participation is enforced per-session inside the service.

### Live chat

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/specialist-chat/start` | Begin a live session for a claimed ticket. 403 if caller isn't the assignee. |
| `GET` | `/specialist-chat/{session_id}` | Poll full state: status + transcript. Applies idle rules lazily. Both participants use the same endpoint. |
| `POST` | `/specialist-chat/{session_id}/message` | Post a message. Role derived from caller (user vs specialist). Auto-clears `idle_warning`. |
| `POST` | `/specialist-chat/{session_id}/end` | End with a typed reason. Optional `propose_knowledge_candidate` flag for SME review queue. |

### Queue (existing) + My Assigned

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/specialist-queue/` | Full queue, filterable. |
| `GET` | `/specialist-queue/{ticket_id}` | Full `HandoffPackage` for a ticket. |
| `POST` | `/specialist-queue/claim` | Atomic claim. |
| `POST` | `/specialist-queue/release` | Release back to the queue. |
| `POST` | `/specialist-queue/resolve` | Resolve via the queue path (no live chat). |
| `GET` | **`/specialist-queue/mine`** | **NEW.** Tickets assigned to me + each one's live-chat status (`live_session_id`, `live_status`, `last_activity_at`). |

---

## 5. Audit + transcript for review / learning

Every transition writes one `AuditEvent` row via `AuditService.log()`:

| Action | Resource | Severity | Metadata payload |
|---|---|---|---|
| `specialist_chat.started` | `specialist_chat_session` | info | ticket #, user id, specialist id, idle threshold |
| `specialist_chat.message_sent` | `specialist_chat_session` | info | role, message id, content SHA-256, length |
| `specialist_chat.idle_warning` | `specialist_chat_session` | info | seconds_since_activity |
| `specialist_chat.ended` | `specialist_chat_session` | info | old_status, new_status, end_reason, ended_by |

We store the message **hash** in the audit row and the message **content**
verbatim in the transcript table. This keeps the audit log compact and
PII-light while still letting reviewers pull the full conversation when
they have business need + permission. Two reasons:

1. **Audit logs are queried often, sometimes for routine analytics.**
   Bloating them with full message bodies makes scans expensive.
2. **PII redaction policy can differ** between the audit trail (retained
   for compliance, often exported to a SIEM) and the transcript (retained
   for resolution review and KB learning, possibly with shorter
   retention). Keeping the two separate gives operators the dials they
   need.

### Reading the transcript

`SpecialistChatService.get_transcript(session_id)` returns the full
ordered list of `SpecialistChatMessage` rows including the system events.
The frontend renders user/specialist/system bubbles distinctly using the
`role` and `system_event` fields.

### Feeding the learning loop

When the specialist ends with `resolved` + ticks
`propose_knowledge_candidate`, the route writes a `KnowledgeCandidate`
(source `specialist_resolution`) with the resolution notes and a
`source_ticket_id` link. SMEs review in the existing candidate queue;
nothing auto-publishes. See
[`knowledge-improvement-loop.md`](./knowledge-improvement-loop.md).

---

## 6. Idle timeout — design choices

* **Default thresholds:** 120 s warning, 180 s end (the 3-minute requirement).
* **Configurable per session** via `idle_warning_seconds` / `idle_end_seconds`
  columns. Set higher for critical incidents that may have natural pauses
  while the specialist investigates.
* **Computed, not scheduled.** No background timer per session; the service
  evaluates idleness against `last_activity_at` whenever someone polls. A
  Phase-2 background sweeper (`sweep_idle()`) can run from cron to clean up
  abandoned sessions where neither participant polls.
* **Activity resets warning state.** A user or specialist sending a message
  while in `idle_warning` flips status back to `active` and clears the
  `idle_warning_at` timestamp. The system message is preserved in the
  transcript.

---

## 7. Permissions

| Action | Roles permitted |
|---|---|
| List `/specialist-queue/mine` | `it_agent`, `it_lead`, `it_admin` |
| Start a live chat | claimer of the ticket only |
| Send a message into a live chat | the user OR the assigned specialist |
| End a live chat | the user, the specialist, or an admin |
| Read transcript (any session) | participants + `it_admin`, `it_lead`, `security_auditor` |

`security_auditor` cannot post messages or end chats; read-only for review.

---

## 8. Phase 1 vs. Phase 2

**Phase 1 (this delivery — backend complete):**

* DB models + indexes
* `SpecialistChatService` (start, send, end, idle math, sweep)
* REST endpoints
* `GET /specialist-queue/mine` "My Assigned"
* Audit hooks at every transition
* Optional knowledge-candidate proposal on resolve

**Phase 2 (next sprint):**

* Frontend live chat UI (specialist pane + employee pane).
* WebSocket push instead of HTTP polling — the polling endpoint already
  returns the same shape, so the wire upgrade is purely an additive
  channel.
* Background idle sweeper as a scheduled task (calls
  `SpecialistChatService.sweep_idle()` every 30 s).
* Migration: `004_specialist_chat.py`. The models are in code; the DDL
  ships before the Phase-2 backend deploy.
* Specialist resolution → KB candidate UI surface in the SME review queue.

**Phase 3:**

* Co-browse / screen share via the existing remote-support service.
* Idle-warning customization per user role.
* Analytics dashboards: median response time, idle-timeout rate,
  resolved-via-live-chat rate.

---

## 9. Related docs

* [`human-handoff-and-queue.md`](./human-handoff-and-queue.md) — how a chat
  reaches the queue in the first place.
* [`knowledge-improvement-loop.md`](./knowledge-improvement-loop.md) — what
  happens to specialist resolutions after close.
* [`escalation-and-live-agent-handoff.md`](./escalation-and-live-agent-handoff.md)
  — the ticket-before-handoff invariant.
* [`rollout-plan-multi-agent.md`](../development/rollout-plan-multi-agent.md)
  — the feature-flag plan around the multi-agent rollout.
