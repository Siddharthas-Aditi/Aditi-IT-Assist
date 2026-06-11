# Retrieval & Indexing (RAG) Design

> Last updated: 2026-06-11

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
- `index_article()` — prepares + indexes; bumps `index_version`, sets
  `embedding_status=indexed`, stamps `indexed_at`. Called automatically on
  **publish**.
- `remove_from_index()` — deletes chunks and resets status on **archive**, so the
  agent stops using the article immediately.
- `reindex()` — admin-triggered rebuild of selected / stale / all published
  articles. Returns counts + per-article errors; never silently truncates.
- `get_status()` — corpus index health for the admin Indexing panel.

### Embedding abstraction

`EmbeddingClient` abstracts the vector backend. The default dev implementation is
a **no-op**: it does not compute real vectors but lets the pipeline mark chunks
indexed so the governed retrieval path is exercised end-to-end without external
dependencies. A production implementation calls the configured provider and
persists vectors to `pgvector` (`VECTOR_STORE_TYPE=pgvector`).

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
- **Scoring**: keyword overlap over `retrieval_text` + tags, boosted by usage and
  quality score; composite confidence with a `LOW_CONFIDENCE_THRESHOLD` (0.45) the
  orchestrator can use to **escalate** low-confidence answers.
- **Citations**: each hit returns `{article_id, title, citation_label, snippet,
  score}` for traceable, explainable answers.
- **Dev fallback**: when the DB has no published content, retrieval transparently
  falls back to the YAML keyword `KnowledgeService` so chat is never empty locally.

Drafts/in-review/approved/archived content is **never** returned to employee chat.
Internal search for IT/Admin is opt-in and gated by `knowledge:view_internal`.

## Endpoints

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/knowledge/search` | Legacy public keyword search (unauthenticated) |
| `GET` | `/knowledge/retrieve` | **Governed**, authenticated, published-only + citations |
| `GET` | `/knowledge/admin/indexing/status` | Index health |
| `POST` | `/knowledge/admin/indexing/reindex` | Trigger rebuild (`knowledge:reindex`) |
| `GET` | `/knowledge/admin/articles/{id}/preview` | Retrieval preview (chunks + warnings) |

## Tuning recommendations

See "recommended next improvements" in the main deliverable summary: wire a real
embedding provider, add hybrid (vector + keyword) fusion, add per-chunk metadata
filters at the vector layer, and feed `feedback_score` / `resolution_rate` back
into ranking.
