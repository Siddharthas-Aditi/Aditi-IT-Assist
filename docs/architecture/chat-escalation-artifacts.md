# Chat-Escalation Artifacts

When an unresolved AI conversation is escalated to a live IT specialist, Aditi
Assist creates **two linked, immutable artifacts** so the specialist can continue
without asking the employee to repeat anything. The ticket is the parent
operational object; full context lives in linked structured records — never as a
raw chat blob in the ticket description.

```
            ┌────────────────────┐
            │      tickets        │  parent operational object
            │  (concise summary)  │
            └─────────┬──────────┘
                      │ 1
          ┌───────────┴─────────────┐
          │ 1                       │ 1
┌─────────▼──────────┐   ┌──────────▼─────────────┐
│ transcript_snapshots│◄──│  escalation_contexts   │
│ immutable ordered   │ 1 │ structured handoff +   │
│ Employee↔AI history │   │ resolution comparison  │
└─────────────────────┘   └────────────────────────┘
```

## Components

| Concern | Location |
|---------|----------|
| ORM models | `backend/app/models/escalation.py` (`TranscriptSnapshot`, `EscalationContext`) |
| Migration | `backend/alembic/versions/009_chat_escalation_artifacts.py` |
| KB-gap vocabulary | `backend/app/services/agents/kb_gap_tags.py` |
| DTOs | `backend/app/schemas/escalation.py` |
| Service | `backend/app/services/escalation_service.py` (`EscalationService`) |
| Creation wiring | `backend/app/services/agents/chat_service.py` (`_persist_and_queue` → `_create_escalation_artifacts`) |
| Specialist consumption | `backend/app/services/specialist_queue_service.py`, `backend/app/api/v1/specialist_queue.py` |
| Frontend | `frontend/src/features/specialist-chat/HandoffContextPanel.tsx` |

## Escalation trigger behavior

Nothing changes about *when* escalation happens — the workflow still escalates
only after a meaningful diagnostic attempt is exhausted, and a ticket is created
only on **explicit user confirmation** (typed "yes" after an offer, or the
"Connect with a specialist" action). See `docs/architecture/escalation-and-live-agent-handoff.md`.

What changed: at the moment the ticket is persisted (`ChatService._persist_and_queue`),
the service now also captures the two artifacts **atomically in the same
transaction** (create ticket → queue for human → snapshot transcript + context →
commit). Artifact creation is best-effort: a failure there is logged but never
blocks the ticket/handoff (the ticket already exists at that point).

Creation is **idempotent per ticket** — a second call returns the existing
`EscalationContext` and never writes a duplicate snapshot.

`handoff_triggered_by` is not a free-text summary. It preserves the exact
deterministic source that caused the handoff: `user_request`, `max_turns`,
`unclassifiable_issue`, `no_grounded_articles`, `low_retrieval_confidence`,
`failed_step_threshold`, `grounded_steps_exhausted`,
`low_resolution_confidence`, `delegation_cap`, `loop_detected`, `policy_block`,
or `other` for legacy contexts with no source trace. `specialist_queue_target`
is the supervisor-selected specialist/queue, when one exists. Both fields are
available in the queue list, full handoff package, and specialist handoff view.

## Escalation Context fields

The structured payload (`escalation_contexts`) is optimized for specialist
triage, queue routing, analytics, KB improvement, and AI evaluation:

| Group | Fields |
|-------|--------|
| Links | `ticket_id` (unique), `transcript_snapshot_id`, `chat_session_id`, `user_id`, `escalation_created_at` |
| Issue understanding | `issue_summary`, `user_problem_statement`, `detected_intent`, `category`, `subcategory`, `affected_system`, `urgency`, `sentiment` |
| AI attempts | `ai_attempted_steps[]`, `user_feedback_on_steps[]`, `kb_articles_referenced[]`, immutable `retrieval_trace`, `kb_gap_tags[]`, `ai_confidence`, `ai_resolution_status` |
| Escalation/routing | `escalation_reason`, `live_support_required`, `specialist_queue_target`, `handoff_triggered_by`, `supervisor_decision_trace`, `diagnostic_slots`, `context_version` |
| Resolution comparison (post-resolution) | `specialist_resolution_summary`, `specialist_resolution_steps[]`, `final_resolution_category`, `ai_vs_specialist_resolution_gap`, `kb_candidate_flag`, `resolution_compared_at` |

`ai_attempted_steps[]` entries are `{instruction, outcome (worked/failed/skipped/unknown), source_kb_title}`.
`kb_articles_referenced[]` entries are `{article_id, title, relevance, retrieval_confidence, version}`. `retrieval_trace` preserves the complete kept/rejected grounding trace at handoff.

## KB gap tags

A typed, versioned controlled vocabulary (`KbGapTag`) records *why* the KB could
not resolve the issue, derived deterministically by `derive_kb_gap_tags(...)`:

| Tag | Meaning |
|-----|---------|
| `no_matching_article` | Retrieval returned no KB articles. |
| `article_suggested_but_unresolved` | Articles existed and steps were tried, but the issue persisted. |
| `specialist_only_resolution_needed` | Requires a privileged action with no self-serve fix. |
| `unclear_problem_statement` | No minimally-useful problem statement was captured. |
| `repeated_escalation_pattern` | The same issue family has escalated before. |
| `missing_runbook` | A topical article existed but had no actionable steps. |
| `policy_or_access_exception` | Escalation reason indicates a policy/access exception. |

Adding a tag is a deliberate change to `kb_gap_tags.py` (`KB_GAP_TAG_VOCAB_VERSION`).

## Audit

Every package creation logs `chat.escalation_package_created`; every resolution
comparison logs `chat.escalation_resolution_compared` (both via `AuditService`,
resource type `escalation_context`). Audit failures never break the flow.

## How this supports AI & KB improvement safely

The resolution-comparison fields let a human-reviewed workflow compare *what the
AI suggested* vs *what the specialist actually did*, surface KB candidates, and
tune prompts/retrieval. There is **no uncontrolled self-learning** — only
structured data for human review (KB candidates still go through SME promotion).

See also: `transcript-snapshot-and-context-model.md`,
`../product/chat-to-ticket-handoff.md`, `../product/specialist-triage-experience.md`,
`../development/chat-escalation-qa-checklist.md`.
