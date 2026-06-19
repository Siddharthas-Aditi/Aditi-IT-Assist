# Multi-Agent Support Architecture

> The target architecture for Aditi IT Assist: a supervisor + typed specialist
> agents over a grounded RAG core, with controlled web fallback and warm human
> handoff. This document is the contract every implementation lines up against.

---

## 1. Goals (and what we deliberately reject)

**Goals**

- Natural, intent-aware conversation; not robotic form-filling.
- Specialist + sub-agent ownership of issue domains; clear boundaries.
- Grounded RAG over governed internal KB; web fallback only under policy.
- Warm handoff to live IT specialists with full structured context.
- Continuous improvement via reviewable knowledge candidates — never silent
  auto-learning into production KB.
- Strong operational guardrails: max handoffs, loop detection, confidence
  floors, audit trail, deterministic replay.

**Anti-goals**

- A "smart LLM" that invents answers when the KB is silent.
- Agent ping-pong: open-ended delegation loops between specialists.
- Background self-modification of the knowledge base.
- Hidden state machines coded across the workflow nodes.

---

## 2. Layer model

```
                          ┌──────────────────────────┐
   user turn  ──────────▶ │   Conversation Intent    │   classify_intent()
                          │   (deterministic)        │   intent_classifier.py
                          └────────────┬─────────────┘
                                       ▼
                          ┌──────────────────────────┐
                          │       Supervisor         │   supervisor.decide()
                          │  (pure routing function) │   over AGENT_REGISTRY
                          └────────────┬─────────────┘
                                       ▼
        ┌───────────┬───────────┬──────┴───────┬──────────────┬────────────┐
        ▼           ▼           ▼              ▼              ▼            ▼
   Clarify     Retrieve    Specialist     Sub-agent     Web research  Escalation
                            (registry)    (registry)    (policy gate)  (handoff)
                                       │              │              │
                                       ▼              ▼              ▼
                                Grounded KB   Grounded KB   Trust-tier   Specialist
                                              + playbook    filtered     queue
                                                            sources
                                                                         │
                                                                         ▼
                                                                    Live IT Spec
                                                                    + KB Improv.
                                                                    candidate
```

Every box is one module, with a typed contract documented inline. Routing
between boxes is the supervisor's only job — no specialist invokes another
specialist directly.

---

## 3. Components

### 3.1 ConversationIntent (existing — Phase 0)
`backend/app/services/agents/intent_classifier.py`. Deterministic, versioned,
typed. Reports `NEW_TOPIC`, `ESCALATE_REQUEST`, `CONFIRM`, `DENY`,
`POSITIVE_FEEDBACK`, `NEGATIVE_FEEDBACK`, `REPEAT_OR_SIMPLIFY`, `GREETING`,
`GRATITUDE`, `SMALL_TALK`, `CONTINUE`. See
[`conversation-intents.md`](./conversation-intents.md).

### 3.2 Agent Registry (Phase 1)
`backend/app/services/agents/registry.py`. The single declarative source of
truth. Every agent is a frozen `AgentSpec`; specialists carry
`systems`/`categories`/`subtypes`/`required_slots`/`web_fallback_allowed`/
`escalation_triggers`. Sub-agents nest inside specialists. Versioned
(`REGISTRY_VERSION`) so audits and analytics can join on it.

Adding a new specialist is **one declaration + one implementation file** —
the rest of the system needs no edits.

### 3.3 Supervisor (Phase 1)
`backend/app/services/agents/supervisor.py`. Pure function: takes
(`IntentClassification`, slot state, retrieval signal, `SessionMetrics`)
and returns a `SupervisorDecision` with `action`, `reason`, `agent`,
`sub_agent`, `confidence`, `inputs_snapshot`. No LLM call, no I/O.

Decisions: `CLARIFY`, `RETRIEVE`, `DELEGATE`, `DELEGATE_SUB`, `RESPOND`,
`WEB_FALLBACK`, `ESCALATE`, `RESET_TOPIC`, `END`.

