# Transcript Snapshot & Context Model

The data model behind the chat→ticket handoff. See
`chat-escalation-artifacts.md` for the surrounding flow.

## Why a snapshot at all

The AI chat transcript is currently held **in process memory**
(`ChatService._sessions`), not persisted per-turn. Rather than refactor the whole
chat hot path, we capture an **immutable copy** of the conversation at escalation
time. This satisfies the compliance/triage requirement exactly: the artifact
reflects the conversation *as it stood at handoff* and can never be altered by
later session edits, message deletions, or chat-state mutations.

> Decision: snapshot-at-escalation (not full chat persistence). **Update
> (2026-07-22):** per-turn mirroring to ``support_sessions``/``messages`` now
> ships via ``SupportSessionService`` (migration ``012``); the escalation
> snapshot remains the immutable handoff artifact. Session history APIs and
> feedback read from the durable rows; the snapshot is still taken from live
> workflow state at escalation time.

## `transcript_snapshots`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `ticket_id` | UUID FK → tickets (CASCADE) | nullable, indexed |
| `chat_session_id` | varchar(128) | the in-memory chat session id, indexed |
| `user_id` | UUID FK → users (SET NULL) | |
| `captured_at` | timestamptz | escalation time |
| `message_count` | int | |
| `messages` | JSONB | ordered array (see below) |
| `context_version` | varchar(16) | snapshot schema version (`1.0`) |
| `created_at` / `updated_at` | timestamptz | |

`messages` element shape:

```json
{ "seq": 0, "role": "employee|assistant|system", "content": "…",
  "message_type": "text|system_event|handoff|resolution|null",
  "timestamp": "ISO-8601|null" }
```

`seq` is the authoritative 0-based ordering. Roles are normalized from LangChain
message types (`human→employee`, `ai→assistant`, `system→system`).

### Immutability contract

Write-once by design, enforced at the service layer:

* `EscalationService` exposes **no update path** for `messages`.
* `extract_transcript()` returns a fresh list of fresh dicts — a **copy**, never
  a reference to the live session messages. Mutating the session afterward cannot
  reach the snapshot (unit-tested in `test_escalation_artifacts.py::test_snapshot_immutable_against_later_state_change`).
* Post-escalation **human↔human** messages are stored separately in
  `specialist_chat_messages` and never mixed into the snapshot. The specialist UI
  labels pre-escalation AI turns vs. live specialist turns distinctly.

## `escalation_contexts`

One row per ticket (`ticket_id` unique). Created with the AI-side fields at
escalation; the resolution-comparison fields are filled later at resolve time.
Links to its transcript via `transcript_snapshot_id`. Full field list in
`chat-escalation-artifacts.md`.

We deliberately do **not** populate `tickets.session_id` (an FK to the unused
`support_sessions` table). The link from ticket → conversation is:
`tickets.id` ← `escalation_contexts.ticket_id` → `transcript_snapshot_id`.

## Read path

`EscalationService.get_handoff_view(ticket_id)` assembles the
`SpecialistHandoffView` (summary first, transcript second). It degrades
gracefully: tickets with no persisted context return a view built from ticket
fields with `has_structured_context=false` rather than failing.

`SpecialistQueueService.build_handoff_package()` now also reads the persisted
context first (falling back to live session state, then ticket fields), so the
typed `HandoffPackage` on claim survives a process restart — fixing the previous
data-starved package that only ever had the ticket title.
