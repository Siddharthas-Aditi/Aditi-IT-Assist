"""Structural parser — converts raw document text into candidate payloads.

The parser uses deterministic heuristics only (no LLM).  Its job is to:
1. Split the raw text into topic segments (one segment ≈ one KB article).
2. Extract structured fields from each segment:
   - title, symptoms, troubleshooting steps, resolution steps, escalation
   - category, product/system, platform, tags, keywords
3. Wrap each segment as a ``CandidatePayload`` for the pipeline.

Heuristics are intentionally conservative — it is better to under-extract and
let LLM enrichment or human review fill gaps than to hallucinate structure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Category keyword map ──────────────────────────────────────────────────────
# Maps partial keyword → (category, subcategory) tuple.
_CATEGORY_KEYWORDS: list[tuple[re.Pattern, tuple[str, str]]] = [
    (re.compile(r"\boutlook\b", re.I), ("email/outlook", "general")),
    (re.compile(r"\bemail\b", re.I), ("email/outlook", "general")),
    (re.compile(r"\bzoom\b", re.I), ("video-conferencing/zoom", "general")),
    (re.compile(r"\bteams\b", re.I), ("video-conferencing/teams", "general")),
    (re.compile(r"\bintune\b", re.I), ("device-management/intune", "general")),
    (re.compile(r"\bmdm\b", re.I), ("device-management/intune", "general")),
    (re.compile(r"\bcamera\b|\bwebcam\b", re.I), ("hardware/camera", "general")),
    (re.compile(r"\bvpn\b", re.I), ("network/connectivity", "vpn")),
    (re.compile(r"\bwifi\b|\bwi-fi\b|\bwireless\b", re.I), ("network/connectivity", "wifi")),
    (
        re.compile(r"\baccess denied\b|\bpermission\b|\brbac\b|\bmfa\b", re.I),
        ("access/permissions", "general"),
    ),
    (re.compile(r"\bpassword\b", re.I), ("access/permissions", "password")),
    (re.compile(r"\bslow\b|\bperformance\b|\blagging\b", re.I), ("hardware/other", "performance")),
    (re.compile(r"\bmonitor\b|\bdisplay\b|\bscreen\b", re.I), ("hardware/other", "display")),
    (re.compile(r"\bkeyboard\b|\bmouse\b|\bperipheral\b", re.I), ("hardware/other", "peripheral")),
    (re.compile(r"\bprinter\b|\bprint\b", re.I), ("hardware/other", "printer")),
    (re.compile(r"\binstall\b|\binstallation\b", re.I), ("software/other", "install")),
    (re.compile(r"\bcrash\b|\bfreezing\b|\bnot respond", re.I), ("software/other", "crash")),
]

# ── Product / system extraction patterns ─────────────────────────────────────
_KNOWN_PRODUCTS = [
    "Outlook",
    "Microsoft 365",
    "M365",
    "Office 365",
    "OneDrive",
    "SharePoint",
    "Teams",
    "Zoom",
    "Intune",
    "Azure AD",
    "Entra ID",
    "Windows",
    "macOS",
    "Chrome",
    "Edge",
    "Firefox",
    "Slack",
    "ServiceNow",
]
_PRODUCT_RE = re.compile(r"\b(" + "|".join(re.escape(p) for p in _KNOWN_PRODUCTS) + r")\b", re.I)

# ── Topic heading patterns ────────────────────────────────────────────────────
# A line is a heading candidate if it matches one of these.
_HEADING_PATTERNS: list[re.Pattern] = [
    re.compile(r"^#{1,3}\s+.+$"),  # Markdown heading
    re.compile(r"^[A-Z][A-Z\s\-/]{4,60}$"),  # ALL-CAPS heading 5–61 chars
    re.compile(r"^\d+[\.\)]\s+[A-Z].+$"),  # Numbered: "1. Title" or "1) Title"
    re.compile(r"^(?:Issue|Problem|Topic|Section|Title):\s*.+$", re.I),  # Labelled heading
]

# ── Symptom / step / escalation line patterns ─────────────────────────────────
_SYMPTOM_LEAD = re.compile(r"^(?:[-•*]\s+|symptoms?:|when\s|users?\s|issue:|problem:)", re.I)
_STEP_LEAD = re.compile(r"^(?:\d+[\.\)]\s+|step\s+\d+[:\.\)]?\s+|[-•*]\s+)", re.I)
_RESOLUTION_SECTION = re.compile(
    r"^(?:resolution|solution|fix|steps?\s+to\s+(?:resolve|fix)|how\s+to\s+fix)", re.I
)
_TROUBLESHOOT_SECTION = re.compile(
    r"^(?:troubleshoot|troubleshooting|diagnosis|diagnostic|investigation)", re.I
)
_SYMPTOM_SECTION = re.compile(r"^(?:symptoms?|signs?|indicators?|manifestation)", re.I)
_ESCALATION_SECTION = re.compile(
    r"^(?:escalat|reach\s+out|contact\s+it|contact\s+support|if\s+(?:the\s+)?issue\s+persists?)",
    re.I,
)

# ── Step dict builder ─────────────────────────────────────────────────────────


def _build_step(n: int, instruction: str) -> dict:
    return {"step_number": n, "instruction": instruction.strip(), "details": ""}


# ─────────────────────────────────────────────────────────────────────────────
# Public types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CandidatePayload:
    """Structured payload for one extracted KB article candidate."""

    candidate_index: int
    raw_segment_text: str

    title: str | None = None
    summary: str | None = None
    category: str | None = None
    subcategory: str | None = None
    product_or_system: str | None = None
    platform: str | None = None
    symptoms: list[str] = field(default_factory=list)
    troubleshooting_steps: list[dict] = field(default_factory=list)
    resolution_steps: list[dict] = field(default_factory=list)
    escalation_criteria: str | None = None
    tags: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    confidence: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────


def parse_document(raw_text: str) -> list[CandidatePayload]:
    """Parse *raw_text* into a list of ``CandidatePayload`` objects.

    Each payload represents one topic segment — roughly corresponding to one
    KB article.  Returns an empty list if the text is blank.
    """
    if not raw_text.strip():
        return []

    segments = _segment_into_topics(raw_text)
    candidates: list[CandidatePayload] = []
    for idx, segment in enumerate(segments):
        payload = _extract_candidate(idx, segment)
        candidates.append(payload)
    return candidates


# ─────────────────────────────────────────────────────────────────────────────
# Topic segmentation
# ─────────────────────────────────────────────────────────────────────────────


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    # Section labels (Troubleshooting, Resolution, Symptoms, etc.) look like
    # headings but are NOT topic boundaries — they divide subsections within
    # the same topic. Exclude them so segmentation doesn't split mid-article.
    if _TROUBLESHOOT_SECTION.match(stripped):
        return False
    if _RESOLUTION_SECTION.match(stripped):
        return False
    if _SYMPTOM_SECTION.match(stripped):
        return False
    if _ESCALATION_SECTION.match(stripped):
        return False
    return any(p.match(stripped) for p in _HEADING_PATTERNS)


def _is_topic_heading(line: str) -> bool:
    """Check whether *line* is a **topic-level** heading (document segmentation).

    Unlike ``_is_heading`` this purposefully excludes numbered / bulleted step
    lines (``1. Open Outlook``, ``- Click File``) which are steps *within* a
    topic, not boundaries between topics.
    """
    stripped = line.strip()
    if not stripped:
        return False
    # Step-lead lines are intra-topic instructions, not topic boundaries.
    if _STEP_LEAD.match(stripped):
        return False
    return _is_heading(stripped)


def _segment_into_topics(text: str) -> list[str]:
    """Split *text* into topic segments.

    Strategy:
    - Split on lines that look like **topic** headings (not numbered steps).
    - Merge tiny segments (< 30 chars) into the previous one.
    - If no headings are found, treat the whole document as one segment.
    """
    lines = text.splitlines()
    segments: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        if _is_topic_heading(line) and current:
            segments.append(current)
            current = [line]
        else:
            current.append(line)

    if current:
        segments.append(current)

    # Merge tiny segments
    merged: list[str] = []
    for seg_lines in segments:
        seg = "\n".join(seg_lines).strip()
        if not seg:
            continue
        if merged and len(seg) < 30:
            merged[-1] = merged[-1] + "\n" + seg
        else:
            merged.append(seg)

    return merged if merged else [text.strip()]


# ─────────────────────────────────────────────────────────────────────────────
# Per-segment field extraction
# ─────────────────────────────────────────────────────────────────────────────


def _extract_candidate(idx: int, segment: str) -> CandidatePayload:
    """Extract all structured fields from a single text segment."""
    lines = [ln.strip() for ln in segment.splitlines() if ln.strip()]

    title = _extract_title(lines)
    symptoms = _extract_symptoms(lines)
    troubleshooting, resolution = _extract_steps(lines)
    escalation = _extract_escalation(lines)
    category, subcategory = _classify_category(segment)
    product = _extract_product(segment)
    tags, keywords = _extract_tags_keywords(segment, category, product)
    summary = _build_summary(lines, title, symptoms)
    confidence = _score_confidence(title, symptoms, troubleshooting, resolution)

    return CandidatePayload(
        candidate_index=idx,
        raw_segment_text=segment,
        title=title,
        summary=summary,
        category=category,
        subcategory=subcategory,
        product_or_system=product,
        symptoms=symptoms,
        troubleshooting_steps=troubleshooting,
        resolution_steps=resolution,
        escalation_criteria=escalation,
        tags=tags,
        keywords=keywords,
        confidence=confidence,
    )


def _extract_title(lines: list[str]) -> str | None:
    """Return the most likely title from the segment's first heading line."""
    for line in lines[:5]:
        if _is_heading(line):
            # Strip markdown hashes and numbering prefixes
            clean = re.sub(r"^#+\s+", "", line)
            clean = re.sub(r"^\d+[\.\)]\s+", "", clean)
            clean = re.sub(r"^(?:Issue|Problem|Topic|Title):\s*", "", clean, flags=re.I)
            if len(clean) >= 5:
                return clean.strip()
    # Fallback: use first non-empty line if short enough to be a title
    if lines and len(lines[0]) <= 120:
        return lines[0]
    return None


