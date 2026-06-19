# Conversational Intent Layer

> How Aditi IT Assist tells **what the user is doing** in this turn — independent of
> *which* IT issue they're describing.
>
> **Architecture: hybrid LLM-first with deterministic safety overrides.**
> An LLM understands open-ended phrasings ("unable to connect to internet",
> "I am not getting new mails", "yeah go ahead and route it to IT").
> A deterministic keyword layer pins the bug-class fixes (NEW_TOPIC,
> ESCALATE_REQUEST) so safety guarantees can't regress when the LLM changes.

---

## Why a separate layer

The chat workflow used to conflate three different signals:

1. **What IT issue is this?** — entity normalization + subtype classifier.
2. **Did the steps work?** — positive/negative feedback detection.
3. **What's the user *doing* in this turn?** — confirm, deny, ask for a human,
   switch topic, end the chat, small-talk.

Mixing (3) into (2) and (1) produced the class of bugs that motivated this
layer. The reproducer: after the agent resolved a "mailbox full" issue, the
user typed *"I have another problem"*. The workflow had no rule for "switch
topic", so it kept the active diagnostic context, ran retrieval against the
mailbox-full subtype, found no remaining steps, routed to escalation, and the
loose `"help" in user_message`-style match misread the message as
*escalation confirmed*. Ticket `ITA-000007` was created without the user ever
confirming they wanted a ticket.

The fix is to surface conversational intent as a first-class, typed, versioned
signal that all workflow nodes read from.

---

## Modules

Two modules behind one return shape:

### Understanding layer (LLM-first) — `agents/llm_intent.py`

Public entry point: `classify_intent_with_llm(...)`. Returns the same
`IntentClassification` as the keyword layer. Calls the LLM with a strict
JSON schema constrained to the same `ConversationIntent` enum.

When it falls back to keywords:

* LLM not configured (`llm.is_available is False`)
* LLM call times out (4 s default)
* LLM call errors
* LLM returns an unknown intent OR confidence below `_LLM_CONFIDENCE_FLOOR`
  (0.5 default)
* Keyword layer detected a safety-priority intent (NEW_TOPIC,
  ESCALATE_REQUEST) — keyword always wins for those, even if the LLM picks
  something else. This is how the bug-class fixes stay pinned regardless
  of model changes.

The audit trail records `matched="llm:<rationale>"`,
`matched="keyword:<phrase>"`, or `matched="hybrid:<details>"` so analytics
can slice by path.

### Safety layer (deterministic) — `agents/intent_classifier.py`

Public entry point: `classify_intent(...)`. Pure-function rule matcher,
no LLM call. Used as:

1. Fallback when the LLM path can't serve a result.
2. **Safety override** for `NEW_TOPIC` and `ESCALATE_REQUEST` — these
   keyword matches win over the LLM unconditionally. This is what guarantees
   no future model regression can re-introduce the ITA-000007 /
   ITA-000006 bugs.
3. The source of truth for unit tests and golden conversations (the
   versioned rule set is what we pin against).

Both functions take the same context flags (`has_active_issue`,
`awaiting_confirmation`, `steps_given`, `issue_resolved`) and return the
same dataclass. Callers don't need to know which path served the answer.

### What stays deterministic forever

Safety-critical decisions never rely on LLM judgement:

* Ticket creation requires `escalation_offered_in_session=True` OR
  explicit `ESCALATE_REQUEST` (intent_classifier whole-word rule).
* Web-fallback policy is registry-driven, not LLM-suggested.
* KB writes still require human SME promotion.
* The supervisor's routing decisions are a pure function over typed inputs.

The LLM gets to interpret *what the user said*; the workflow decides
*what the system is allowed to do*.

---

## Intent taxonomy

| Intent | What it means | Workflow effect |
|---|---|---|
| `NEW_TOPIC` | User is switching to a different IT issue mid-conversation. | Reset the diagnostic context, ask "what's the new issue?" — do **not** ticket. |
| `CONFIRM` | "Yes" to the agent's pending yes/no question. | Advance the confirmation state. |
| `DENY` | "No, that's not it" to the pending yes/no question. | Re-open clarification. |
| `NEGATIVE_FEEDBACK` | The steps we gave did **not** fix it. | Mark the batch failed, present the next batch (do not repeat). |
| `POSITIVE_FEEDBACK` | The steps fixed it. | Close out with a warm acknowledgment; mark `issue_resolved`. |
| `ESCALATE_REQUEST` | "Connect me with a human / specialist / agent / ticket." | Route to escalation **with** `escalation_confirmed=True`. This is the **only** non-API path that may create a ticket. |
| `GREETING` | "Hi", "hello", etc. — only when no issue is in flight. | Warm greeting; ask what's going on. |
| `GRATITUDE` | Pure "thank you" after help was given. | Close warmly; no new triage. |
| `REPEAT_OR_SIMPLIFY` | "Can you explain again", "in plain English". | Re-render the current step batch in simpler language. |
| `SMALL_TALK` | "How are you", "lol", "ok cool" — content-free filler. | Acknowledge briefly; nudge back to the issue. |
| `CONTINUE` | Default. The message contributes to the active flow. | Triage handles it as a normal diagnostic turn. |

