# Fluid, Grounded Chat — Natural IT-Specialist Conversation (Sub-project A)

**Date:** 2026-07-23
**Status:** Approved design — ready for implementation plan
**Scope:** The employee-facing AI chat *conversation flow*. Make it feel like a real IT
specialist instead of a rigid scripted state machine — **without** loosening the grounding
that keeps factual IT advice from being hallucinated.

---

## 1. Problem

The chat pipeline works and is safely grounded, but it *feels* robotic — it does not read
like a competent human IT specialist talking to an employee. The unnaturalness is
**flow-driven**, not tone-driven. Three scripted mechanics cause it:

1. **Forced "confirm understanding" gate.** Triage restates its understanding and *waits for
   an explicit yes/no* before giving any solution (`DiagnosticContext.awaiting_confirmation`
   / `understanding_confirmed`; triage.py:120-125, 719-843). Every issue costs an extra
   round-trip: "Got it — just to confirm: X. Is that what you're experiencing?" → user must
   answer "yes" → only then help.
2. **Templated, repeating clarifying questions.** Playbook-slot questions can repeat verbatim
   (observed: "What's happening with the application?" asked twice). A real specialist never
   re-asks the same thing.
3. **One-step-at-a-time delivery.** The resolution prompt forces "the SINGLE next step; do not
   preview later steps" (resolution.py:37), so even a simple fix dribbles out over multiple
   turns.