Guardrails enforced here:
- Global `_GLOBAL_HANDOFF_CAP` (8) — beyond → escalate.
- Per-specialist soft cap `_PER_SPECIALIST_CAP` (3) — beyond → web fallback
  if allowed, else escalate.
- Loop detection (≥2 no-progress signals).
- Intent short-circuits (`NEW_TOPIC` → `RESET_TOPIC`; `ESCALATE_REQUEST` →
  `ESCALATE`; `issue_resolved` → `END`).
- Confidence-floor escalation (`knowledge_confidence` below specialist
  threshold after attempts).

### 3.4 Triage (existing, enhanced)
`backend/app/workflows/nodes/triage.py`. Entity normalization, subtype
classification, sentiment, slot extraction. Runs the new intent classifier at
the top of every turn; reset on `NEW_TOPIC`, confirms on `ESCALATE_REQUEST`.

### 3.5 Retrieval (existing)
`backend/app/workflows/nodes/retrieval.py` +
`backend/app/services/knowledge/retrieval.py`. Narrow, system-aware,
subtype-aware queries with grounding guard
([retrieval-guardrails.md](./retrieval-guardrails.md),
[chat-grounding-rules.md](./chat-grounding-rules.md)). Returns kept articles +
trace. Confidence reflects grounded relevance, never raw keyword overlap.

### 3.6 Specialist agents (Phase 1: Outlook; Phase 2: others)
`backend/app/services/agents/specialists/`. Each implements the
`SpecialistAgent` Protocol from `specialists/base.py`:
- `handle(SpecialistInput) -> SpecialistOutput`
- `can_handle(SpecialistInput) -> bool`

Specialists are stateless functions of (`DiagnosticContext`,
grounded `knowledge_results`, optional `sub_agent`). They:
1. Pick the next step batch from grounded content, scoped to the active
   subtype.
2. Skip steps already presented or marked failed.
3. Render a natural, conversational reply (NOT a numbered dump).
4. Emit `KnowledgeImprovementHint`s when they hit gaps.
5. Signal `escalation_signal` when their KB is exhausted.

### 3.7 Controlled Web Research (Phase 1)
`backend/app/services/agents/web_research.py`. Wraps the raw
`WebSearchService` with:
- **Policy gate** — refuses unless `SpecialistAgentSpec.web_fallback_allowed`.
- **Trust-tier filter** — `OFFICIAL` + `VENDOR` by default;
  `TRUSTED_COMMUNITY` opt-in per specialist; `GENERAL_BLOG` never.
- **Mandatory candidate creation** — every external content pull becomes a
  `KnowledgeCandidate` for SME review. Production KB never auto-grows.
- **Audit** — every call, including blocks, logged via structlog.

### 3.8 Escalation + Specialist Queue (Phase 1)
- `backend/app/workflows/nodes/escalation.py` — typed handoff package
  builder, queues the ticket.
- `backend/app/services/specialist_queue_service.py` — atomic claim
  (single UPDATE with `WHERE assigned_to IS NULL OR assigned_to=:me`), list,
  release, resolve.
- `backend/app/api/v1/specialist_queue.py` — REST endpoints for the IT
  specialist UI.
- `backend/app/schemas/specialist_queue.py` — `HandoffPackage` schema
  (typed: summary + slots + steps_attempted + KB sources + web sources +
  conversation + supervisor decision trace).

### 3.9 Knowledge Improvement loop (Phase 1)
- `backend/app/models/knowledge_candidate.py` — DB model with lifecycle
  `proposed → triaged → approved → promoted | rejected | duplicate`.
- `backend/app/services/knowledge/improvement.py` — propose +
  deduplicate (rolling 30-day window) + review-queue ops.
- `backend/app/services/specialist_queue_service.SpecialistQueueService.resolve`
  optionally proposes a candidate when a live specialist closes a chat
  resolution — opt-in, NEVER auto-published.

