# Retrieval Guardrails

> Status: Active · Owner: Retrieval · Last updated: 2026-06-17

How retrieval is constrained so the resolver only ever sees on-topic,
on-subtype knowledge. This complements
[retrieval-and-indexing.md](./retrieval-and-indexing.md) (the base retriever)
and [chat-grounding-rules.md](./chat-grounding-rules.md) (the contract).

## Pipeline

```
diagnostic context
       │  _build_focused_query (system + subtype + symptom + error)
       ▼
KnowledgeRetrievalService.search(category=..., limit=candidate_limit)
       │  (DB published-only; YAML keyword fallback in dev)
       ▼
candidate articles  (broad pool: max(limit*4, 12))
       │  ground_results(candidates, diag_ctx)
       ▼
┌─────────────────────────────────────────────┐
│ 1. Domain guard  — reject cross-family       │
│ 2. Subtype rerank — exact subcategory first  │
│ 3. Symptom/system overlap scoring            │
└─────────────────────────────────────────────┘
       ▼
kept[:limit]  +  trace (kept/rejected/relevance)
```

Implemented in
[`grounding.py`](../../backend/app/services/agents/grounding.py) and wired in
[`nodes/retrieval.py`](../../backend/app/workflows/nodes/retrieval.py).

### Why a broad candidate pool first

The base retriever truncates to `limit` (playbook default 3). If the
subtype-specific article isn't in the top-3 by raw keyword score it would be
dropped before grounding could rerank it. So the node requests
`max(limit*4, 12)` candidates, then grounding reranks, then we keep `limit`.

## 1. Domain guard (cross-domain rejection)

`family = category.split("/")[0]`. An article is **rejected** if its family
differs from the issue's family and is not in the playbook's `allowed_families`.

Example — issue `email/outlook`, subtype `mailbox-full`:

| Article | Family | Decision |
|---------|--------|----------|
| Outlook Mailbox Full | `email` | keep |
| Reset your password | `access` | **reject** |
| Windows Update | `device-management` | **reject** |
| Headset not detected | `hardware` | **reject** |

Rejections are recorded in the trace with a reason.

## 2. Subtype-aware rerank

Relevance for a kept article:

- `+0.55` if `subcategory == issue_subtype` (or subtype tokens ⊆ article tokens)
- `+0.30 × symptom-token overlap`
- `+0.10` if the normalized system appears in the article
- `+0.10` if same full category
- `+0.10 × retriever score` (small prior)

Articles are sorted by `(subtype_match, relevance)` descending. The first
subtype-matching article therefore wins over any generic one.

## 3. Confidence from grounding (not raw overlap)

The node derives `knowledge_confidence` from the **grounded** top relevance:

- subtype match present → `0.4 + 0.55 × top_relevance` (max 0.95)
- on-family but no subtype match → `0.2 + 0.4 × top_relevance` (max 0.6)
- nothing kept → `0.0`

This feeds the composite resolution confidence (see
[chat-grounding-rules.md](./chat-grounding-rules.md)).

### Reliability floor

`FLUID_CHAT_MIN_CONFIDENCE_TO_ADVISE` (currently `0.35`, retained under its
existing configuration name for compatibility) is a hard floor for **all** chat
flows, not only fluid chat. Below it, the retrieval node records an uncertainty
reason and routing goes directly to escalation; the resolution LLM is not
invoked with the weak context.

## Traceability

`ground_results(...).trace()` returns:

```json
{
  "kept": [{"id","title","category","subcategory","relevance","subtype_match","reasons"}],
  "rejected": [{"id","title","category","reason"}],
  "top_relevance": 0.93,
  "has_subtype_match": true
}
```

The trace is attached to `WorkflowState.retrieval_trace`, logged in the
`knowledge.searched` audit entry, and surfaced (IT/admin only) in the chat
debug panel. See [chat-debugging-guide.md](../development/chat-debugging-guide.md).

## Adding a new system/subtype

1. Add subtype rules to `subtype_classifier._CATEGORY_RULES`.
2. Add subtype-scoped KB articles whose `subcategory` matches the new subtypes.
3. Add the subtypes to the category playbook's `subtypes` (for `playbook_fit`).
4. Add a golden conversation + tests.
