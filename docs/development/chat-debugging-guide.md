# Chat Debugging Guide

> Status: Active · Owner: Conversational AI · Last updated: 2026-06-17

How to diagnose a wrong, repeated, or low-quality chat answer.

## What to inspect

Every chat turn produces structured signals. For a given turn collect:

1. **Detected system** — `diagnostic_context.normalized_system`
2. **Detected subtype** — `issue_subtype` + `subtype_confidence`
3. **Selected playbook** — category → `get_playbook(category)`
4. **Retrieved (kept) chunks** — `retrieval_trace.kept`
5. **Rejected chunks** — `retrieval_trace.rejected` (with reasons)
6. **Confidence components** — `confidence_breakdown`
7. **Loop/escalation** — `loop_counter`, `escalation_reason`,
   `suggested_steps`, `failed_steps`

## Where to find them

### A. Admin debug panel (no code)

Sign in as an IT/admin role (`it_agent`, `it_lead`, `it_admin`,
`security_auditor`). The API attaches a `debug` object to the chat response
(`ChatDebugInfo`) and the chat bubble renders a collapsible **"Debug trace
(internal)"** panel under each assistant message. Employees never receive this
field (data isolation enforced in `api/v1/chat.py`).

### B. Structured logs

Search logs by event:

| Event | Emitted by | Key fields |
|-------|-----------|------------|
| `subtype_classified` | triage | `subtype`, `confidence`, `matched` |
| `resolution_marked_failed` | triage | `failed_count`, `subtype` |
| `knowledge.searched` (audit) | retrieval | `subtype`, `grounding` (full trace), `candidates`, `results_count`, `confidence` |
| `resolution.generated` (audit) | resolution | `confidence_breakdown`, `steps_count`, `remaining_after` |
| `resolution.exhausted` (audit) | resolution | `steps_tried`, `loop_counter` |
| `escalation.triggered` (audit) | escalation | `reason` |

The audit entries accumulate in `WorkflowState.audit_trail`.

## Triage tree for common symptoms

### "Answer is from the wrong topic" (cross-domain)
- Check `retrieval_trace.rejected` — was the wrong-family article rejected?
  - If it was **kept**, the issue's `issue_category` family is wrong → check
    triage entity normalization / classification.
- Check `issue_subtype`. If `null`, the subtype classifier didn't fire → the
  resolver fell back to generic steps. Add/adjust rules in
  `subtype_classifier.py`.

### "Wrong subtype within the right topic"
- Check `subtype_classifier.classify_subtype(text, category)` for the user's
  text. Adjust keywords / anti-keywords. Multi-word phrases score higher.
- Confirm a KB article exists whose `subcategory` equals the subtype.

### "It repeats the same steps after I say it didn't work"
- Confirm the failure phrase matches `_NEGATIVE_FEEDBACK` in `triage.py`.
- Confirm `diagnostic_context.failed_steps` grows turn over turn.
- Confirm `suggested_steps` is persisted (ChatService must not reset
  `diagnostic_context`).

### "Confidence looks wrong"
- Read `confidence_breakdown`: `grounding`, `subtype_match`,
  `retrieval_relevance`, `playbook_fit`, and the penalties. A high final score
  is impossible without `grounding > 0`. See
  [chat-grounding-rules.md](../architecture/chat-grounding-rules.md).

### "It escalates too early / too late"
- `route_after_resolution` escalates when `resolution_confidence < 0.35` or the
  resolver flagged exhaustion (phase `escalating`). Tune the article step lists
  or the confidence weights (`confidence._WEIGHTS`).

## Reproducing locally

The retrieval node hits the DB, but the grounding + resolution core can be
exercised directly against the YAML KB (the dev fallback). See
`backend/tests/unit/test_outlook_mailbox_full_flow.py` for the pattern: load
articles via `get_articles_by_category`, run `ground_results`, then
`resolution_node` with `get_llm_service` patched unavailable.

## Related
- [chat-grounding-rules.md](../architecture/chat-grounding-rules.md)
- [troubleshooting-state-machine.md](../architecture/troubleshooting-state-machine.md)
- [retrieval-guardrails.md](../architecture/retrieval-guardrails.md)
- [golden-conversations.md](./golden-conversations.md)
