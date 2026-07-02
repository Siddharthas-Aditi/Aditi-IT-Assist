# Domain Model

Core entities, relationships, lifecycles, and invariants. Models live in
`backend/app/models/`; DTOs in `backend/app/schemas/`. **Change a schema or invariant
here → update this file + the relevant `docs/architecture/*.md` in the same PR.**

## Identity & access

- **User** (`auth.py`) — has ≥1 **Role** (invariant: never strip a user's last role).
  Roles: `employee`, `it_agent`, `it_lead`, `it_admin`, `security_auditor`.
- **Permissions** (`core/permissions.py`) — fine-grained, checked in services via
  `require_permissions(...)`; UI mirrors them in `frontend/src/lib/permissions.ts`.
  Examples: `ticket:assign`, `knowledge:*`, `admin:manage_users`, `feedback:*`,
  `integration:directory_read/write`, `integration:ticketing_read/write`.
- **AuditEvent** (`audit.py`) — immutable; every mutation (role change, KB
  transition, specialist-chat transition, tool call) is logged with before/after.

## Support core

- **Ticket** (`ticket.py`, `support.py`) — lifecycle + SLA, assignment, events.
  Invariants: persisted **only on explicit user confirmation**; **idempotent per
  chat session**; employees see only their own; internal notes hidden from employees.
- **Chat session / messages** (`agents/conversation_messages.py`, chat service) —
  `DiagnosticContext` carries `issue_subtype`, normalized system, intent flags,
  `suggested_steps` / `failed_steps`; persisted across turns (not reset mid-conversation).
- **RemoteSupport** (`remote_support.py`) — session, consent, audit trail.

## Live specialist chat (`specialist_chat.py`, migration 008)

- Dedicated tables; lifecycle state machine; typed end reasons (incl.
  `ended_by_timeout`). Idle policy: 7-min warning + 2-min grace (configurable).
  Full transcript persisted + resumes on refresh. Typing state is ephemeral in-memory
  (8s TTL), never persisted / audited.
- **SpecialistQueue** — DB-level atomic claim; typed `HandoffPackage`.

## Escalation artifacts (`escalation.py`, migration 009) — immutable by contract

- **TranscriptSnapshot** (`transcript_snapshots`) — write-once, ordered Employee↔AI
  history captured at escalation. No update path exists; `extract_transcript()`
  returns a copy. Post-escalation human↔human messages stay in
  `specialist_chat_messages` and are **never** mixed in.
- **EscalationContext** (`escalation_contexts`, one per ticket) — structured handoff:
  issue summary, problem statement, intent, category/subtype, affected system,
  `ai_attempted_steps[]`, `kb_articles_referenced[]`, `kb_gap_tags[]`, `ai_confidence`,
  `ai_resolution_status`, `escalation_reason`, routing, `supervisor_decision_trace`,
  `diagnostic_slots`, + resolution-comparison fields filled at resolve time.
- Invariant: **never** store a raw chat blob in the ticket description — link to
  these artifacts. Improvement loop is **human-reviewed only**.

## Knowledge

- **KnowledgeArticle** (`knowledge.py`) — lifecycle:
  `draft → in_review → approved → published → archived`. Chat retrieves **published
  only**. Each article's `subcategory` MUST equal a real subtype from
  `subtype_classifier.known_subtypes(category)`. No monolithic "all issues" articles.
  Publish → index; archive → de-index; both snapshot a version.
- **KnowledgeChunk + embedding** (migration 006) — pgvector; chunk `indexed` only
  when it actually has a vector, else `pending`.
- **KnowledgeCandidate** (`knowledge_candidate.py`, migration 007) — review-gated
  promotion; six signal sources; never auto-published.
- **Ingestion** (`ingestion.py`, migration 004) — `ExtractionCandidate` is the
  stable contract (bump `SCHEMA_VERSION` to change); never auto-publishes.

## Feedback (`feedback.py`, migration 005)

- **conversation_feedback** (one per session per user, idempotent upsert) +
  **message_feedback** (thumbs per message). `quality_bucket` and `review_flag`
  computed at write time — never re-derived in queries. No auto (un)publish of KB.

## Migrations

`002_enterprise_upgrade` → `003_knowledge_management` → `004_document_ingestion` →
`005_feedback` → `006_add_knowledge_chunks_embedding` → `007_knowledge_candidates` →
`008_specialist_chat` → `009_chat_escalation_artifacts`. Next revision = `010_*`.
See skill `skills/playbooks/database-migrations.md`.