Illustrative failure (employee asked to install Docker Desktop): the bot ran the
troubleshooting playbook, re-asked "What's happening with the application?" twice, forced a
confirm, then delivered generic, irrelevant steps one at a time ("close all instances and
restart" → "run as administrator" → "Intune reinstall"). A real specialist would answer
directly and naturally.

### Goals
- The conversation reads like a knowledgeable IT specialist: understands the issue, asks only
  what's genuinely needed (and never repeats), and gives the relevant help in a natural,
  coherent reply.
- Preserve the grounding guarantee: **factual fixes still come only from the KB**; genuinely
  unknown → honest "let me bring in a specialist," never fabricated steps.

### Non-goals
- Do **not** let the LLM answer factual IT questions from its own general knowledge (that was
  explicitly ruled out — grounding stays strict).
- Do **not** rearchitect into a full LLM-driven agent; keep the LangGraph node pipeline.
- No new request-type/"provisioning vs troubleshooting" taxonomy in this sub-project (separate
  future work). We only make the *existing* flow fluid.

---

## 2. Design decisions (agreed) — "Grounded but fluid"

**Principle:** the LLM owns *how the conversation feels*; the KB still owns *what facts are
stated*.

### A. Drop the forced confirmation gate
Remove the mandatory "restate understanding → wait for yes/no → then solve" round-trip. When
the subtype is confidently classified and grounded steps exist, **help immediately**, folding
the understanding into the first sentence of the helpful reply ("Sounds like your mailbox is
full — the quickest fix is…"). Retain a confirm **only** when the input is genuinely ambiguous
(no confident subtype). Mechanically: `awaiting_confirmation` is set only on the
genuinely-ambiguous branch; the confident branch skips straight to grounded resolution.

### B. LLM-generated, context-aware clarifying — never repeat
When clarification is genuinely needed (can't determine subtype / not enough to help), the
question is generated from the actual conversation (reuse the existing `generate_*` /
`evaluate_clarify_or_answer` LLM helpers) and must reference what the user already said. Track
asked questions on `DiagnosticContext` and de-duplicate: never emit a question whose normalized
form was already asked. Keep the existing `clarification_count` / `max_clarifications` cap.

### C. Present grounded steps naturally, not one-at-a-time
Drop the "single next step only" instruction. The specialist voice gives the coherent set of
relevant steps for the matched subtype in one natural reply (still **only** the KB's approved
steps; still tracked in `suggested_steps`/`failed_steps` so a follow-up "still not working"
advances to genuinely new steps and never repeats a failed batch).

### D. Honest on no / weak grounding match
When `grounding.ground_results` yields no confident article for the issue (the Docker case: a
too-generic "software" article must not be dressed up as a fix), the bot says so like a real
specialist and offers a human — **no fabricated generic steps**. This is a confidence/relevance
threshold on the grounded result, not a new behavior surface.

### E. Context carry-over + specialist tone
Feed the recent conversation turns + known diagnostic facts into the resolution/clarify prompts
so replies read like someone who has been in the conversation (acknowledge specifics, don't
re-ask answered things). Tone stays warm/competent (the prompt already aims for this).

### F. Frontend — de-script the affordances
The rigid "Yes, that's right / No, not quite" quick-replies (which exist to serve the forced
confirm gate) become **contextual/optional**: shown only when the bot actually asks something,
not as a mandatory confirm step. Free-text remains first-class. (`quick_replies` in
`ChatResponse`; `SupportChatPage.tsx`.)

---

## 3. Architecture & touchpoints

Change is contained to the conversational surface; the grounding spine is untouched.

**Backend (workflow):**
- `app/workflows/nodes/triage.py` — the main change. Route confident-subtype turns straight to
  resolution (skip the confirm gate); set `awaiting_confirmation` only on the ambiguous branch;
  generate clarifying questions via the LLM helpers with de-dup.
- `app/workflows/nodes/resolution.py` — remove the "single next step" constraint; group the
  matched subtype's remaining steps into one natural reply; keep `_build_progression`'s
  tried-step memory; add the weak-match honesty branch (offer specialist instead of generic
  steps).
- `app/workflows/graph.py` / orchestrator routing — relax the routing conditions that depend on
  the confirm gate so the graph can go intake → (clarify | resolve) without a forced confirm hop.

**Backend (state):**
- `app/services/agents/diagnostic_state.py` `DiagnosticContext` — add `asked_questions:
  list[str]` (normalized) for repeat-suppression; keep `awaiting_confirmation` (now set only
  when ambiguous), `clarification_count`, `phase`. The `DiagnosticPhase` enum stays; the
  CONFIRMING-understanding phase becomes optional rather than mandatory.

**Backend (prompts):** rewrite the triage-clarify and resolution "humanizer" prompts per A/C/E.
No change to grounding, subtype classification, or confidence code.

**Frontend:** `SupportChatPage.tsx` (+ any quick-reply rendering) for F.

**Explicitly preserved (do not modify behavior):** `subtype_classifier.py`, `grounding.py`
`ground_results`, `confidence.py`, escalation→ticket→live-agent (`_handle_ticketing` /
`request_live_agent`), session store, and the whole live-handoff feature just shipped.

---

## 4. Validation

Naturalness is partly subjective, so validate on three levels:

1. **Structural regression assertions** (deterministic, in the chat eval / a new test):
   - No verbatim-repeated clarifying question within a conversation.
   - A confident, well-specified issue reaches grounded help **without** a separate
     confirm-only turn (turn-count assertion on a golden scenario).
   - When grounded steps exist, the reply contains the relevant steps together (not a single
     step when multiple short steps apply).
   - Weak/no grounding match → the reply offers a specialist and contains **no** step list.
2. **Golden conversations** (`docs/development/golden-conversations.md`): add/refresh scenarios
   incl. the Docker-install case and a multi-turn "still not working" progression; human-review
   the transcripts for specialist-like feel.
3. **Grounding non-regression:** the existing grounding/confidence eval and the retrieval eval
   must stay green — proves fluidity didn't loosen grounding.

---

## 5. Risks & rollout

- **Risk: dropping the confirm gate mis-routes an ambiguous issue.** Mitigation: the confirm is
  retained precisely for the low-confidence/ambiguous branch; only confident subtype
  classifications skip it. Confidence code is unchanged.
- **Risk: grouping steps re-introduces the "dump the KB" feel the earlier B1 work fixed.**
  Mitigation: group only the *matched subtype's* approved steps (typically 1–4), in prose, and
  keep the tried-step memory; this is "give the relevant fix," not "dump all articles."
- **Rollout:** gate the new flow behind a config flag (e.g. `FEATURE_FLUID_CHAT`, default on in
  dev) so it can be compared against the current flow and reverted without a code change if a
  golden-conversation regression appears. Remove the flag once validated.

---

## 6. Success criteria
- The Docker-install scenario (and the golden set) read like a competent specialist: no
  repeated questions, no forced "is that right?" turn, relevant help in one natural reply, and
  an honest hand-off when the KB genuinely lacks the answer.
- All existing grounding/confidence/retrieval evals stay green (no grounding regression).