---

## 4. Routing rules (the supervisor's contract)

Encoded once, in `supervisor.decide`:

| Priority | Condition | Action |
|---|---|---|
| 1 | intent == `NEW_TOPIC` | `RESET_TOPIC` |
| 2 | intent == `ESCALATE_REQUEST` | `ESCALATE` |
| 3 | `issue_resolved` | `END` |
| 4 | `handoffs ≥ 8` (global cap) | `ESCALATE` |
| 5 | `loop_signals ≥ 2` | `ESCALATE` |
| 6 | `needs_clarification` | `CLARIFY` |
| 7 | no specialist + no KB + ≥1 attempt | `ESCALATE` |
| 8 | no specialist + no KB | `RETRIEVE` |
| 9 | no specialist + KB hit | `RESPOND` |
| 10 | per-specialist cap + web allowed | `WEB_FALLBACK` |
| 11 | per-specialist cap + no web | `ESCALATE` |
| 12 | specialist's required slots missing | `CLARIFY` |
| 13 | KB confidence < floor + ≥1 attempt | `ESCALATE` |
| 14 | sub-agent owns subtype | `DELEGATE_SUB` |
| 15 | else | `DELEGATE` |

The supervisor is replayable: given the same inputs, it returns the same
decision. Golden tests pin this.

---

## 5. Grounding rules

1. Internal published KB is preferred and exclusive when available.
2. Retrieval is system-aware and subtype-aware (see retrieval-guardrails).
3. Specialists may only use steps inside the returned articles — never
   invent steps, never bleed across subtypes.
4. If no KB hit, the supervisor asks; if asking exhausted, it escalates.
5. Web research is policy-gated and produces candidates, not auto-answers
   into a user-facing reply unless re-rendered by the response agent with
   explicit "external source" labeling.

---

## 6. Observability

Every layer writes structured logs with stable event names so dashboards can
slice consistently:

| Event | Fields |
|---|---|
| `conversation_intent` | intent, confidence, matched, version |
| `supervisor_decision` | action, reason, agent, sub_agent, confidence, snapshot |
| `specialist.<name>.handled` | subtype, steps_count, remaining_after |
| `specialist.<name>.exhausted` | subtype, attempts |
| `web_research_completed` | specialist, results_in, results_out, tiers |
| `web_research_blocked` | specialist, reason |
| `knowledge_candidate_proposed` | candidate_id, source, subtype, agent |
| `knowledge_candidate_deduplicated` | candidate_id, times_seen, source |
| `specialist_queue_claimed` | ticket_id, claimer_id |
| `specialist_queue_resolved` | ticket_id, resolver_id, candidate_id |

Every entry carries the registry/supervisor/intent-classifier versions for
reproducibility.

---

## 7. What's deferred (Phase 2/3)

See [`rollout-plan-multi-agent.md`](../development/rollout-plan-multi-agent.md).

In short: only one specialist (`outlook`) ships with a full implementation in
Phase 1. The other specialists are *declared* in the registry but delegate to
the legacy resolution node — this means the supervisor's decisions take
effect immediately (better routing, better escalation, no `ITA-000007`-style
bugs) while the migration to per-specialist handlers happens behind a feature
flag in Phase 2.

---

## 8. Related docs

- [`conversation-intents.md`](./conversation-intents.md)
- [`human-handoff-and-queue.md`](./human-handoff-and-queue.md)
- [`knowledge-improvement-loop.md`](./knowledge-improvement-loop.md)
- [`controlled-web-fallback.md`](./controlled-web-fallback.md)
- [`retrieval-and-indexing.md`](./retrieval-and-indexing.md)
- [`troubleshooting-state-machine.md`](./troubleshooting-state-machine.md)
- [`rollout-plan-multi-agent.md`](../development/rollout-plan-multi-agent.md)