### Priority

When two intents match the same turn (e.g. *"yes, connect me to a human"*
matches both `CONFIRM` and `ESCALATE_REQUEST`), the higher-priority intent
wins. The priority order, encoded in `_PRIORITY`, is:

```
ESCALATE_REQUEST > NEW_TOPIC > NEGATIVE_FEEDBACK > POSITIVE_FEEDBACK
> REPEAT_OR_SIMPLIFY > DENY > CONFIRM > GRATITUDE > GREETING
> SMALL_TALK > CONTINUE
```

This is **the contract**: changing it requires a version bump and a review of
the golden-conversation suite.

### Context flags

Several intents are only meaningful at certain points in the conversation —
the classifier honors that:

- `awaiting_confirmation` gates `CONFIRM`/`DENY`. A bare "yes" at session
  start is `CONTINUE`, not `CONFIRM`.
- `steps_given` gates `POSITIVE_FEEDBACK`/`NEGATIVE_FEEDBACK`. We don't
  interpret a fresh message as "the steps didn't work" when we haven't given
  any yet.
- `has_active_issue` demotes `GREETING` to `CONTINUE` — a "hey" mid-flow is
  not a session restart.
- `issue_resolved` promotes longer follow-up messages to `NEW_TOPIC` — after a
  fix is confirmed, a non-thanks 4+-token message almost always introduces a
  new request.

---

## Workflow wiring

```
user message
    │
    ▼
classify_intent(message, …context flags…)
    │
    ├── NEW_TOPIC          → diag_ctx.reset_issue_context(); ask what's new
    ├── ESCALATE_REQUEST   → escalation_confirmed = True; ticket path
    ├── POSITIVE_FEEDBACK  → resolved_message()
    ├── NEGATIVE_FEEDBACK  → mark_last_batch_failed(); advance to next batch
    ├── REPEAT_OR_SIMPLIFY → re-render current batch in simpler language
    ├── DENY               → re-open clarification
    ├── CONFIRM            → understanding_confirmed = True; proceed to fix
    ├── GREETING           → greeting_message()
    ├── GRATITUDE          → gratitude_close_message()
    ├── SMALL_TALK         → brief ack + nudge to the issue
    └── CONTINUE           → triage runs normally (entity + slot extraction)
```

The triage node calls `classify_intent` **before** any other rule (greeting
heuristics, gratitude heuristics, etc. — those legacy heuristics are now
removed in favor of the classifier so all routing rules live in one place).

---

## Ticketing invariant

A ticket is created in **exactly two** places:

1. `ChatService._handle_ticketing` — when `escalation_confirmed=True`, set
   only by the workflow when the user's intent was `ESCALATE_REQUEST` (or the
   user explicitly confirmed an escalation offer).
2. `ChatService.request_live_agent` — when the user clicks "Connect with a
   specialist" in the UI, hitting `POST /chat/request-live-agent`.

No other code path may set `escalation_confirmed=True` and no node persists a
ticket directly. The escalation node may still *offer* a ticket (with an
explanatory message and a quick-reply chip) — but offering and creating are
strictly different operations.

---

## Versioning

`CLASSIFIER_VERSION` (currently `1.0.0`) is bumped whenever the rules or
priorities change. Golden-conversation tests record the version they were
authored against; analytics joins on intent classification carry the version
so behavior shifts are traceable.

---

## Adding a new intent

1. Add the enum value to `ConversationIntent`.
2. Add the keyword set and detector function.
3. Insert it into `_PRIORITY` at the right precedence.
4. Add unit tests covering: a positive match, a near-miss, negation if
   relevant, and any context-flag interactions.
5. Bump `CLASSIFIER_VERSION`.
6. Update this document and the workflow-wiring table.
7. If the new intent changes a routing decision, extend
   `docs/development/golden-conversations.md` with at least one conversation
   that exercises it.

---

## Related docs

- `docs/architecture/intent-analysis.md` — IT-issue intent (login, OTP, locked
  account, error, etc.). Orthogonal to this layer.
- `docs/architecture/troubleshooting-state-machine.md` — how feedback signals
  drive the resolution loop.
- `docs/architecture/escalation-and-live-agent-handoff.md` — the ticket
  lifecycle and the *offer vs. create* boundary.
- `docs/development/golden-conversations.md` — canonical conversation fixtures
  that exercise this layer.
