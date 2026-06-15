# Extraction Schema Reference

> Aditi IT Assist · Schema v2.0.0 · Last updated: 2026-06-15

The extraction schema is the **stable contract** between the parsing layer
and everything downstream (validator, confidence scorer, mapper, review UI).

---

## Schema Versioning

```python
SCHEMA_VERSION = "2.0.0"   # in schema.py
```

Every `ExtractionCandidate` carries `schema_version`.  Downstream code
checks this to handle forward compatibility.  When fields are added or
semantics change, bump the version following semver:

| Change | Version bump |
|--------|-------------|
| New optional field added | Minor (`2.1.0`) |
| Field renamed or removed | Major (`3.0.0`) |
| Confidence formula change | Patch (`2.0.1`) |

---

## `FieldExtraction` — Per-field container

Every field in `ExtractionCandidate` is a `FieldExtraction`:

```python
@dataclass
class FieldExtraction:
    value: object                  # str | list[str] | list[dict] | None
    confidence: float              # 0.0 – 1.0
    source_excerpt: str | None     # snippet the value was drawn from
    method: ExtractionMethod       # see below
    warnings: list[str]            # field-specific issues
```

### `ExtractionMethod` enum

| Value | Meaning |
|-------|---------|
| `DETERMINISTIC` | Rule/regex — highest trust |
| `HEURISTIC` | Structural inference |
| `LLM` | LLM-only |
| `COMBINED` | Deterministic + LLM agreed |
| `NOT_EXTRACTED` | Absent or skipped |

### Absent fields

Use `FieldExtraction.absent()` — never `None` for the field itself.
Check `field_extraction.is_present` to test presence.

---

## `ExtractionCandidate` — Full extraction result

```python
@dataclass
class ExtractionCandidate:
    # ── Provenance ────────────────────────────────
    schema_version: str           # "2.0.0"
    parser_version: str           # settings.INGESTION_PARSER_VERSION
    parser_profile: str           # profile name used
    candidate_index: int
    raw_segment_text: str
    semantic_signals: SemanticSignal

    # ── Core identity ─────────────────────────────
    title: FieldExtraction
    short_summary: FieldExtraction

    # ── Classification ────────────────────────────
    category: FieldExtraction     # value: str
    subcategory: FieldExtraction  # value: str
    product_or_system: FieldExtraction
    platform: FieldExtraction
    issue_type: FieldExtraction

    # ── Content ───────────────────────────────────
    symptoms: FieldExtraction              # value: list[str]
    probable_causes: FieldExtraction       # value: list[str]
    troubleshooting_steps: FieldExtraction # value: list[{step_number, instruction, details}]
    resolution_steps: FieldExtraction      # value: list[{step_number, instruction, details}]
    validation_steps: FieldExtraction
    escalation_criteria: FieldExtraction   # value: str
    escalation_target_team: FieldExtraction

    # ── Governance ────────────────────────────────
    tags: FieldExtraction                  # value: list[str]
    keywords: FieldExtraction              # value: list[str]

    # ── Composite quality ─────────────────────────
    extraction_confidence: float           # 0.0 – 1.0
    confidence_level: str                  # HIGH|MEDIUM|LOW|VERY_LOW
    review_required: bool
    parser_warnings: list[str]
    extraction_metadata: dict              # for JSONB storage
```

---

## Confidence Levels

| Level | Score | `review_required` | UI colour |
|-------|-------|-------------------|-----------|
| `HIGH` | ≥ 0.75 | False | Green |
| `MEDIUM` | ≥ 0.50 | False | Yellow |
| `LOW` | ≥ 0.30 | **True** | Orange |
| `VERY_LOW` | < 0.30 | **True** | Red |

---

## `SemanticSignal` flags

Bit flags set by the segmenter, consumed by the extractor and confidence scorer:

| Flag | Meaning |
|------|---------|
| `HAS_PROBLEM` | Contains problem/symptom vocabulary |
| `HAS_RESOLUTION` | Contains resolution/fix vocabulary |
| `HAS_TROUBLESHOOTING` | Contains diagnostic step vocabulary |
| `HAS_ESCALATION` | Contains escalation vocabulary |
| `HAS_PRODUCT` | Product name detected |
| `HAS_STEPS` | Numbered/procedural steps detected |
| `IS_COMPLETE_TOPIC` | Both HAS_PROBLEM + HAS_RESOLUTION |

---

## `extraction_metadata` JSONB payload

Stored in `IngestionCandidate.normalized_payload_json`:

```json
{
  "schema_version": "2.0.0",
  "parser_profile": "it_support_v1",
  "parser_version": "2.0.0",
  "confidence_level": "medium",
  "review_required": true,
  "parser_warnings": ["No symptoms detected."],
  "field_confidences": {
    "title": 0.90,
    "category": 0.80,
    "short_summary": 0.55,
    "symptoms": 0.0,
    "troubleshooting_steps": 0.88,
    "resolution_steps": 0.88,
    "escalation_criteria": 0.62,
    "tags": 0.72,
    "product_or_system": 0.75
  },
  "extraction_metadata": {
    "title": {"confidence": 0.90, "method": "deterministic", "warnings": [], "excerpt": "## Outlook Not Receiving Emails"},
    ...
  }
}
```

---

## Adding a New Field

1. Add a `FieldExtraction` attribute to `ExtractionCandidate` in `schema.py`
2. Bump `SCHEMA_VERSION` minor version
3. Add extraction strategy in `field_extractor.py`
4. Add weight to `ConfidenceWeights` in `profiles/base.py`
5. Add field to `_SCOREABLE_FIELDS` in `confidence.py`
6. Add TypeScript field to `frontend/src/types/ingestion.ts`
7. Add test fixture assertion in `test_ingestion_adaptive.py`

---

## Migration: v1 → v2

Candidates produced by the v1 pipeline (`parser_version < 2.0.0`) have:

- `normalized_payload_json = null` — no extraction metadata
- `extracted_confidence` — single numeric score only
- No per-field confidences exposed to UI

The frontend handles this gracefully: `ExtractionMetaBanner` only renders
when `schema_version` is present; `ConfidenceBadge` falls back to
`extracted_confidence` when `confidence_level` is null.

Old candidates can be re-extracted via the `/retry` endpoint.
