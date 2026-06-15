# Knowledge Ingestion Pipeline — Stage Reference

> Aditi IT Assist · Pipeline v2 · Last updated: 2026-06-15

Detailed specification of each pipeline stage, its inputs/outputs, error
handling, and extension points.

---

## Stage Overview

```
File on disk
  │
  A  extractor.py      → ExtractionResult(raw_text, page_count, …)
  B  normalizer.py     → NormalizedDocument(lines: list[NormalizedLine])
  ·  profiles/         → ParserProfile (auto-detected or explicit)
  C  segmenter.py      → list[DocumentSegment]
  D  field_extractor.py→ list[ExtractionCandidate]  (deterministic)
  D+ llm_extractor.py  → list[ExtractionCandidate]  (LLM enriched, opt-in)
  ·  confidence.py     → scores + confidence_level + review_required
  ·  validator.py      → blocking_issues + warnings
  ·  deduplicator.py   → duplicate_hints
  ·  DB               → IngestionCandidate rows
```

---

## Layer A — Text Extraction (`extractor.py`)

**Input:** file path + source type
**Output:** `ExtractionResult(raw_text, page_count, slide_count, word_count, format_hints)`

| Format | Library | Notes |
|--------|---------|-------|
| DOCX | `python-docx` | Preserves paragraph order; tables joined with `\|` |
| PDF | `pymupdf` (fitz) | Page text joined with form-feed separator |
| PPTX | `python-pptx` | Slide title + body text, slide separator |
| TXT/MD | built-in | Direct UTF-8 read |

**Failure:** raises `ExtractionError`; pipeline marks job `failed`.

---

## Layer B — Structural Normalisation (`normalizer.py`)

**Input:** raw text string
**Output:** `NormalizedDocument(lines: list[NormalizedLine])`

Each `NormalizedLine` carries:

| Field | Description |
|-------|-------------|
| `raw` | Original line |
| `text` | Cleaned text (markers stripped) |
| `marker` | Original bullet/number token |
| `line_type` | `LineType` enum value |
| `indent` | 0-based indent depth |
| `number` | Parsed integer for NUMBERED lines |
| `label` | Label name for LABEL lines |

### Line types

| Type | Detection |
|------|-----------|
| `HEADING` | `## …` markdown, ALL-CAPS run ≥ 5 chars, underline-next |
| `HEADING_WEAK` | Short title-case line not ending with period |
| `BULLET` | 15+ bullet chars (`•●○▪▸◦→⇒►▶-–—*+`) |
| `NUMBERED` | `1.`, `1)`, `(1)`, `Step 1:`, `1-`, `1:` |
| `LABEL` | `SomeLabel:` format |
| `CONTINUATION` | Normal paragraph/sentence |
| `TABLE_ROW` | `|` pipe-separated row |
| `SEPARATOR` | `---` / `===` decorative separator |
| `BLANK` | Empty line |

---

## Parser Profiles (`profiles/`)

A `ParserProfile` is a data object that configures extraction for one
document family.  **No code change is needed to support a new document
template** — only a new profile.

```python
@dataclass
class ParserProfile:
    name: str                          # Unique identifier
    version: str                       # Data version (increment on change)
    section_markers: dict[str, list[str]]  # field → [label variants]
    heading_signals: list[Pattern]     # Extra heading detectors
    topic_separators: list[Pattern]    # Topic boundary patterns
    confidence_weights: ConfidenceWeights
    thresholds: ReviewThresholds
    detection: DetectionCriteria       # Keyword signals for auto-detection
```

### Auto-detection

`detect_profile(text)` in `profiles/registry.py` scores each registered
profile by counting `detection.keyword_signals` hits.  The profile with
the most hits (above `min_keyword_matches`) wins; falls back to
`IT_SUPPORT_PROFILE`.

### Bundled profiles

| Name | File | Target documents |
|------|------|-----------------|
| `it_support_v1` | `it_support.py` | IT helpdesk troubleshooting guides |

To add a new profile: see [`docs/development/parser-rules.md`](../development/parser-rules.md).

---

## Layer C — Semantic Segmentation (`segmenter.py`)

**Input:** `NormalizedDocument`, `ParserProfile`
**Output:** `list[DocumentSegment]`

Each `DocumentSegment` contains:

