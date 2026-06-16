# Entity Normalization

> Maps fuzzy user-typed product names to canonical system identifiers.

---

## Problem Statement

Users refer to IT systems in many ways:
- "sixthsenses", "sixth sense", "Sixth Sense", "naukri", "SS portal"
- "ms outlook", "outlook365", "o365 mail"
- "zoomm", "zoom meeting", "zoom app"

The system must recognize all variants and map them to a single canonical
name for consistent routing, retrieval, and playbook matching.

## Design

### Three-Phase Matching

1. **Exact Match** — full text against alias registry (conf 1.0)
2. **Substring Match** — alias appears within the sentence (conf 0.9)
3. **Fuzzy Match** — edit-distance for typos (conf 0.6–0.85)

### Data Model

```python
@dataclass
class EntityMatch:
    canonical_name: str    # e.g. "sixth_sense"
    display_name: str      # e.g. "Sixth Sense (Naukri)"
    category: str          # e.g. "access/sixth_sense"
    matched_text: str      # what the user actually wrote
    confidence: float      # 0.0–1.0
    method: str            # "exact" | "alias" | "fuzzy"
    common_issues: list[str]
```

### Alias Registry

The alias registry is defined in `entity_normalizer.py` as a flat list
of `SystemEntity` objects. Each entity has:

- A list of known aliases (lowercase)
- The canonical category for playbook routing
- Common issue subtypes

### Fuzzy Matching Strategy

For fuzzy matching, the system:
1. Splits user text into individual words and bigrams
2. Also creates concatenated bigrams (e.g. "sixth" + "senses" → "sixthsenses")
3. Compares each candidate against all aliases using `SequenceMatcher`
4. Accepts matches with ratio > 0.75
5. Scales confidence: `ratio * 0.85`

This catches typos like:
- "sixthsenses" → "sixthsense" (ratio ~0.91)
- "naukhri" → "naukri" (ratio ~0.83)

## Integration Points

- **Triage Node** — runs entity normalization on every message
- **Diagnostic Context** — stores `normalized_system`, `raw_system_mention`
- **Playbook Router** — `get_playbook_for_entity(canonical_name)`
- **Retrieval Node** — uses entity name in focused queries
- **Escalation Node** — includes entity in handoff summary

## Testing

See `tests/unit/test_entity_normalizer.py` for comprehensive tests
covering exact matches, typos, sentence extraction, and edge cases.
