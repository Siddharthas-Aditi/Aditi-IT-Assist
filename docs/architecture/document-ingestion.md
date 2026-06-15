# Document Ingestion Architecture

> **Aditi IT Assist** — Knowledge Authoring subsystem
> Last updated: 2026-06-15 · Pipeline v2 (adaptive, schema-stable)

---

## Overview

The Document Ingestion pipeline allows IT Leads and Admins to upload source
documents (DOCX, PDF, PPTX, TXT, Markdown) and automatically extract
structured knowledge article candidates from them.  A human reviewer
inspects each candidate before it is promoted to a draft `KnowledgeArticle`.

---

## Pipeline Stages

```
Upload
  │
  ▼
Stage 1 — Load Job + Locate File
  │
  ▼
Stage 2 — Text Extraction (extractor.py)
  │         DOCX → python-docx
  │         PDF  → pymupdf (fitz)
  │         PPTX → python-pptx
  │         TXT/MD → plain read
  ▼
Stage 3 — Persist Raw Text Path
  │
  ▼
Stage 4 — Structural Parsing (parser.py)
  │         Segment into topics
  │         Extract title, symptoms, steps, escalation
  │         Classify category, detect product
  ▼
---

## Design Principle — Schema-Stable, Parser-Flexible

> "Document formats change constantly; the schema must not."

The v2 pipeline separates **what to extract** (the stable `ExtractionCandidate`
schema) from **how to extract it** (swappable parser profiles + layered
strategies).  Adding support for a new document template requires only a new
or updated `ParserProfile` — never a code change to the extraction engine.

---

## Pipeline Stages (v2)

```
Upload
  │
  ▼
Stage 1 — Load Job + Locate File
  │
  ▼
Stage 2 — Text Extraction          extractor.py          Layer A
  │         DOCX → python-docx
  │         PDF  → pymupdf (fitz)
  │         PPTX → python-pptx
  │         TXT/MD → plain read
  ▼
Stage 3 — Persist Raw Text Path
  │
  ▼
Stage 4 — Structural Normalisation  normalizer.py         Layer B
  │         Raw text → typed NormalizedLine sequence
  │         15+ bullet variants unified
  │         8+ number formats detected
  │         5 heading detection signals
  ▼
Stage 5 — Profile Detection         profiles/registry.py
  │         Keyword-based auto-detection
  │         Falls back to IT_SUPPORT_PROFILE
  ▼
Stage 6 — Semantic Segmentation     segmenter.py          Layer C
  │         NormalizedDocument → list[DocumentSegment]
  │         Evidence-accumulating boundary detection
  │         section_map built per segment from profile labels
  ▼
Stage 7 — Deterministic Extraction  field_extractor.py    Layer D
  │         2–4 independent strategies per field
  │         Priority: labeled-section > structural > semantic scan
  │         Per-field FieldExtraction with confidence + excerpt
  ▼
Stage 8 — Optional LLM Enrichment   llm_extractor.py      Layer D+
  │         Only fills fields below profile threshold (0.50)
  │         Hallucination guard: values must be grounded in segment
  │         Marks enriched fields as ExtractionMethod.COMBINED
  ▼
Stage 9 — Score + Validate + Dedup + Persist
            confidence.py — weighted composite score
            validator.py  — blocking errors + quality warnings
            deduplicator.py — similarity check vs existing articles
            ingestion_repository.py — persist to DB
```

---

## Data Models

### `IngestionJob`

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `source_filename` | String | Original filename |
| `source_type` | String | docx / pdf / pptx / txt / md |
| `source_size` | Integer | Bytes |
| `uploaded_by` | UUID FK | User who uploaded |
| `parse_status` | Enum | pending / extracting / parsing / completed / failed |
| `extraction_status` | Enum | pending / completed / failed |
| `candidate_count` | Integer | Number of extracted candidates |
| `processing_summary` | JSONB | Per-stage timing (s1_locate … total) |
| `raw_text_ref` | Text | Path to extracted text on disk |
| `parser_version` | String | `settings.INGESTION_PARSER_VERSION` |
| `error_details` | Text | Traceback on failure |

### `IngestionCandidate`

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `ingestion_job_id` | UUID FK | Parent job |
| `candidate_index` | Integer | Zero-based position |
| `extracted_*` | Various | Extracted KB article fields |
| `extracted_confidence` | Float | 0.0 – 1.0 composite score |
| `validation_warnings` | JSONB | `[{code, message, severity}]` |
| `review_status` | Enum | pending / approved / rejected / saved |
| `mapped_article_id` | UUID FK | Set when saved as KB article |
| `raw_segment_text` | Text | Original document segment |
| `normalized_payload_json` | JSONB | Schema version, profile, per-field confidences |

---

## Extraction Schema Contract

Every field is wrapped in a `FieldExtraction`:

```python
@dataclass
class FieldExtraction:
    value: object          # str | list | None
    confidence: float      # 0.0 – 1.0
    source_excerpt: str    # text the value was drawn from
    method: ExtractionMethod  # DETERMINISTIC | HEURISTIC | LLM | COMBINED
    warnings: list[str]
