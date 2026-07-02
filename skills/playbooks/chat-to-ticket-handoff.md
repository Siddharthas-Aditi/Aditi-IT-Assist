# Playbook: Chat → Ticket → Live Handoff

**When**: changing escalation logic, ticket creation from chat, or the handoff artifacts.

## Key files
`services/agents/chat_service.py` (`_handle_ticketing`, `request_live_agent`,
`_persist_and_queue`, `_create_escalation_artifacts`), `agents/escalation_policy.py`,
`workflows/nodes/{escalation,ticketing}.py`, `services/escalation_service.py`,
`models/escalation.py`. Docs: `docs/architecture/escalation-and-live-agent-handoff.md`,
`chat-to-live-handoff.md`, `chat-escalation-artifacts.md`,
`transcript-snapshot-and-context-model.md`.

## Invariants (do not break)
1. **Gate first**: `handoff_context_sufficient` must pass before any human handoff or
   ticket creation. If not, gather a problem statement — do not escalate.
2. **Confirmation-gated persistence**: a real ticket persists only on explicit user
   confirmation ("Connect with a specialist" / typed "yes"), and always **before** the
   human handoff. **Idempotent per session.**
3. **Service-layer persistence**: tickets are persisted in `ChatService`, not in
   workflow nodes; `ticketing.py` only builds a draft + offer.
4. **Immutable artifacts**: create a write-once `TranscriptSnapshot` + one
   `EscalationContext` per ticket. Never mutate the snapshot; never mix post-escalation
   human↔human messages in; never dump raw chat into the ticket description.
5. Tell the employee their conversation is being shared so they don't repeat themselves.
6. Improvement (resolution-comparison, KB gap tags) is **human-reviewed only**.

## Validate
Run `test_escalation_*` unit/api tests, the golden conversations, and
`docs/development/chat-escalation-qa-checklist.md`. Confirm no duplicate ticket on repeat
confirmation, and that the specialist sees summary-first context.

## Checklist
- [ ] Gate enforced at both call sites; no early connect.
- [ ] Ticket confirmation-gated + idempotent; persisted in service layer.
- [ ] Snapshot immutable; context complete; no raw chat in ticket.
- [ ] Tests + golden convos + QA checklist pass.