def _extract_symptoms(lines: list[str]) -> list[str]:
    """Collect lines that look like symptom descriptions."""
    symptoms: list[str] = []
    in_symptom_section = False

    for line in lines:
        if _SYMPTOM_SECTION.match(line):
            in_symptom_section = True
            continue
        if in_symptom_section:
            if _is_heading(line):
                in_symptom_section = False
                continue
            if line.startswith(("-", "•", "*")) or re.match(r"^\d+[\.\)]", line):
                symptoms.append(re.sub(r"^[-•*\d\.\)]\s*", "", line).strip())
        elif _SYMPTOM_LEAD.match(line):
            cleaned = re.sub(r"^[-•*]\s+", "", line)
            cleaned = re.sub(
                r"^(?:symptoms?|when|users?|issue|problem):\s*", "", cleaned, flags=re.I
            )
            if cleaned and len(cleaned) > 10:
                symptoms.append(cleaned)

    return symptoms[:10]  # Cap at 10 symptoms


def _extract_steps(lines: list[str]) -> tuple[list[dict], list[dict]]:
    """Extract troubleshooting and resolution steps."""
    troubleshooting: list[dict] = []
    resolution: list[dict] = []
    mode: str | None = None  # "troubleshoot" | "resolution"

    for line in lines:
        if _TROUBLESHOOT_SECTION.match(line):
            mode = "troubleshoot"
            continue
        if _RESOLUTION_SECTION.match(line):
            mode = "resolution"
            continue
        # A true topic heading (but NOT a numbered step) ends the current
        # step section. Without the _STEP_LEAD guard, "1. Open Outlook"
        # would incorrectly terminate the section because it matches the
        # numbered-heading pattern in _is_heading.
        if _is_heading(line) and mode and not _STEP_LEAD.match(line):
            mode = None
            continue

        if mode and _STEP_LEAD.match(line):
            instruction = re.sub(
                r"^(?:\d+[\.\)]|[-•*]|step\s+\d+[:\.\)]*)\s*", "", line, flags=re.I
            ).strip()
            if instruction:
                target = troubleshooting if mode == "troubleshoot" else resolution
                target.append(_build_step(len(target) + 1, instruction))

    return troubleshooting[:20], resolution[:20]


