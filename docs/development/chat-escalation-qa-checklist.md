# Chat-Escalation QA Checklist

Run after any change to the chat→ticket→specialist handoff. Items marked
**(Docker)** need Postgres + the full backend stack.

## Setup (Docker)

```bash
docker compose up --build -d
docker compose exec backend uv run alembic upgrade head      # applies 009
docker compose exec backend uv run python -m scripts.seed_enterprise
```

## Automated tests

- [ ] **(Docker)** `make test-backend` — includes:
  - `tests/unit/test_kb_gap_tags.py` (pure; also runs without DB)
  - `tests/unit/test_escalation_artifacts.py` (fake-session; also runs without DB)
  - `tests/api/test_specialist_queue_handoff.py` (patched service; no DB)
  - existing `tests/unit/test_chat_ticket_handoff.py` still green (backward compat)
- [ ] `make test-frontend` — includes
  `src/features/specialist-chat/HandoffContextPanel.test.tsx`
- [ ] `make lint` — backend Ruff + frontend ESLint (`--max-warnings=0`)
- [ ] `cd frontend && npx tsc --noEmit` — type-check clean

> Sandbox note: `vitest` requires the platform-native rollup binary; run frontend
> tests in your dev environment / CI, not a cross-platform sandbox. `tsc` and
> `eslint` are platform-independent and were verified.

## Migration

- [ ] **(Docker)** `alembic upgrade head` creates `transcript_snapshots` +
  `escalation_contexts` with indexes; `alembic downgrade -1` drops them cleanly.

## End-to-end manual flow (Docker)

1. [ ] Log in as `employee@aditi.com`. Start a chat that won't resolve (e.g.
   "Outlook mailbox is full and I can't send mail"); let the AI walk through
   steps until it offers escalation.
2. [ ] Confirm escalation ("Connect with a specialist"). Verify the employee sees
   the escalation-confirmation message naming the ticket + the "sharing the
   conversation" reassurance, plus the ticket-created card.
3. [ ] **DB check:** a row exists in `tickets`, `transcript_snapshots`
   (message_count > 0, ordered messages), and `escalation_contexts`
   (ai_attempted_steps, kb_gap_tags, escalation_reason populated;
   transcript_snapshot_id set; live_support_required = true).
4. [ ] **Immutability:** continue the chat after escalation; verify the existing
   snapshot's `messages`/`message_count` are unchanged.
5. [ ] Log in as `agent@aditi.com`, open the Specialist Queue, claim the ticket,
   open the live chat. Verify the handoff panel shows: summary first; attempted
   steps with outcome icons; KB gap tags; and a collapsed transcript that expands
   to role-distinct bubbles in correct order.
6. [ ] Send a message as specialist; verify live messages are stored separately
   (specialist_chat_messages) and the AI snapshot is untouched.
7. [ ] Resolve the ticket; verify `escalation_contexts.specialist_resolution_summary`
   and `resolution_compared_at` are set.
8. [ ] `POST /specialist-queue/{ticket_id}/resolution-comparison` with steps + a
   gap note; verify the fields persist and an audit event
   `chat.escalation_resolution_compared` is written.
9. [ ] **Audit:** `chat.escalation_package_created` event exists for the ticket.

## RBAC

- [ ] Employee gets 403 on `/specialist-queue/{id}/handoff-view` and
  `/resolution-comparison`.
- [ ] it_agent+ can read the handoff view and record comparisons.