| Field | Description |
|-------|-------------|
| `segment_index` | Position in document |
| `heading` | Best-guess heading text |
| `lines` | `NormalizedLine` list |
| `raw_text` | Reconstructed original text |
| `signals` | `SemanticSignal` flags |
| `boundary_confidence` | 0–1 confidence of leading boundary |
| `topic_score` | 0–1 completeness as an IT topic |
| `section_map` | `{field_name → [text lines]}` from profile labels |

### Boundary evidence scoring

| Signal | Evidence added |
|--------|---------------|
| `HEADING` line type | +0.90 |
| Profile `topic_separators` match | +0.90 |
| `SEPARATOR` line | +0.85 |
| `HEADING_WEAK` after content block | +0.45 |
| 2+ consecutive blank lines | +0.25 |

Boundary confirmed when accumulated evidence ≥ 0.50.

### `section_map` building

The segmenter walks each segment's lines.  When a `LABEL` line matches a
profile `section_markers` key (case-insensitive), it opens a collection
bucket for that field.  Subsequent non-heading content lines are appended
until the next label or heading resets the active section.

---

## Layer D — Deterministic Field Extraction (`field_extractor.py`)

**Input:** `DocumentSegment`, `ParserProfile`
**Output:** `ExtractionCandidate`

Each field has 2–4 independent strategies tried in priority order:

### Field strategies

| Field | Strategy 1 (Labeled) | Strategy 2 (Structural) | Strategy 3 (Semantic) |
|-------|----------------------|------------------------|-----------------------|
| `title` | LABEL with title synonym | First HEADING/HEADING_WEAK | First short CONTINUATION |
| `category` | — | Category keyword rules | Regex scan |
| `product_or_system` | LABEL with product synonym | — | Product name regex |
| `symptoms` | `section_map["symptoms"]` | — | Negation + opener patterns |
| `resolution_steps` | `section_map["resolution_steps"]` | Longest numbered run | Bullets after label |
| `troubleshooting_steps` | `section_map["troubleshooting_steps"]` | Numbered run | Bullets after label |
| `escalation_criteria` | `section_map["escalation_criteria"]` | — | Escalation vocabulary scan |
| `tags` | From category + product | — | — |
| `short_summary` | First CONTINUATION lines | Derived from title | — |

Every extracted value is wrapped in `FieldExtraction` with:
- `confidence` — how certain the strategy is
- `method` — `DETERMINISTIC` or `HEURISTIC`
- `source_excerpt` — the line it was drawn from

---

## Layer D+ — LLM Enrichment (`llm_extractor.py`)

**Opt-in:** `settings.INGESTION_LLM_ENABLED = True`

**What it does:**
Only requests LLM output for fields whose confidence is below
`profile.thresholds.medium` (0.50 by default).  Merges LLM values into
the existing `ExtractionCandidate` with `method = COMBINED`.

**Hallucination guard:**
Any LLM-returned value is cross-checked against the segment text.  At
least one significant word from the value must appear in the segment.
Values failing this check are silently dropped.

**On any failure:**
The original deterministic candidate is returned unchanged.

---

## Confidence Scoring (`confidence.py`)

```
composite = Σ (field_weight × field_confidence) / total_weight
          + completeness_bonus (up to +0.08)
```

Weights come from `profile.confidence_weights` (tunable per profile):

| Field | Default weight |
|-------|---------------|
| `title` | 0.25 |
| `resolution_steps` | 0.20 |
| `category` | 0.15 |
| `symptoms` | 0.10 |
| `troubleshooting_steps` | 0.10 |
| `tags` | 0.05 |
| `product_or_system` | 0.05 |
| `short_summary` | 0.05 |
| `escalation_criteria` | 0.05 |

Completeness bonus:
- +0.04 if both symptoms and resolution_steps ≥ MEDIUM threshold
- +0.02 if escalation_criteria ≥ MEDIUM threshold
- +0.02 if `IS_COMPLETE_TOPIC` signal set

---

## Error Handling

| Failure | Behaviour |
|---------|-----------|
| File not found | Job → `failed`, error_details set |
| Text extraction error | Job → `failed` |
| Segmenter produces 0 segments | Job → `failed` |
| LLM timeout / error | Deterministic candidate used unchanged |
| Duplicate check DB error | Warning logged; candidate saved without hint |
| Persist error | Exception re-raised; job → `failed` |
