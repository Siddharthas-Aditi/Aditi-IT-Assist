"""Layer D — Deterministic rule-based field extractor.

Takes a ``DocumentSegment`` (Layer C output) and a ``ParserProfile`` and
produces an ``ExtractionCandidate`` by applying multiple independent
extraction strategies per field.

ADAPTIVE DESIGN:
  - Every field has 2–4 independent strategies tried in priority order.
  - Strategy priority: labeled-section > structural-heading > semantic-scan.
  - Strategies read ``segment.section_map`` first (built from profile labels),
    then fall back to scanning all lines.
  - Adding a new field strategy never touches other fields.
  - Document position is NEVER assumed.

Strategy tiers (each field picks the highest-confidence successful result):
  1. ``section_map`` lookup — segmenter already tagged labeled sections
  2. Structural-context inference — adjacent heading / numbered run
  3. Semantic vocabulary scan — keyword / negation / product-name patterns
  4. Last-resort derivation — build a plausible value from whatever is present
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.services.ingestion.normalizer import LineType, NormalizedLine
from app.services.ingestion.schema import (
    ExtractionCandidate,
    ExtractionMethod,
    ExtractionStep,
    FieldExtraction,
)

if TYPE_CHECKING:
    from app.services.ingestion.profiles.base import ParserProfile
    from app.services.ingestion.segmenter import DocumentSegment

# ── Category detection lookup table ──────────────────────────────────────────
# Ordered by specificity — first match wins.
_CATEGORY_RULES: list[tuple[re.Pattern, tuple[str, str | None]]] = [
    (re.compile(r"\boutlook\b|\bexchange\b|\bemail\s+client\b", re.I), ("email/outlook", None)),
    (re.compile(r"\bemail\b", re.I), ("email/outlook", "general")),
    (re.compile(r"\bms\s*teams\b|\bmicrosoft\s+teams\b", re.I), ("video-conferencing/teams", None)),
    (re.compile(r"\bzoom\b", re.I), ("video-conferencing/zoom", None)),
    (
        re.compile(r"\bintune\b|\bmdm\b|\bdevice\s+enrollment\b|\bdevice\s+management\b", re.I),
        ("device-management/intune", None),
    ),
    (re.compile(r"\bcamera\b|\bwebcam\b", re.I), ("hardware/camera", None)),
    (re.compile(r"\bvpn\b|\bvirtual\s+private\s+network\b", re.I), ("network/connectivity", "vpn")),
    (
        re.compile(r"\bwifi\b|\bwi-fi\b|\bwireless\s+network\b", re.I),
        ("network/connectivity", "wifi"),
    ),
    (
        re.compile(r"\bdns\b|\bip\s+address\b|\bnetwork\s+connectivity\b", re.I),
        ("network/connectivity", "general"),
    ),
    (
        re.compile(r"\bmfa\b|\bmulti.factor\b|\bauthenticator\b", re.I),
        ("access/permissions", "mfa"),
    ),
    (
        re.compile(r"\baccess\s+denied\b|\bpermission\s+denied\b|\brunas\b", re.I),
        ("access/permissions", "general"),
    ),
    (
        re.compile(r"\bpassword\b|\bpassphrase\b|\bcredential\b", re.I),
        ("access/permissions", "password"),
    ),
    (
        re.compile(r"\bmonitor\b|\bdisplay\b|\bscreen\s+resolution\b|\bdual\s+monitor\b", re.I),
        ("hardware/other", "display"),
    ),
    (re.compile(r"\bprinter\b|\bprint\b|\bscanner\b", re.I), ("hardware/other", "printer")),
    (
        re.compile(r"\bslow\b|\bperformance\b|\blagging\b|\bfreez", re.I),
        ("hardware/other", "performance"),
    ),
    (
        re.compile(r"\binstall\b|\bsetup\b|\bdeployment\b|\bprovisioning\b", re.I),
        ("software/other", "install"),
    ),
    (
        re.compile(r"\bcrash\b|\bnot\s+respond\b|\bblue\s+screen\b|\bbsod\b", re.I),
        ("software/other", "crash"),
    ),
    (re.compile(r"\blicense\b|\bactivation\b", re.I), ("software/other", "license")),
    (
        re.compile(r"\bsharepoint\b|\bonedrive\b|\bm365\b|\boffice\s+365\b", re.I),
        ("software/other", "general"),
    ),
]

# Known products — ordered longest-first for greedy matching
_KNOWN_PRODUCTS = [
    "Microsoft 365",
    "Office 365",
    "Azure Active Directory",
    "Azure AD",
    "Entra ID",
    "Microsoft Entra",
    "Windows 11",
    "Windows 10",
    "Windows",
    "OneDrive",
    "SharePoint",
    "Microsoft Teams",
    "Outlook",
    "Office",
    "Zoom",
    "Intune",
    "Edge",
    "Chrome",
    "Firefox",
    "Safari",
    "Slack",
    "ServiceNow",
    "macOS",
    "iOS",
    "Android",
    "Linux",
]
_PRODUCT_RE = re.compile(r"\b(" + "|".join(re.escape(p) for p in _KNOWN_PRODUCTS) + r")\b", re.I)

_PLATFORM_RE = re.compile(
    r"\b(Windows\s+1[01]|Windows\s+Server\s+\d{4}|Windows|macOS|iOS|Android|Linux|Ubuntu|RedHat)\b",
    re.I,
)

# Negative-sentiment patterns for symptom detection
_NEGATIVE_RE = re.compile(
    r"\b(?:not\s+\w+|can(?:not|'t)\s+\w+|won't\s+\w+|doesn'?t\s+\w+|"
    r"fails?\s+to\s+\w+|unable\s+to\s+\w+|no\s+\w+\s+(?:showing|appearing|working)|"
    r"keeps?\s+(?:crashing|failing|showing)|error\s+\w+|missing\s+\w+)\b",
    re.I,
)

# Escalation vocabulary (local — not imported from segmenter)
_ESCALATION_RE = re.compile(
    r"\b(?:escalate|escalation|contact\s+(?:it|support|helpdesk)|service\s+desk|"
    r"if\s+the\s+(?:issue|problem)\s+persists|if\s+(?:still|unresolved)|"
    r"further\s+assistance|reach\s+out|raise\s+a\s+ticket)\b",
    re.I,
)

# Symptom opener patterns (the line is likely a symptom if it starts with these)
_SYMPTOM_OPENER_RE = re.compile(
    r"^(?:user|employee|device|system|app|application|the\s+(?:user|device)|"
    r"when|after|i\s+(?:can|cannot)|cannot|unable|fails?|doesn'?t)\b",
    re.I,
)


# ── Public API ─────────────────────────────────────────────────────────────────


def extract_fields(
    segment: DocumentSegment,
    profile: ParserProfile,
    candidate_index: int = 0,
    parser_version: str = "2.0.0",
) -> ExtractionCandidate:
    """Run deterministic field extraction on *segment* and return a candidate.

    This is the single entry point for Layer D.  Every field is extracted
    independently — a failure in one field never prevents others.
    """
    c = ExtractionCandidate(
        parser_profile=profile.name,
        parser_version=parser_version,
        candidate_index=candidate_index,
        raw_segment_text=segment.raw_text,
        semantic_signals=segment.signals,
    )

    c.title = _title(segment, profile)
    c.category, c.subcategory = _category(segment)
    c.product_or_system = _product(segment)
    c.platform = _platform(segment)
    c.symptoms = _list_field(segment, profile, "symptoms")
    c.probable_causes = _list_field(segment, profile, "probable_causes")
    c.troubleshooting_steps = _steps_field(segment, profile, "troubleshooting_steps")
    c.resolution_steps = _steps_field(segment, profile, "resolution_steps")
    c.validation_steps = _steps_field(segment, profile, "validation_steps")
    c.escalation_criteria = _escalation(segment, profile)
    c.tags, c.keywords = _tags_and_keywords(segment, c.category, c.product_or_system)
    c.short_summary = _summary(segment, c.title)

    return c


# ── Title ─────────────────────────────────────────────────────────────────────


def _title(segment: DocumentSegment, profile: ParserProfile) -> FieldExtraction:
    # Strategy 1: explicit heading detected by segmenter (high confidence)
    if segment.heading:
        cleaned = _clean_title(segment.heading)
        if len(cleaned) >= 5:
            return FieldExtraction.make(
                cleaned, 0.90, method=ExtractionMethod.DETERMINISTIC, excerpt=segment.heading
            )

    # Strategy 2: first LABEL line whose label is a title synonym
    _title_synonyms = {"title", "topic", "issue", "article", "name", "subject"}
    for line in segment.lines[:8]:
        if (
            line.line_type == LineType.LABEL
            and line.label
            and line.label.lower() in _title_synonyms
            and line.text
            and len(line.text) >= 5
        ):
            return FieldExtraction.make(
                line.text.strip(), 0.85, method=ExtractionMethod.DETERMINISTIC, excerpt=line.raw
            )

    # Strategy 3: first short CONTINUATION line that looks like a title
    for line in segment.lines[:5]:
        txt = line.text.strip()
        if (
            line.line_type == LineType.CONTINUATION
            and 5 <= len(txt) <= 120
            and re.match(r"^[A-Z]", txt)
            and not txt.endswith(".")
        ):
            return FieldExtraction.make(
                txt, 0.55, method=ExtractionMethod.HEURISTIC, excerpt=line.raw
            )

    # Strategy 4: first HEADING_WEAK
    for line in segment.lines[:8]:
        if line.line_type == LineType.HEADING_WEAK and line.text:
            cleaned = _clean_title(line.text)
            if len(cleaned) >= 5:
                return FieldExtraction.make(
                    cleaned, 0.50, method=ExtractionMethod.HEURISTIC, excerpt=line.raw
                )

    return FieldExtraction.absent()


def _clean_title(raw: str) -> str:
    s = re.sub(r"^#{1,4}\s+", "", raw)
    s = re.sub(r"^(?:Issue|Problem|Topic|Title|Article|Subject):\s*", "", s, flags=re.I)
    s = re.sub(r"^\d+[\.\)]\s+", "", s)
    return s.strip()


# ── Category & subcategory ────────────────────────────────────────────────────


def _category(segment: DocumentSegment) -> tuple[FieldExtraction, FieldExtraction]:
    text = segment.raw_text
    for pattern, (cat, sub) in _CATEGORY_RULES:
        m = pattern.search(text)
        if m:
            cat_fe = FieldExtraction.make(
                cat, 0.80, method=ExtractionMethod.DETERMINISTIC, excerpt=m.group(0)
            )
            sub_fe = (
                FieldExtraction.make(sub, 0.70, method=ExtractionMethod.DETERMINISTIC)
                if sub
                else FieldExtraction.absent()
            )
            return cat_fe, sub_fe
    return FieldExtraction.absent(), FieldExtraction.absent()


# ── Product ───────────────────────────────────────────────────────────────────


def _product(segment: DocumentSegment) -> FieldExtraction:
    # Strategy 1: labeled section (e.g. "Affected System: Outlook")
    for line in segment.lines[:10]:
        if (
            line.line_type == LineType.LABEL
            and line.label
            and any(
                kw in line.label.lower()
                for kw in ("product", "system", "application", "app", "software", "affected")
            )
        ):
            m = _PRODUCT_RE.search(line.text) if line.text else None
            if m:
                return FieldExtraction.make(
                    m.group(1), 0.90, method=ExtractionMethod.DETERMINISTIC, excerpt=line.raw
                )

    # Strategy 2: product name regex scan
    m = _PRODUCT_RE.search(segment.raw_text)
    if m:
        return FieldExtraction.make(
            m.group(1), 0.75, method=ExtractionMethod.DETERMINISTIC, excerpt=m.group(0)
        )

    return FieldExtraction.absent()


# ── Platform ──────────────────────────────────────────────────────────────────


def _platform(segment: DocumentSegment) -> FieldExtraction:
    m = _PLATFORM_RE.search(segment.raw_text)
    if m:
        return FieldExtraction.make(
            m.group(1), 0.72, method=ExtractionMethod.DETERMINISTIC, excerpt=m.group(0)
        )
    return FieldExtraction.absent()


# ── Generic list field (symptoms, probable_causes) ────────────────────────────


def _list_field(
    segment: DocumentSegment,
    profile: ParserProfile,
    field_name: str,
) -> FieldExtraction:
    # Strategy 1: labeled section from section_map
    section_lines = segment.section_map.get(field_name, [])
    if section_lines:
        items = [line.strip() for line in section_lines if line.strip()][:10]
        if items:
            return FieldExtraction.make(
                items, 0.88, method=ExtractionMethod.DETERMINISTIC, excerpt=section_lines[0]
            )

    # Strategy 2: field-specific semantic scan
    if field_name == "symptoms":
        return _symptoms_semantic_scan(segment)
    if field_name == "probable_causes":
        return _causes_semantic_scan(segment)

    return FieldExtraction.absent()


def _symptoms_semantic_scan(segment: DocumentSegment) -> FieldExtraction:
    """Scan all lines for symptom-like content."""
    items: list[str] = []
    for line in segment.lines:
        if line.line_type in (LineType.BULLET, LineType.NUMBERED):
            if _NEGATIVE_RE.search(line.text) or _SYMPTOM_OPENER_RE.match(line.text):
                items.append(line.text.strip())
                if len(items) >= 8:
                    break
        elif line.line_type == LineType.CONTINUATION and _NEGATIVE_RE.search(line.text):
            items.append(line.text.strip())
            if len(items) >= 8:
                break
    if items:
        return FieldExtraction.make(
            items, 0.58, method=ExtractionMethod.HEURISTIC, excerpt=items[0]
        )
    return FieldExtraction.absent()


def _causes_semantic_scan(segment: DocumentSegment) -> FieldExtraction:
    """Look for causal language patterns."""
    cause_re = re.compile(
        r"\b(?:caused\s+by|due\s+to|because|reason(?:ed|s)?|root\s+cause|as\s+a\s+result\s+of)\b",
        re.I,
    )
    items: list[str] = []
    for line in segment.lines:
        if cause_re.search(line.text):
            items.append(line.text.strip())
            if len(items) >= 5:
                break
    if items:
        return FieldExtraction.make(
            items, 0.55, method=ExtractionMethod.HEURISTIC, excerpt=items[0]
        )
    return FieldExtraction.absent()


# ── Step-based list fields (resolution, troubleshooting, validation) ──────────


def _steps_field(
    segment: DocumentSegment,
    profile: ParserProfile,
    field_name: str,
) -> FieldExtraction:
    # Strategy 1: labeled section from section_map
    section_lines = segment.section_map.get(field_name, [])
    if section_lines:
        steps = _lines_to_steps(section_lines)
        if steps:
            return FieldExtraction.make(
                [s.to_dict() for s in steps],
                0.90,
                method=ExtractionMethod.DETERMINISTIC,
                excerpt=section_lines[0],
            )

    # Strategy 2: longest numbered run in segment (heuristic — most likely to be steps)
    run = _longest_numbered_run(segment.lines)
    if run and len(run) >= 2 and field_name in ("resolution_steps", "troubleshooting_steps"):
        steps = [
            ExtractionStep(step_number=i + 1, instruction=line.text.strip())
            for i, line in enumerate(run)
            if line.text.strip()
        ]
        return FieldExtraction.make(
            [s.to_dict() for s in steps],
            0.62,
            method=ExtractionMethod.HEURISTIC,
            excerpt=run[0].text,
        )

    # Strategy 3: bullet list adjacent to a matching label line
    labeled_bullets = _bullets_after_label(segment.lines, profile, field_name)
    if labeled_bullets:
        steps = _lines_to_steps([line.text for line in labeled_bullets])
        if steps:
            return FieldExtraction.make(
                [s.to_dict() for s in steps],
                0.72,
                method=ExtractionMethod.HEURISTIC,
            )

    return FieldExtraction.absent()


# ── Escalation criteria ───────────────────────────────────────────────────────


def _escalation(segment: DocumentSegment, profile: ParserProfile) -> FieldExtraction:
    # Strategy 1: labeled section
    section_lines = segment.section_map.get("escalation_criteria", []) or segment.section_map.get(
        "escalation", []
    )
    if section_lines:
        text = " ".join(line.strip() for line in section_lines if line.strip())[:600]
        return FieldExtraction.make(
            text, 0.88, method=ExtractionMethod.DETERMINISTIC, excerpt=section_lines[0]
        )

    # Strategy 2: scan lines for escalation vocabulary
    for i, line in enumerate(segment.lines):
        if _ESCALATION_RE.search(line.text):
            chunk_lines = segment.lines[i : i + 4]
            chunk = " ".join(cl.text for cl in chunk_lines if cl.text)[:600]
            return FieldExtraction.make(
                chunk, 0.62, method=ExtractionMethod.HEURISTIC, excerpt=line.text
            )

    return FieldExtraction.absent()


# ── Tags and keywords ─────────────────────────────────────────────────────────


def _tags_and_keywords(
    segment: DocumentSegment,
    cat_fe: FieldExtraction,
    product_fe: FieldExtraction,
) -> tuple[FieldExtraction, FieldExtraction]:
    tags: list[str] = []

    # Tag from category
    if cat_fe.is_present:
        primary = str(cat_fe.value).split("/")[0]
        tags.append(primary)

    # Tag from product
    if product_fe.is_present:
        tags.append(str(product_fe.value).lower())

    # Keywords — TitleCase words from segment (likely proper nouns/product names)
    seen: set[str] = {t.lower() for t in tags}
    keywords: list[str] = []
    for m in re.finditer(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*)\b", segment.raw_text):
        word = m.group(1)
        if word.lower() not in seen and len(word) >= 4:
            seen.add(word.lower())
            keywords.append(word)
        if len(keywords) >= 15:
            break

    tags_conf = 0.72 if tags else 0.0
    kw_conf = 0.50 if keywords else 0.0
    return (
        FieldExtraction.make(tags, tags_conf, method=ExtractionMethod.DETERMINISTIC),
        FieldExtraction.make(keywords, kw_conf, method=ExtractionMethod.HEURISTIC),
    )


# ── Short summary ─────────────────────────────────────────────────────────────


def _summary(segment: DocumentSegment, title_fe: FieldExtraction) -> FieldExtraction:
    # Strategy 1: first CONTINUATION lines after heading (up to 600 chars)
    parts: list[str] = []
    for line in segment.lines:
        if line.line_type == LineType.CONTINUATION and len(line.text) > 20:
            parts.append(line.text.strip())
        if sum(len(p) for p in parts) >= 300:
            break
    if parts:
        summary = " ".join(parts)[:600]
        return FieldExtraction.make(summary, 0.55, method=ExtractionMethod.HEURISTIC)

    # Strategy 2: derive from title
    if title_fe.is_present:
        return FieldExtraction.make(
            f"Troubleshooting guide: {title_fe.value}",
            0.35,
            method=ExtractionMethod.HEURISTIC,
        )

    return FieldExtraction.absent()


# ── Helpers ────────────────────────────────────────────────────────────────────


def _lines_to_steps(text_lines: list[str]) -> list[ExtractionStep]:
    """Convert text lines into numbered ExtractionStep objects."""
    steps: list[ExtractionStep] = []
    for raw_line in text_lines:
        line = raw_line.strip()
        if not line:
            continue
        # Strip leading number/bullet markers
        cleaned = re.sub(
            r"^(?:\d+[\.\):\-]?\s+|[•\-\*◦▸]\s+|step\s+\d+[:\.\)]\s+)", "", line, flags=re.I
        )
        if cleaned:
            steps.append(ExtractionStep(step_number=len(steps) + 1, instruction=cleaned))
    return steps[:25]


def _longest_numbered_run(
    lines: list[NormalizedLine],
    min_len: int = 2,
) -> list[NormalizedLine] | None:
    """Return the longest contiguous NUMBERED line run (≥ min_len)."""
    best: list[NormalizedLine] = []
    current: list[NormalizedLine] = []
    for line in lines:
        if line.line_type == LineType.NUMBERED:
            current.append(line)
        else:
            if len(current) > len(best):
                best = current
            current = []
    if len(current) > len(best):
        best = current
    return best if len(best) >= min_len else None


def _bullets_after_label(
    lines: list[NormalizedLine],
    profile: ParserProfile,
    field_name: str,
) -> list[NormalizedLine]:
    """Return bullet/numbered lines that immediately follow a label for *field_name*."""
    result: list[NormalizedLine] = []
    collecting = False
    for line in lines:
        if line.line_type == LineType.LABEL and profile.matches_label(
            f"{line.label or line.raw.strip()}:", field_name
        ):
            collecting = True
            continue
        if collecting:
            if line.line_type in (LineType.BULLET, LineType.NUMBERED):
                result.append(line)
            elif line.line_type in (LineType.HEADING, LineType.HEADING_WEAK, LineType.LABEL):
                break  # A new section started
            elif line.line_type == LineType.CONTINUATION and result:
                # Only allow one continuation line between bullets
                pass
    return result[:20]
