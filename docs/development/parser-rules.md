# Parser Rules — Adding and Tuning Parser Profiles

> Aditi IT Assist · Pipeline v2 · Last updated: 2026-06-15

This guide explains how to support a new IT document format or tune extraction
quality **without changing any extraction code** — only parser profile data.

---

## Core Principle

The adaptive ingestion pipeline reads all document-family-specific knowledge
from a `ParserProfile` object.  The extraction engine (`field_extractor.py`,
`segmenter.py`) is **profile-agnostic**.

```
new_document_format → new ParserProfile → register → done
```

---

## ParserProfile Reference

```python
@dataclass
class ParserProfile:
    name: str              # Unique id, e.g. "it_support_v1"
    version: str           # Semantic version; increment when markers change
    description: str       # Human-readable description

    # ── Section label mappings (most important field) ──────────────────────
    # Maps schema field names → list of label strings that identify
    # that section in a document (case-insensitive prefix match + ":").
    # The MORE variants you list, the more document styles are supported.
    section_markers: dict[str, list[str]]

    # ── Structural signals ──────────────────────────────────────────────────
    # Extra regex patterns that identify headings in this document family.
    heading_signals: list[re.Pattern]
    # Regex patterns that mark a topic boundary (e.g. "---" or "====").
    topic_separators: list[re.Pattern]

    # ── Confidence tuning ──────────────────────────────────────────────────
    confidence_weights: ConfidenceWeights  # per-field weight
    thresholds: ReviewThresholds           # HIGH / MEDIUM / LOW cutoffs

    # ── Auto-detection ──────────────────────────────────────────────────────
    detection: DetectionCriteria
    # detection.keyword_signals: words that suggest this profile
    # detection.min_keyword_matches: minimum hits to activate
```

---

## Step-by-Step: Adding a New Profile

### 1. Create the profile file

```
backend/app/services/ingestion/profiles/my_format.py
```

```python
from __future__ import annotations
import re
from app.services.ingestion.profiles.base import (
    ConfidenceWeights, DetectionCriteria, ParserProfile, ReviewThresholds,
)

MY_FORMAT_PROFILE = ParserProfile(
    name="my_format_v1",
    version="1.0.0",
    description="Format description",

    section_markers={
        # List ALL label variants you've seen in real documents
        "symptoms": [
            "symptom", "symptoms", "issue description", "observed behavior",
            "what the user sees", "reported issue",
        ],
        "resolution_steps": [
            "resolution", "fix", "solution", "corrective action",
            "steps to fix", "how to resolve",
        ],
        "troubleshooting_steps": [
            "troubleshooting", "diagnosis", "investigation",
            "steps to diagnose",
        ],
        "escalation_criteria": [
            "escalation", "escalate", "when to escalate",
            "contact support if",
        ],
        "probable_causes": [
            "cause", "causes", "root cause", "probable cause",
        ],
    },

    heading_signals=[
        re.compile(r"^SECTION\s+\d+:", re.I),  # "SECTION 3: ..."
    ],

    topic_separators=[
        re.compile(r"^={3,}"),   # ======
        re.compile(r"^-{3,}"),   # ------
    ],

    # Tune weights if this format is resolution-heavy
    confidence_weights=ConfidenceWeights(
        title=0.25, resolution_steps=0.25, category=0.15,
        symptoms=0.10, troubleshooting_steps=0.10,
        tags=0.05, product_or_system=0.05,
        short_summary=0.03, escalation_criteria=0.02,
    ),

    thresholds=ReviewThresholds(high=0.75, medium=0.50, low=0.30),

    detection=DetectionCriteria(
        # Words likely found in this document type (not in other types)
        keyword_signals=["your_unique_keyword", "another_signal"],
        min_keyword_matches=2,
    ),
)
```

### 2. Register the profile

In `profiles/registry.py`, add:

```python
from app.services.ingestion.profiles.my_format import MY_FORMAT_PROFILE
_REGISTRY[MY_FORMAT_PROFILE.name] = MY_FORMAT_PROFILE
```

### 3. Test with real documents

```python
from app.services.ingestion.normalizer import normalize_document
from app.services.ingestion.profiles.registry import detect_profile
from app.services.ingestion.segmenter import segment_document
from app.services.ingestion.field_extractor import extract_fields

raw_text = open("my_doc.txt").read()
norm = normalize_document(raw_text)
profile = detect_profile(raw_text)   # Should return MY_FORMAT_PROFILE
segments = segment_document(norm, profile)
candidates = [extract_fields(seg, profile, i) for i, seg in enumerate(segments)]

for c in candidates:
    print(c.title.value, c.title.confidence, c.resolution_steps.is_present)
```

---

## Tuning Section Labels

The most common issue is that label variants in uploaded documents don't
match the profile.  Examples of label drift:

| What the doc says | Add this variant |
|-------------------|-----------------|
| `Fix:` | `"fix"` |
| `How to fix:` | `"how to fix"` |
| `Steps to resolve the issue:` | `"steps to resolve the issue"` |
| `Suggested Actions:` | `"suggested actions"` |
| `Workaround:` | `"workaround"` |

Just add the new string to the relevant list in `section_markers`.
**No code change.  Increment profile `version`.**

---

## Tuning Confidence Weights

If reviewers say "the confidence scores are too high / low":

- **Too high for low-quality docs**: reduce the weight of `resolution_steps` (it's the most forgiving field)
- **Resolution-heavy docs scoring low**: increase `resolution_steps` weight, reduce `symptoms`
- **Category often missing**: reduce `category` weight slightly so missing category doesn't tank the score

The total of all weights doesn't need to be 1.0 — the scorer normalises by
`total_weight`.

---

## Tuning Review Thresholds

`ReviewThresholds` controls when the UI shows "Review required":

```python
ReviewThresholds(
    high=0.75,    # ≥ 0.75 → no banner, save directly
    medium=0.50,  # ≥ 0.50 → "Review recommended" banner
    low=0.30,     # ≥ 0.30 → "Review required" banner
    # < 0.30 → candidate kept but marked for retry
)
```

For document families where content is consistently sparse (e.g. quick-fix
one-pagers), consider lowering `medium` to `0.40` to reduce noise.

---

## Testing Your Profile

Add fixtures in `backend/tests/unit/test_ingestion_adaptive.py`:

```python
FIXTURE_MY_FORMAT = """
<paste a real doc excerpt>
"""

class TestMyFormat:
    def test_title(self):
        c = _run(FIXTURE_MY_FORMAT)[0]
        assert c.title.is_present

    def test_resolution_extracted(self):
        c = _run(FIXTURE_MY_FORMAT)[0]
        assert c.resolution_steps.is_present
```

Run with: `cd backend && uv run pytest tests/unit/test_ingestion_adaptive.py -v`

---

## Adding a New Field Strategy

If the deterministic strategies miss a field for your document type, add a new
strategy to `field_extractor.py` **inside the relevant field function only**.
The strategy pattern is:

```python
# Strategy N: description
items_or_value = my_new_detection_logic(segment)
if items_or_value:
    return FieldExtraction.make(
        items_or_value, 0.70,
        method=ExtractionMethod.DETERMINISTIC,
        excerpt="source text",
    )
```

Since every field function tries strategies in order and returns the first
successful result, your new strategy won't break existing extractions.
