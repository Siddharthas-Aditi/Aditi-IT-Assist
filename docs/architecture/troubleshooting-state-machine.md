# Troubleshooting State Machine

> Status: Active · Owner: Conversational AI · Last updated: 2026-06-17

The chat agent is a stateful troubleshooting analyst, not a one-shot Q&A. This
document describes the state it tracks and the transitions that drive
progression, loop control, and escalation.

## State container

All multi-turn state lives in
[`DiagnosticContext`](../../backend/app/services/agents/diagnostic_state.py),
serialized into `WorkflowState.diagnostic_context` and persisted across turns by
`ChatService` (it is **never** reset between turns of the same session).

Key fields (added/used by the troubleshooting flow):

| Field | Meaning |
|-------|---------|
| `normalized_system` | Canonical product/system (e.g. `outlook`). |
| `issue_category` | Broad category (e.g. `email/outlook`). |
| `issue_subtype` | Concrete subtype (e.g. `mailbox-full`). |
| `subtype_confidence` | Confidence of the subtype classification. |
| `symptom` / `exact_problem_statement` | Free-text problem signal. |
| `suggested_steps` | Step instructions already presented to the user. |
| `attempted_steps` / `failed_steps` | Steps the user tried / reported as not working. |
| `resolved_steps` | Steps that contributed to a fix. |
| `retrieval_sources_used` | Article titles already used (avoid re-grounding the same chunk). |
| `last_response_type` | `clarify` \| `resolve` \| `escalate` \| `resolved`. |
| `loop_counter` | Increments on a no-progress round (stuck-state signal). |
| `last_resolution_failed` | Set by triage when the user reports the last steps failed. |
| `issue_resolved` | Set when the user confirms the fix worked. |
| `resolution_attempts` / `clarification_count` | Counters bounding the flow. |

## Phases

`DiagnosticPhase`: `intake → clarifying → diagnosing → resolving → confirming →
escalating`. The phase is informational; routing is driven by the fields above.

## Transition rules

1. **Do not suggest a failed step again.** `_build_progression` filters out any
   step already in `suggested_steps` or `failed_steps`.
2. **Advance on failure.** When the user says "it didn't work", triage sets
   `last_resolution_failed`, moves the last batch into `failed_steps`, and does
   **not** re-clarify — the resolver presents the next NEW batch.
3. **No repeated wording.** Because batches are drawn from the remaining steps,
   the same batch cannot be re-emitted.
4. **Escalate when exhausted.** If there is no new grounded step, the resolver
   sets confidence `0.0`, records an `escalation_reason`, increments
   `loop_counter`, and routing sends the conversation to the escalation node.
5. **Close on success.** Positive feedback ("that worked") ends the turn with a
   closing message and `issue_resolved=true` (no retrieval).

## Human-like conversation flow (triage)

The agent behaves like a real analyst, not a form:

1. **Greeting / small talk** — "hi", "hello", "good morning" (when no issue is in
   flight) get a warm welcome that invites the problem, NOT "which system is
   affected?". See `_is_greeting` / `_greeting_message`.
2. **Clarify if incomplete** — vague input ("I have an outlook issue") triggers a
   playbook-guided follow-up with chips.
3. **Confirm understanding BEFORE solving** — once there's enough context, the
   agent restates the problem ("Just to confirm — your mailbox is full. Is that
   right?") and waits. Only an affirmative proceeds to the solution; a denial
   re-opens clarification. Tracked by `awaiting_confirmation` /
   `understanding_confirmed`.
4. **Topic shift resets context** — if the user switches systems (Sixth Sense →
   Outlook), `reset_issue_context()` clears the stale symptom/subtype/flags/tried
   steps so the new issue is clarified and confirmed afresh. This prevents the
   previous problem's symptom from leaking into the new one.
5. **Solve from the KB** in natural language (see chat-grounding-rules.md).
6. **Ticket only when the KB has no solution** — see routing below.

## Turn flow (graph)

```
                 ┌─────────┐
 user message →  │ triage  │
                 └────┬────┘
   greeting ─────────┼──────────────→ END (warm welcome)
   issue_resolved ───┼──────────────→ END (closing message)
   needs_clarification┼──────────────→ END (clarify OR "is that right?" confirm)
   live_agent / no cat┼──────────────→ escalate
                      ▼ (context confirmed)
                 ┌──────────┐
                 │ retrieve │  broad pool → ground_results: system-aware guard,
                 └────┬─────┘  reject cross-domain, rerank subtype
        no/weak GROUNDED┼────────────→ escalate  (below confidence floor → ticket offer)
        article         ▼
                 ┌──────────┐
                 │ resolve  │  progression: next NEW steps; track suggested
                 └────┬─────┘
   steps exhausted ───┼──────────────→ escalate → draft_ticket → END
                      ▼ (grounded next steps at or above the confidence floor)
                     END ("did this help?")
```

### Ticketing policy (important)

A ticket is logged **only** when the KB genuinely has no solution:
- retrieval grounding kept **zero** articles (nothing on-system/on-domain), or
- the resolver **exhausted** every grounded step for the issue.

A retrieval confidence below the configured floor triggers an escalation offer,
even if an article was technically retrieved; the resolver does not answer from
that weak context. The ticket draft includes
**user details** (name/email/id), the **problem statement**, and the **steps
already tried** (`nodes/ticketing.py`).

### Deterministic escalation policy

`services/agents/escalation_triggers.py` is the single pure policy function
used by graph routes and progression. It records the first applicable trigger:

- explicit human request;
- maximum conversation turns;
- no safe issue classification;
- no grounded articles;
- retrieval or resolution confidence below the configured floor;
- failed-step threshold reached; or
- grounded steps exhausted.

An escalation still only **offers** a ticket. Ticket creation remains gated on
the employee's explicit confirmation in `ChatService`.

Routing lives in [`graph.py`](../../backend/app/workflows/graph.py):
`route_after_triage`, `route_after_retrieval`, `route_after_resolution`,
`route_after_escalation`.

## Negative / positive feedback detection

Triage ([`nodes/triage.py`](../../backend/app/workflows/nodes/triage.py))
detects feedback only when steps were previously given
(`suggested_steps` present or phase `confirming`):

- Negative phrases (`didn't work`, `still not`, `not resolved`, …) → mark failed,
  advance.
- Positive phrases (`that worked`, `fixed`, …) → close out as resolved.

The frontend "Still having issues" / "Yes, it's fixed!" buttons send phrases
that match these detectors.

## Escalation → ticket → live agent

When grounded troubleshooting is exhausted (or the user asks for a human), the
agent **offers** to raise a ticket and connect a specialist. A real ticket is
created only on explicit confirmation, and always **before** the live-agent
handoff. See [escalation-and-live-agent-handoff.md](escalation-and-live-agent-handoff.md).
