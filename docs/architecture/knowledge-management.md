# Knowledge Management Architecture

> Module owner: IT Knowledge Platform · Last updated: 2026-06-11

The Knowledge Management (KM) module is an enterprise knowledge capability optimized
for **admin authoring & governance**, **high-quality AI retrieval**, **traceable/
explainable answers**, and **future scalability** across support domains. It is
deliberately *not* a CRUD page: every article is structured, governed, versioned,
audited, and retrieval-ready.

## Service boundaries

KM is split into three clear boundaries so they can scale and be reasoned about
independently:

| Boundary | Responsibility | Key modules |
|----------|----------------|-------------|
| **KB management** (write side) | Authoring, lifecycle, versioning, taxonomy, governance | `services/knowledge/management.py`, `taxonomy.py`, `lifecycle.py` |
| **KB retrieval** (read side) | Governed, published-only retrieval for the agent + citations | `services/knowledge/retrieval.py` |
| **Indexing pipeline** | Article → chunks → vector index, reindex on lifecycle events | `services/knowledge/indexing.py`, `normalization.py` |

Agent orchestration (the LangGraph workflow) consumes the **retrieval** boundary
only — it never touches the management or indexing internals.

## Backend file map

```
backend/app/
├── core/permissions.py            # knowledge:* permission codes + role mapping
├── models/knowledge.py            # 7 tables (article + version/chunk/taxonomy/…)
├── schemas/knowledge.py           # Pydantic v2 request/response models
├── repositories/knowledge_repository.py   # all KB data-access (no inline queries)
├── services/knowledge/
│   ├── lifecycle.py               # pure transition + publish-validation rules
│   ├── normalization.py           # article → retrieval_text + semantic chunks
│   ├── indexing.py                # (re)index pipeline + EmbeddingClient abstraction
│   ├── taxonomy.py                # taxonomy + ownership-group CRUD + validation
│   ├── management.py              # authoring, lifecycle, versioning, feedback, audit
│   ├── retrieval.py               # governed published-only retrieval + citations
│   ├── analytics.py               # usage / effectiveness aggregation
│   └── serializers.py             # ORM → API dict mapping
├── api/v1/knowledge.py            # public: legacy search/list + governed /retrieve + feedback
├── api/v1/knowledge_admin.py      # admin: CRUD, lifecycle, versions, taxonomy, indexing, analytics
├── knowledge_base/structured_seed.py  # structured published seed articles
└── alembic/versions/003_knowledge_management.py
```

## Data model

The aggregate root is `KnowledgeArticle`, supported by normalized tables. Highlights:

- **Core**: `slug`, `title`, `short_summary`, `article_type`, `status`, `version`,
  `language`, `audience`, `visibility_scope`.
- **Domain**: `category`, `subcategory`, `product_or_system`, `platform`,
  `issue_type`, `severity_hint`, `tags`, `keywords`, `ownership_group_id`.
- **Support structure** (JSONB): `symptoms`, `probable_causes`, `prerequisites`,
  `troubleshooting_steps`, `resolution_steps`, `validation_steps`,
  `escalation_criteria`, `escalation_target_team`, `references`, `related_articles`.
- **Governance**: `author_id`, `reviewer_id`, `approver_id`, `last_reviewed_at`,
  `next_review_due_at`, `published_at`, `archived_at`, `source_type`,
  `confidence_level`, `quality_score`.
- **Retrieval**: `retrieval_text`, `chunking_strategy`, `citation_label`,
  `embedding_status`, `indexed_at`, `index_version`.
- **Analytics**: `view_count`, `usage_count`, `successful_resolution_count`,
  `feedback_score`, `negative_feedback_count`.

Normalized companions:

| Table | Purpose |
|-------|---------|
| `knowledge_article_versions` | Immutable snapshots (history / restore) |
| `knowledge_chunks` | Retrieval chunks with contextual headers |
| `knowledge_taxonomy_terms` | Admin-managed vocabulary; maps to ticket categories |
| `knowledge_ownership_groups` | Stewardship / review ownership |
| `knowledge_feedback` | Helpfulness signals from chat/portal/tickets |
| `knowledge_review_notes` | Reviewer decisions in the approval workflow |

Legacy columns (`content`, `steps`, `is_published`, `is_approved`) are retained for
backwards compatibility with the original article model and the YAML retrieval
fallback; new authoring uses the structured fields.

## Frontend file map

```
frontend/src/
├── lib/permissions.ts             # RBAC mirror (UI gating only; backend enforces)
├── lib/api.ts                     # typed fetch wrapper + chat/remote clients
├── types/knowledge.ts             # TS mirror of backend schemas
├── features/knowledge/
│   ├── api.ts                     # React Query hooks
│   ├── constants.ts               # status/type/action labels + styles
│   └── components/                # StatusBadge, StepsEditor, TagsInput, LifecycleActions,
│                                  #   MetadataPanel, RetrievalPreviewPanel, PreviewPanel, Modal, …
└── pages/admin/knowledge/         # Detail, Editor, ReviewQueue, Taxonomy, Versions, Indexing, Analytics
    + pages/admin/KnowledgeManagementPage.tsx   # list page (entry)
```

## Design principles

Governed · retrieval-aware · metadata-rich · versioned · auditable ·
enterprise-friendly · easy to maintain · directly useful to the AI chat workflow.

## Current limitations

- Embeddings use a no-op `EmbeddingClient` in dev; retrieval falls back to keyword
  scoring over prepared chunks. Wire a provider for true semantic/hybrid search.
- The LangGraph retrieval node uses the YAML `KnowledgeService` dev fallback; the
  DB-backed governed `KnowledgeRetrievalService` is exposed at `/knowledge/retrieve`
  and is the production path. Threading a request DB session into the graph is the
  next integration step.
- Version *diff* is presented as full snapshots (no field-level diff UI yet).

See also: [retrieval-and-indexing.md](retrieval-and-indexing.md),
[../product/knowledge-workflow.md](../product/knowledge-workflow.md),
[../security/knowledge-access-control.md](../security/knowledge-access-control.md).
