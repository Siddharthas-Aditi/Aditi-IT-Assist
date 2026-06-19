# Knowledge Improvement Loop

> How real signals from production — feedback, unresolved sessions, specialist
> resolutions, web-fallback hits — become reviewable knowledge candidates that
> SMEs promote into the published KB. The loop is **closed but governed**:
> the system proposes, humans approve.

---

## 1. Why this loop exists

If the assistant only ever consulted a static KB, the gap between what users
ask and what the KB covers would widen over time. If the assistant edited the
KB on its own, the KB would drift in ways no one signed off on. The middle
path is to **observe → propose → review → promote**: every signal becomes a
candidate; SMEs decide what becomes truth.

This document is the contract for that loop.

---

## 2. Sources of candidates

`backend/app/services/knowledge/improvement.py` exposes one method per source.
All return a `KnowledgeCandidate`; all dedupe against recent candidates with
the same `(source, category, issue_subtype)` triple within a 30-day window.

| Method | Trigger | Confidence |
|---|---|---|
| `record_specialist_resolution` | Live IT specialist closes a chat-derived ticket with `propose_knowledge_candidate=True`. | `0.75` |
| `record_unresolved_session` | Session ended escalated, no KB article matched the subtype. | `0.50` |
| `record_negative_feedback` | User thumbs-down or rating ≤ 2 on a chat answer. | `0.55` |
| `record_web_fallback_used` | Controlled web research returned a result. | `0.45` |
| `record_missing_subtype` | Supervisor saw a subtype no specialist owns. | `0.60` |

Confidence here is "how worth a human's time is this?" — it ranks the
review queue, not "how true is the content".

---

## 3. Candidate lifecycle

```
              ┌────────────┐
   signal ──▶ │  proposed  │ ◀── duplicate hit (bumps times_seen)
              └─────┬──────┘
                    │ triage
                    ▼
              ┌────────────┐
              │  triaged   │
              └─────┬──────┘
                    │ review
        ┌───────────┼────────────┐
        ▼           ▼            ▼
   ┌─────────┐ ┌──────────┐ ┌────────────┐
   │approved │ │ rejected │ │ duplicate  │ (merged into existing article)
   └────┬────┘ └──────────┘ └────────────┘
        │ promote (separate explicit op)
        ▼
   ┌──────────┐
   │ promoted │ ── promoted_article_id ──▶ knowledge_articles
   └──────────┘
```

State transitions are encoded in `KnowledgeImprovementService` methods. The
table never holds an article — only references to one via
`promoted_article_id` or `duplicate_of`.

---

## 4. Governance rules

These are non-negotiable; they're what makes "the assistant improves itself"
safe to deploy.

1. **No auto-promotion.** A candidate becomes an article only when a human
   with `knowledge:write` permission calls the promotion endpoint. The
   service refuses to flip a candidate from `approved` to `promoted` without
   a corresponding article id.
2. **Two-step approval.** `approve_for_promotion` marks the candidate ready
   but does NOT create the article. The SME may edit the candidate's content
   in the admin UI before clicking "Promote". The two-step flow is
   deliberate — once an article exists, the audit chain is immutable.
3. **Provenance traceable end-to-end.** Every candidate carries
   `source_session_id`/`source_ticket_id`/`source_feedback_id`/`source_url`
   so reviewers can see what the system was looking at when it proposed.
4. **Dedup before insert.** Same `(source, category, issue_subtype)` in the
   30-day window bumps `times_seen` and `confidence` instead of creating a
   new row. SMEs see ranked novelty, not noise.
5. **External content is always lower confidence.** `web_fallback` defaults
   to `confidence=0.45` precisely because external content must be reviewed
   by a human before any of it touches user-facing replies.

---

## 5. SME review queue (Phase 2 UI)

Endpoint scaffolding lives in `KnowledgeImprovementService.list_for_review`
already. The Phase 2 admin page renders:

- Filter by `state` (default `proposed` + `triaged`).
- Sort by `confidence` desc, then `times_seen` desc, then `created_at` desc.
- Per row: source badge, category, subtype, summary, "Triage / Approve /
  Reject / Mark Duplicate" actions.
- Promotion: opens the candidate as a draft `KnowledgeArticle` in the
  existing editor; on save, the service calls
  `link_promoted_article(candidate_id, article_id)` to close the loop.

Reviewer permissions live in the existing `knowledge:*` permission family
(`knowledge:review`, `knowledge:write`).

---

## 6. Metrics to watch

| Metric | Why it matters |
|---|---|
| `candidates_proposed_total` by source | Where the assistant is hitting gaps. |
| `candidates_promoted_total / proposed_total` | Reviewer signal-to-noise. Should trend up over time. |
| Median time `proposed → triaged` | Reviewer responsiveness. |
| Subtypes with ≥5 unresolved candidates | Priority queue for KB authoring. |
| Distinct sources per candidate (via `times_seen`) | Repeat-hit issues that *must* be fixed. |

Dashboards and the candidate table queries live behind the
`security_auditor` and `it_admin` roles.

---

## 7. Related docs

- [`multi-agent-support-architecture.md`](./multi-agent-support-architecture.md)
- [`knowledge-management.md`](./knowledge-management.md) — the published-KB
  lifecycle this loop ultimately feeds.
- [`feedback-analytics.md`](./feedback-analytics.md) — how feedback flows
  into negative-feedback candidates.
- [`controlled-web-fallback.md`](./controlled-web-fallback.md) — the
  upstream policy gate.
