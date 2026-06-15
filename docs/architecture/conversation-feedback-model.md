# Feedback Data Model

Two tables implement the post-chat feedback loop.

---

## `conversation_feedback`

One row per support session per employee (unique on `conversation_id + submitted_by_user_id`).

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `conversation_id` | UUID FK → `support_sessions.id` | Session being rated |
| `ticket_id` | UUID FK → `tickets.id` (nullable) | Linked ticket |
| `submitted_by_user_id` | UUID FK → `users.id` | Employee who submitted |
| `helpful` | Boolean (nullable) | Step 1 answer |
| `resolved` | Boolean (nullable) | Step 2 answer |
| `rating` | Integer 1–5 (nullable) | Step 3 answer |
| `comment` | Text (nullable) | Step 4 answer |
| `submitted_at` | Timestamptz | When submitted |
| `channel` | String | `web_chat` (default) |
| `feedback_source` | Enum | `inline_chat` / `ticket_page` / `followup` |
| `support_mode` | Enum | `ai_only` / `ai_plus_live_agent` / `live_agent_only` |
| `agent_user_id` | UUID FK → `users.id` (nullable) | Assigned agent |
| `escalation_occurred` | Boolean | Auto-derived from session status |
| `category` | String (nullable) | Copied from session |
| `subcategory` | String (nullable) | Copied from session |
| `knowledge_article_ids` | JSONB (nullable) | Article UUIDs cited in session |
| `session_duration_seconds` | Integer (nullable) | Auto-computed |
| `first_response_time_seconds` | Integer (nullable) | Auto-computed |
| `sentiment_label` | String (nullable) | Set by async analytics job |
| `quality_bucket` | Enum | `positive` / `neutral` / `negative` — computed at write |
| `review_flag` | Boolean | Auto-set when `rating≤2` or `resolved=False` or `helpful=False` |
| `review_flag_reason` | String (nullable) | Human-readable reason |
| `created_at`, `updated_at` | Timestamptz | |

### Quality Bucket Logic

```
POSITIVE  = helpful=True AND resolved=True AND (rating is None OR rating >= 4)
NEGATIVE  = helpful=False OR resolved=False OR rating <= 2
NEUTRAL   = everything else (at least one positive, no negative signals)
```

### Review Flag Logic

`review_flag = True` when:
- `rating ≤ 2`, OR
- `resolved = False`, OR
- `helpful = False`

---

## `message_feedback`

One row per message per employee (unique on `message_id + submitted_by_user_id`).

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `message_id` | UUID FK → `messages.id` | Message being reacted to |
| `session_id` | UUID FK → `support_sessions.id` | Parent session |
| `submitted_by_user_id` | UUID FK → `users.id` | Reactor |
| `helpful` | Boolean | True = thumbs up, False = thumbs down |
| `comment` | Text (nullable) | Optional context (thumbs down) |
| `knowledge_article_ids` | JSONB (nullable) | Articles surfaced in message |
| `submitted_at` | Timestamptz | |
| `created_at`, `updated_at` | Timestamptz | |

---

## Alembic Migration

File: `alembic/versions/005_feedback.py`
Revision: `005_feedback` → revises `004_document_ingestion`

Creates both tables and the three enum types:
`support_mode_enum`, `feedback_source_enum`, `quality_bucket_enum`.

---

## ORM Model File

`backend/app/models/feedback.py` — imported in `models/__init__.py`
