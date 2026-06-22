# Retrieval & Indexing (RAG) Design

> Last updated: 2026-06-22 (Phase 6: semantic + hybrid retrieval)

This document describes how structured knowledge becomes high-quality,
citation-ready retrieval for the AI chat agent.

## The retrieval-aware pipeline

```
Structured Article ──normalization──> retrieval_text + semantic chunks
        │                                        │
        │ (on publish)                           │ (on publish)
        ▼                                        ▼
  KnowledgeIndexingService ───────────> knowledge_chunks (embedding_status=indexed)
        ▲                                        │
        │ (on archive: removed)                  ▼
        │                          KnowledgeRetrievalService (published-only)
        │                                        │
        └────── reindex (admin) ─────────────────┘ ──> ranked hits + citations
```

## Article → retrieval transformation

`services/knowledge/normalization.py` (pure, no I/O):

- **Semantic-section chunking**: one chunk per meaningful section
  (`summary, overview, symptoms, probable_causes, prerequisites,
  troubleshooting_steps, resolution_steps, validation_steps, references,
  escalation`), in a fixed order so chunk indices are stable.
- **Contextual chunk headers**: every chunk is prefixed with
  `Article: … | Section: … | Category: … | Product: … | Platform: … | Audience: …`
  so a chunk read in isolation retains the article's identity and metadata —
  critical for grounding and de-contextualization resistance.
- **`retrieval_text`**: a flattened blob (title + tags + keywords + all chunks)
  used for keyword/BM25-style matching and previews.
- **`citation_label`**: deterministic, human-readable source attribution.

`chunking_strategy` is stored per article (`semantic_sections` default) so the
strategy can evolve per content type without breaking older chunks.

## Indexing pipeline

`services/knowledge/indexing.py`:

- `prepare_article()` — regenerates `retrieval_text` + chunks on every save, so
  the **retrieval preview** in the editor always reflects current content.
- `index_article()` — prepares + indexes; bumps `index_version` and stamps
  `indexed_at`. Called automatically on **publish**. **Honest status (Phase 6):**
  a chunk is marked `embedding_status=indexed` **only when it actually carries a
  vector**; without a configured provider chunks stay `pending` (keyword
  retrieval still works). An article is `indexed` only when *all* its chunks are
  embedded, else `pending`.
- `backfill_embeddings()` — embeds published chunks whose `embedding` is NULL,
  in batches. Idempotent; no-op (and says so) when no provider is configured.
  Driver: `scripts/backfill_embeddings.py`.
- `remove_from_index()` — deletes chunks and resets status on **archive**, so the
  agent stops using the article immediately.
- `reindex()` — admin-triggered rebuild of selected / stale / all published
  articles. Returns counts + per-article errors; never silently truncates.
- `get_status()` — corpus index health for the admin Indexing panel.

### Embedding abstraction

`EmbeddingClient` abstracts the vector backend. The default dev implementation is
a **no-op** (`available=False`) — it computes no vectors, and (Phase 6) chunks
are honestly left `pending` rather than marked indexed. `AzureOpenAIEmbeddingClient`
is the production client (LiteLLM → `azure/text-embedding-3-large`,
`EMBEDDING_DIMENSIONS=3072`), selected automatically by `get_embedding_client()`
when `LLM_PROVIDER=azure` and the Azure keys are set. Vectors persist to the
`KnowledgeChunk.embedding` `pgvector` column.

## Reindex triggers

| Event | Effect |
|-------|--------|
| `publish` | Prepare chunks + index (article becomes retrievable) |
| `archive` | Remove chunks from index (article stops being retrievable) |
| `create_revision` | Forks a draft; published version stays indexed until replaced |
| Admin reindex | Rebuild stale / selected / all published articles |

## Governed retrieval (the safety property)

`services/knowledge/retrieval.py` enforces the platform's central guarantee:

> The employee-facing chat agent retrieves **only published** articles.

- **Audience scoping**: employees → `employee` audience only; IT staff →
  `employee + it_staff`; holders of `knowledge:view_internal` → all audiences.
- **Metadata filters**: category, product/system, platform (from triage context).
- **Scoring**: the shared hybrid ranker (`services/knowledge/ranking.py`) blends
  semantic vector similarity, keyword overlap, usage, and quality (see below);
  composite confidence with a `LOW_CONFIDENCE_THRESHOLD` (0.45) the orchestrator
  can use to **escalate** low-confidence answers.
- **Citations**: each hit returns `{article_id, title, citation_label, snippet,
  score}` for traceable, explainable answers.
- **Dev fallback**: when the DB has no published content, retrieval transparently
  falls back to the YAML keyword `KnowledgeService` so chat is never empty locally.

Drafts/in-review/approved/archived content is **never** returned to employee chat.
Internal search for IT/Admin is opt-in and gated by `knowledge:view_internal`.

## Semantic + hybrid retrieval (Phase 6 — behind `FEATURE_VECTOR_RETRIEVAL`)

Default **off**: pure keyword retrieval (unchanged). When enabled **and** an
embedding provider is configured, `KnowledgeRetrievalService.search`:

1. lists published candidates (audience + metadata filtered) as before;
2. embeds the query and asks the repository for per-article best-chunk cosine
   similarity — `KnowledgeRepository.article_vector_scores` runs a pgvector
   `cosine_distance` aggregation over chunks with a non-null embedding;
3. blends signals via `ranking.hybrid_score` and ranks; `source` becomes
   `db_hybrid` (else `db_keyword`).

**Hybrid blend** (`ranking.py`, `RANKING_VERSION`): weights sum to 1.0 and are
tunable in config — `HYBRID_WEIGHT_VECTOR` (0.60), `_KEYWORD` (0.30), `_USAGE`
(0.07), `_QUALITY` (0.03). Key properties:

- **Keyword floor:** when a candidate has no vector signal, the vector weight
  folds into keyword, so hybrid never scores *below* keyword — vector retrieval
  cannot regress exact-term matches.
- **Graceful degradation:** no provider, an embedding error, or no embedded
  chunks all fall back to keyword automatically (the flag is safe to flip on
  before a backfill completes). Misconfigured weights log and fall back to
  defaults rather than failing a request.

**Evaluation gate:** `tests/data/retrieval_eval.yaml` + `test_retrieval_eval.py`
assert the keyword baseline meets a recall@k target and that **hybrid ≥ keyword
recall@k** on the same set. Real-corpus recall with the production embedding
model runs in the embedding-gated CI job. Unit coverage: `test_hybrid_ranking.py`
(pure ranker), `test_vector_retrieval.py` (service orchestration with fakes).

## Endpoints

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/knowledge/search` | Legacy public keyword search (unauthenticated) |
| `GET` | `/knowledge/retrieve` | **Governed**, authenticated, published-only + citations |
| `GET` | `/knowledge/admin/indexing/status` | Index health |
| `POST` | `/knowledge/admin/indexing/reindex` | Trigger rebuild (`knowledge:reindex`) |
| `GET` | `/knowledge/admin/articles/{id}/preview` | Retrieval preview (chunks + warnings) |

## Tuning recommendations

Done in Phase 6: real embedding client (`AzureOpenAIEmbeddingClient`), hybrid
(vector + keyword) fusion, honest indexing status, and a recall@k eval gate.

Still open: per-chunk metadata filters pushed down to the vector query, a learned
cross-encoder reranker (only if eval shows the heuristic blend is insufficient),
and feeding `feedback_score` / `resolution_rate` more strongly back into ranking.
Roadmap: `plans/agentic-ops-platform-evolution.md` (Phase 6).
