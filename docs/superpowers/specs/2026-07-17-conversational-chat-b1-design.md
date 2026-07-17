# Sub-project B1 — Conversational, One-Step-at-a-Time Chat

**Date:** 2026-07-17
**Status:** Approved design (pending user spec review)
**Part of:** production-readiness engagement, sub-project B (B1 of B1/B2)

## Problem

Employees experience the troubleshooting reply as a "KB dump," not a specialist
talking. Three causes (verified):

1. The resolver emits a **3-step batch** each turn (`resolution.py::_BATCH_SIZE = 3`)
   and the frontend renders it as a bordered **"Resolution Steps" timeline card**
   (`StepTimeline.tsx`, gated on `steps.length > 1`), with the prose literally
   pointing at it ("I've laid out the exact steps for you just below").
2. There is **no one-step-at-a-time guided flow** — the closest is a batch that
   advances 3-at-a-time across turns.
3. **Escalation and ticketing messages are 100% canned f-strings**
   (`escalation.py`, `ticketing.py`, and the post-create banner in
   `chat_service.py`) — they never use the LLM, so the operational moments read
   most robotically of all.

## Goal

The agent guides the employee like a human IT specialist: **one concrete step at a
time, in natural prose that includes the exact click-path**, waits for the
employee to try it, then advances. After a small number of unsuccessful steps it
**proactively offers a live specialist**. Escalation and ticketing messages are
LLM-phrased with the same warm persona. No behavioral guardrail changes.

## Non-goals

- Web search / specialist handoff enrichment — that is **B2** (separate spec).
- No change to grounding/subtype/confidence logic, escalation *gating*
  (`handoff_context_sufficient`), or ticket persistence/idempotency.
- No new frontend framework/components beyond adjusting how the single-step reply
  renders and keeping the existing confirm buttons.

## Design decisions (user-approved)

- **Truly one step per turn**, BUT **escalate after 2–3 consecutive misses**
  (configurable; default 3) instead of walking every remaining step.
- **Concrete click-paths live in the prose** (e.g. "open Settings → Accessibility
  → Keyboard…"), not a separate card.

## Units of work

### 1. One-step delivery (`backend/app/workflows/nodes/resolution.py`)
- Introduce `RESOLUTION_STEP_BATCH_SIZE` config (default **1**) replacing the
  hardcoded `_BATCH_SIZE = 3`. The existing progression memory
  (`_build_progression` + `DiagnosticContext.suggested_steps/failed_steps` +
  `is_step_exhausted_or_seen`) already advances per batch, so batch=1 yields
  one-at-a-time with no new state machine.
- Update `RESOLUTION_PROMPT` / `RESOLUTION_SYSTEM_PROMPT` so that, for a
  single step, the LLM weaves the step's **instruction AND `details` (the exact
  click-path)** into 1–3 natural sentences and ends by asking the user to try it
  and report back. (The prompt already forbids numbered lists; extend it to
  explicitly include the concrete path in prose.)
- Update the deterministic fallback `_format_concise_response` for the single-step
  case: no "laid out below" pointer; state the one action + its path in a sentence.

### 2. Proactive escalation after N misses (`resolution.py` + `diagnostic_state.py`)
- Add `RESOLUTION_MISS_ESCALATE_THRESHOLD` config (default **3**).
- Track **consecutive unsuccessful steps** (reuse `resolution_attempts` /
  `failed_steps`; the exact counter is chosen in the plan). When the count reaches
  the threshold *before* steps are naturally exhausted, route to the escalation
  offer instead of presenting the next step.
- Natural exhaustion (no steps left) still escalates, as today. Both paths use the
  LLM-phrased escalation message (unit 3).

### 3. LLM-phrased escalation (`conversation_messages.py` + `escalation.py`)
- Add persona generators mirroring the existing pattern (async, `_PERSONA`,
  temperature ~0.8, deterministic fallback): `generate_escalation_offer(diag_ctx,
  reason)` and `generate_escalation_confirmed(diag_ctx)`.
- Wire `escalation_node` to call them, replacing the inline f-strings at
  `escalation.py:58-61` and `_build_escalation_message`. The *reason* and
  *handoff summary* logic is unchanged — only the user-facing wording is LLM'd.