```

Confidence thresholds (from `schema.py`):

| Level | Score | Review |
|-------|-------|--------|
| `HIGH` | ≥ 0.75 | Not required |
| `MEDIUM` | ≥ 0.50 | Recommended |
| `LOW` | ≥ 0.30 | Required |
| `VERY_LOW` | < 0.30 | Required; consider retry |

---

## Service Boundaries

| Module | Responsibility |
|--------|----------------|
| `extractor.py` | Raw text only — no parsing decisions |
| `normalizer.py` | Structure tokens — no semantic decisions |
| `segmenter.py` | Topic boundaries + section_map — no field values |
| `field_extractor.py` | Deterministic field values — no LLM |
| `llm_extractor.py` | LLM enrichment — additive only, never overwrites |
| `confidence.py` | Composite scoring + warnings |
| `validator.py` | Blocking errors + quality checks |
| `deduplicator.py` | Similarity search vs published articles |
| `mapper.py` | `ExtractionCandidate` → `ArticleCreate` |
| `pipeline.py` | Orchestrates stages 1–9, updates job status |
| `profiles/` | Per-document-family extraction configuration |

---

## API Endpoints

Base: `/api/v1/knowledge/ingest`

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/upload` | `knowledge:ingest` | Upload file, start pipeline |
| GET | `/jobs` | `knowledge:ingest` | List jobs |
| GET | `/jobs/{id}` | `knowledge:ingest` | Job detail + counts |
| POST | `/jobs/{id}/retry` | `knowledge:ingest` | Re-run failed job |
| GET | `/jobs/{id}/candidates` | `knowledge:ingest_review` | List candidates |
| GET | `/jobs/{id}/candidates/{cid}` | `knowledge:ingest_review` | Candidate detail |
| PATCH | `/jobs/{id}/candidates/{cid}` | `knowledge:ingest_review` | Edit fields |
| POST | `/jobs/{id}/candidates/{cid}/save` | `knowledge:ingest_review` | Save as draft |
| POST | `/jobs/{id}/candidates/{cid}/reject` | `knowledge:ingest_review` | Reject |
| POST | `/jobs/{id}/bulk-save` | `knowledge:ingest_review` | Bulk save |
| GET | `/duplicates` | `knowledge:ingest_review` | Duplicate lookup |

### New v2 response fields

`IngestionCandidateDetail` now includes:

```json
{
  "schema_version": "2.0.0",
  "parser_profile": "it_support_v1",
  "parser_version": "2.0.0",
  "confidence_level": "medium",
  "review_required": true,
  "field_confidences": {
    "title": 0.90, "category": 0.80, "resolution_steps": 0.88
  },
  "parser_warnings": ["No symptoms detected — article may be hard to find via search."]
}
```

---

## Configuration

```env
UPLOAD_DIR=/tmp/aditi_uploads          # File storage root
MAX_UPLOAD_MB=50                       # Upload size limit
INGESTION_PARSER_VERSION=2.0.0         # Stamped on each job
INGESTION_LLM_ENABLED=true             # Set false to skip LLM enrichment
```

---

## Frontend Routes

| Path | Component | Description |
|------|-----------|-------------|
| `/dashboard/knowledge/upload` | `KnowledgeUploadPage` | Drop zone + recent jobs |
| `/dashboard/knowledge/ingest/:jobId` | `CandidateReviewPage` | Candidate list + bulk save |
| `/dashboard/knowledge/ingest/:jobId/:candidateId` | `CandidateEditorPage` | Two-panel editor with extraction metadata |

The `CandidateEditorPage` now shows:
- `ExtractionMetaBanner` — schema version, parser profile, per-field confidences
- Colour-coded `ConfidenceBadge` using `confidence_level` (HIGH/MEDIUM/LOW/VERY_LOW)
- "Review required" indicator on `CandidateCard` and editor header

---

## See Also

- [`docs/architecture/knowledge-ingestion-pipeline.md`](knowledge-ingestion-pipeline.md) — detailed stage spec
- [`docs/development/parser-rules.md`](../development/parser-rules.md) — adding profiles + tuning guide
- [`docs/development/extraction-schema.md`](../development/extraction-schema.md) — schema versioning reference
