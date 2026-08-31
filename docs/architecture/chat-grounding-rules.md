# Chat Grounding Rules

> Status: Active · Owner: Conversational AI · Last updated: 2026-06-17

This document defines the **grounding contract** for the employee-facing chat
agent: which knowledge it may use to answer, and the guarantees that prevent the
class of failure that produced wrong, cross-domain advice.

## The failure this prevents

Observed bug:

```
User: I have an issue with outlook
Bot:  (broad clarification)
User: my inbox is full
Bot:  - wait 15 minutes
      - change email password
      (after "it didn't work")
      - wait 15 minutes
      - change email password
      - Windows Update
```

"Inbox full" is an **Outlook mailbox-storage** problem. The answer mixed in
**account-lock** ("wait"), **access/password** ("change password"), and
**device** ("Windows Update") content, then **repeated** the same failed steps.

Root causes (all now fixed):

1. **No subtype.** The agent classified only the broad category `email/outlook`
   and then answered with the "first N steps of the first article", which had
   nothing to do with storage.
2. **No retrieval guard.** Cross-domain articles (password, Windows Update)
   could surface and contaminate the answer.
3. **No tried-step memory / loop control.** "It didn't work" re-ran the same
   steps instead of advancing.
4. **Meaningless confidence.** A mismatched answer still reported ~95%.

## The grounding contract

An answer may only be built from knowledge that is **all three** of:

1. **On-system** — relevant to the normalized system/product
   (`DiagnosticContext.normalized_system`, e.g. `outlook`).
2. **On-subtype** — relevant to the identified subtype
   (`DiagnosticContext.issue_subtype`, e.g. `mailbox-full`), as produced by
   [`subtype_classifier.py`](../../backend/app/services/agents/subtype_classifier.py).
3. **On-step** — not a step the user has already been given or has reported as
   failed (`DiagnosticContext.suggested_steps` / `failed_steps`).

These are enforced in three places, not the prompt:

| Stage | Module | Guarantee |
|-------|--------|-----------|
| Classification | `subtype_classifier.classify_subtype` | Maps symptom → concrete subtype deterministically. Vague input → `None` (ask, don't guess). |
| Retrieval | `grounding.ground_results` | Rejects cross-domain articles; reranks subtype matches to the top; returns a trace. |
| Resolution | `nodes/resolution.py` `_build_progression` | Presents only NEW steps; advances on failure; escalates when exhausted. |
| Scoring | `confidence.compute_resolution_confidence` | Confidence cannot be high without real grounding. |

## Forbidden cross-domain mixing

For an Outlook mailbox-full issue, the following must never appear unless the
playbook explicitly allows it:

- account-lock / "wait for auto-unlock" steps (`access/*`)
- password change / reset steps (`access/*`)
- Windows Update / device compliance steps (`device-management/*`)
- audio / camera / unrelated hardware steps (`hardware/*`)

The domain guard in `ground_results` rejects any article whose **category
family** (the part before `/`) differs from the issue's family, and records the
rejection in the trace.

## Subtype → article alignment

Each KB article carries a `subcategory` whose value matches a subtype emitted by
the classifier (e.g. `mailbox-full`). The grounding reranker gives an exact
`subcategory == subtype` match the dominant relevance boost, so the focused
article wins over a generic one. See
[retrieval-guardrails.md](./retrieval-guardrails.md) and
[knowledge-management.md](./knowledge-management.md).

When adding a KB article, set `subcategory` to a real subtype from
`subtype_classifier.known_subtypes(category)` and keep its steps scoped to that
subtype only. Do **not** create monolithic "all issues" articles.

## What the agent does when it can't ground

- **No subtype yet** → ask a focused, playbook-driven clarification (with chips).
- **No on-domain/on-subtype article, or confidence below the configured floor** → state uncertainty explicitly and escalate with a summary. The resolver must not use weak retrieval as permission to answer from model knowledge.
- **Steps exhausted** → escalate with the list of what was tried.

See [troubleshooting-state-machine.md](./troubleshooting-state-machine.md).