- Fallbacks preserve today's wording so no-LLM behavior is unchanged.

### 4. LLM-phrased ticketing (`conversation_messages.py` + `ticketing.py` + `chat_service.py`)
- Add `generate_ticket_offer(diag_ctx, priority)` and
  `generate_ticket_created(ticket_number, diag_ctx)` generators (persona +
  fallback).
- Wire the ticket *offer* message in `ticketing.py:60-73` and the post-create
  confirmation banner in `chat_service.py:324-332` to use them.
- Ticket **content** (title/description) and persistence/idempotency are unchanged
  — only the conversational wording is LLM'd. Ticket numbers still appear in the
  confirmation (the persona's "don't mention ticket numbers" rule is overridden
  here intentionally — the number is the whole point of the confirmation).

### 5. Frontend single-step rendering (`frontend/src/features/chat/`)
- With one step, `StepTimeline` already does not render (gated on `>1`). Verify the
  single-step reply renders cleanly as conversational prose in `ChatBubble.tsx`,
  and that the "That worked / Still not working / Talk to a specialist" buttons
  (`ResolutionConfirm.tsx`, driven by `conversation_phase === 'confirming'`) still
  appear. Remove the now-misleading `proseSingleStep` numbered-pill special case
  if it conflicts with plain conversational prose. `tsc` + eslint clean.

## Data flow (unchanged control flow, new pacing)

```
turn → triage → retrieve → resolve
  resolve: _build_progression → take 1 step → LLM prose (step + click-path) → CONFIRMING
  user "still not working" → mark step failed; misses += 1
     misses < threshold AND steps remain → present next single step
     misses >= threshold OR steps exhausted → escalation offer (LLM-phrased)
  user "that worked" → resolved (existing)
  user confirms escalation → ticket (explicit) → LLM-phrased confirmation
```

## Error handling / guardrails

- LLM only phrases. Steps come only from grounded KB (unit 1 changes batch size,
  not the source). If the LLM is unavailable, every generator falls back to a
  deterministic template — behavior identical to today except one-step pacing.
- Escalation gating (`handoff_context_sufficient`) and ticket
  explicit-confirmation + idempotency are untouched (`known-risks.md` #2).
- No hallucinated advice: the prose is constrained to the single approved step
  (`known-risks.md` #1).

## Testing

- **Unit (resolution):** with batch=1, turn 1 presents step 1 only; on
  "still not working" turn 2 presents step 2 (not repeating step 1); after
  `RESOLUTION_MISS_ESCALATE_THRESHOLD` misses the flow routes to the escalation
  offer; natural exhaustion escalates. Single-step response payload has exactly
  one `resolution_step`.
- **Unit (messages):** `generate_escalation_offer/confirmed` and
  `generate_ticket_offer/created` return LLM text when available and the exact
  fallback string when `llm.is_available` is False (inject a fake LLM service).
- **Regression:** existing golden-conversation, workflow-node, and chat-flow tests
  stay green (adjust any that assert the old 3-step batch or old canned strings —
  update expectations, don't weaken assertions).
- **Frontend:** existing ChatBubble/ResolutionConfirm tests stay green; add/adjust
  a test that a single-step bot message renders prose + confirm buttons and no
  "Resolution Steps" card.
- **Manual:** walk a laptop issue end-to-end (one step per turn, click-paths in
  prose, escalate after 3 misses, LLM-phrased escalation + ticket confirmation).

## Acceptance criteria

1. Default flow presents one step per turn with the concrete click-path in prose;
   no "Resolution Steps" card for the normal flow.
2. After the configured consecutive misses, the agent proactively offers a live
   specialist; natural exhaustion still escalates.
3. Escalation and ticketing messages are LLM-phrased with deterministic fallbacks.
4. Grounding/escalation-gating/ticket-idempotency guarantees unchanged (tests
   prove it).
5. Backend `ruff` + `pytest` green; frontend `tsc` + eslint + vitest green.

## Risks (`memory/known-risks.md`)

- #1 grounded retrieval, #2 escalation/ticket persistence — both explicitly
  preserved; tests assert no regression.
- Turn count: truly-one-at-a-time can be many turns; mitigated by the
  escalate-after-N-misses rule.
- Config contract: new settings are additive with safe defaults.
