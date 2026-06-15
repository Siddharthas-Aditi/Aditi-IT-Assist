# Document Ingestion Architecture

> **Aditi IT Assist** — Knowledge Authoring subsystem
> Last updated: 2026-06-15

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
Stage 5 — Optional LLM Enrichment (llm_extractor.py)
  │         Disabled when INGESTION_LLM_ENABLED=false
  │         Fills missing fields from LLM JSON output
  │         Raises confidence by up to +0.15
  ▼
Stage 6 — Validation + Scoring (validator.py)
  │         Blocking: title, category, actionable content
  │         Warnings: summary, escalation, tags, confidence
  ▼
Stage 7 — Duplicate Detection (deduplicator.py)
  │         Title similarity (SequenceMatcher ≥ 0.70)
  │         Tag overlap (≥ 2 shared tags)
  │         Product + category exact match
  ▼
Stage 8 — Persist Candidates (ingestion_repository.py)
  │
  ▼
Stage 9 — Finalise Job (status = completed | failed)
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
| `processing_summary` | JSONB | Per-stage timing |
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
| `extracted_confidence` | Float | 0.0 – 1.0 |
| `validation_warnings` | JSONB | `[{code, message, severity}]` |
| `review_status` | Enum | pending / approved / rejected / saved |
| `mapped_article_id` | UUID FK | Set when saved as KB article |
| `raw_segment_text` | Text | Original document segment |

---

## Service Boundaries

| Module | Responsibility |
|--------|----------------|
| `extractor.py` | Raw text extraction only — no parsing |
| `parser.py` | Deterministic structural heuristics — no LLM |
| `llm_extractor.py` | Optional LLM enrichment — additive only |
| `validator.py` | Validation rules + confidence scoring |
| `deduplicator.py` | Similarity search against published articles |
| `mapper.py` | `CandidatePayload` → `ArticleCreate` translation |
| `pipeline.py` | Orchestrates stages 1–9, updates job status |
| `ingestion_repository.py` | All DB access for jobs and candidates |

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

---

## Configuration

```env
UPLOAD_DIR=/tmp/aditi_uploads          # File storage root
MAX_UPLOAD_MB=50                       # Upload size limit
INGESTION_PARSER_VERSION=1.0.0         # Stamped on each job
INGESTION_LLM_ENABLED=true            # Set false to skip LLM enrichment
```

---

## Frontend Routes

| Path | Component | Description |
|------|-----------|-------------|
| `/dashboard/knowledge/upload` | `KnowledgeUploadPage` | Drop zone + recent jobs |
| `/dashboard/knowledge/ingest/:jobId` | `CandidateReviewPage` | Candidate list + bulk save |
| `/dashboard/knowledge/ingest/:jobId/:candidateId` | `CandidateEditorPage` | Two-panel editor |