def _extract_escalation(lines: list[str]) -> str | None:
    """Find an escalation / contact note."""
    for i, line in enumerate(lines):
        if _ESCALATION_SECTION.match(line):
            # Collect this line + next 2 lines as the escalation text
            chunk = " ".join(lines[i : i + 3])
            return chunk[:500]
    return None


def _classify_category(text: str) -> tuple[str | None, str | None]:
    """Return (category, subcategory) based on keyword matching."""
    for pattern, (cat, sub) in _CATEGORY_KEYWORDS:
        if pattern.search(text):
            return cat, sub
    return None, None


def _extract_product(text: str) -> str | None:
    """Return the first recognised product/system name found in *text*."""
    match = _PRODUCT_RE.search(text)
    if match:
        return match.group(1)
    return None


def _extract_tags_keywords(
    text: str, category: str | None, product: str | None
) -> tuple[list[str], list[str]]:
    """Generate lightweight tags and keyword lists from context."""
    tags: list[str] = []
    if category:
        tags.append(category.split("/")[0])
    if product:
        tags.append(product.lower())

    # Pull capitalised proper-noun tokens as keywords
    words = re.findall(r"\b[A-Z][a-z]{2,}\w*\b", text)
    # Deduplicate, limit
    seen: set[str] = set()
    keywords: list[str] = []
    for w in words:
        if w.lower() not in seen and w.lower() not in {t.lower() for t in tags}:
            seen.add(w.lower())
            keywords.append(w)
        if len(keywords) >= 15:
            break

    return tags, keywords


def _build_summary(lines: list[str], title: str | None, symptoms: list[str]) -> str | None:
    """Produce a short plain-text summary."""
    non_heading = [ln for ln in lines if not _is_heading(ln)]
    # Take first 2 non-heading lines that aren't in symptom lists
    body_lines = [ln for ln in non_heading if not _SYMPTOM_LEAD.match(ln)][:2]
    if body_lines:
        summary = " ".join(body_lines)
        return summary[:800]
    if symptoms:
        return "Issues: " + "; ".join(symptoms[:3])
    if title:
        return f"Troubleshooting guide for: {title}"
    return None


def _score_confidence(
    title: str | None,
    symptoms: list[str],
    troubleshooting: list[dict],
    resolution: list[dict],
) -> float:
    """Simple rule-based confidence score (0.0 – 1.0)."""
    score = 0.0
    if title:
        score += 0.3
    if symptoms:
        score += min(len(symptoms) * 0.05, 0.2)
    if troubleshooting:
        score += min(len(troubleshooting) * 0.04, 0.2)
    if resolution:
        score += min(len(resolution) * 0.05, 0.2)
    # Cap at 0.9 — full confidence reserved for LLM-enriched candidates
    return min(round(score, 2), 0.9)
