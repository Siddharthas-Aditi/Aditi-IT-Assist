"""Layer C — Semantic document segmenter.

Splits a NormalizedDocument into topic segments (DocumentSegment objects).
Each segment roughly corresponds to one IT support topic / KB article.

ADAPTIVE DESIGN:
- Does NOT require headings to be present
- Accumulates evidence from multiple weak signals (heading change, blank lines,
  semantic vocabulary shift, label transitions) before declaring a boundary
- Handles mixed formats, headingless docs, and multi-topic files
- Assigns SemanticSignal flags that the extractor uses to know what to look for
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.services.ingestion.normalizer import LineType, NormalizedDocument, NormalizedLine
from app.services.ingestion.schema import SemanticSignal

if TYPE_CHECKING:
    from app.services.ingestion.profiles.base import ParserProfile

# ── Document segment ──────────────────────────────────────────────────────────


@dataclass
class DocumentSegment:
    """One extracted topic block from a document."""

    segment_index: int
    heading: str | None  # Best-guess heading for this topic
    raw_text: str  # Full segment text (original)
    lines: list[NormalizedLine]  # Normalized lines
    signals: SemanticSignal  # Detected semantic signals
    boundary_confidence: float  # How confident is the leading boundary? 0-1
    topic_score: float  # Is this a complete IT topic? 0-1
    section_map: dict[str, list[str]]  # label → list of text lines in that section


# ── Semantic vocabulary signals ────────────────────────────────────────────────

_PROBLEM_WORDS = re.compile(
    r"\b(?:not\s+working|fails?|failing|error|crash|broken|unable|cannot|can't|"
    r"won't|doesn't|missing|lost|stuck|freeze|froze|slow|disconnected|"
    r"access\s+denied|permission\s+denied|issue|problem|symptom)\b",
    re.I,
)
_RESOLUTION_WORDS = re.compile(
    r"\b(?:resolution|solution|fix|resolve|solved|corrective|workaround|"
    r"reinstall|restart|reset|reconfigure|re-add|uninstall|update|upgrade|"
    r"restore|rollback|reprovision)\b",
    re.I,
)
_STEP_WORDS = re.compile(
    r"\b(?:click|open|go\s+to|navigate|select|type|enter|run|execute|"
    r"check|verify|confirm|ensure|launch|close|disable|enable)\b",
    re.I,
)
_ESCALATION_WORDS = re.compile(
    r"\b(?:escalate|escalation|contact\s+it|contact\s+support|helpdesk|"
    r"service\s+desk|if\s+the\s+issue\s+persists|if\s+unresolved|further\s+assistance)\b",
    re.I,
)
_PRODUCT_WORDS = re.compile(
    r"\b(?:outlook|zoom|teams|intune|sharepoint|onedrive|vpn|azure|office|"
    r"windows|macos|chrome|edge|firefox|slack|excel|word|powerpoint)\b",
    re.I,
)


# ── Public entry point ────────────────────────────────────────────────────────


def segment_document(doc: NormalizedDocument, profile: ParserProfile) -> list[DocumentSegment]:
    """Split *doc* into topic segments using semantic + structural signals.

    Strategy:
    1. Walk lines accumulating boundary evidence.
    2. A boundary is confirmed when evidence ≥ 0.5.
    3. Tiny segments (< 3 non-blank lines) are merged into the previous.
    4. Semantic signals are computed for each segment.
    5. Each segment gets a topic score.
    """
    if not doc.lines:
        return []

    # ── Step 1: find boundary positions ──────────────────────────────────────
    groups: list[list[NormalizedLine]] = _split_into_groups(doc.lines, profile)

    # ── Step 2: merge tiny groups ─────────────────────────────────────────────
    groups = _merge_tiny_groups(groups)

    # ── Step 3: build segments ────────────────────────────────────────────────
    segments: list[DocumentSegment] = []
    for idx, group_lines in enumerate(groups):
        seg = _build_segment(idx, group_lines, profile)
        segments.append(seg)

    return segments


# ── Boundary detection ────────────────────────────────────────────────────────


def _split_into_groups(
    lines: list[NormalizedLine], profile: ParserProfile
) -> list[list[NormalizedLine]]:
    """Split lines at topic boundaries. Returns list of line groups."""
    groups: list[list[NormalizedLine]] = []
    current: list[NormalizedLine] = []

    for i, line in enumerate(lines):
        evidence = _boundary_evidence(lines, i, profile)
        if evidence >= 0.5 and current:
            groups.append(current)
            current = [line]
        else:
            current.append(line)

    if current:
        groups.append(current)
    return groups


def _boundary_evidence(lines: list[NormalizedLine], idx: int, profile: ParserProfile) -> float:
    """Return 0–1 evidence that a new topic starts at lines[idx]."""
    line = lines[idx]
    evidence = 0.0

    # Strong signals
    if line.line_type == LineType.HEADING:
        evidence += 0.9
    if line.line_type == LineType.SEPARATOR:
        evidence += 0.85
    # Check profile topic separators
    for pat in profile.topic_separators:
        if pat.match(line.raw.strip()):
            evidence += 0.9

    # Medium signals
    if line.line_type == LineType.HEADING_WEAK and idx > 0:
        # Only count as boundary if preceded by blank line
        prev_non_blank = next(
            (lines[j] for j in range(idx - 1, -1, -1) if lines[j].line_type != LineType.BLANK), None
        )
        if prev_non_blank and prev_non_blank.line_type in (
            LineType.BULLET,
            LineType.NUMBERED,
            LineType.CONTINUATION,
        ):
            evidence += 0.45

    # Weak signals: consecutive blank lines
    if line.line_type == LineType.BLANK and idx > 0:
        blank_run = 0
        for j in range(idx, -1, -1):
            if lines[j].line_type == LineType.BLANK:
                blank_run += 1
            else:
                break
        if blank_run >= 2:
            evidence += 0.25

    # Topic separator profile patterns on the PREVIOUS line
    if idx > 0 and lines[idx - 1].line_type == LineType.SEPARATOR:
        evidence += 0.7

    return min(evidence, 1.0)


def _merge_tiny_groups(
    groups: list[list[NormalizedLine]],
    min_content_lines: int = 3,
) -> list[list[NormalizedLine]]:
    """Merge groups with fewer than *min_content_lines* content lines into previous."""
    if not groups:
        return groups
    result: list[list[NormalizedLine]] = [groups[0]]
    for g in groups[1:]:
        content = [ln for ln in g if ln.line_type not in (LineType.BLANK, LineType.SEPARATOR)]
        if len(content) < min_content_lines and result:
            result[-1].extend(g)
        else:
            result.append(g)
    return result


# ── Segment construction ──────────────────────────────────────────────────────


def _build_segment(
    idx: int, lines: list[NormalizedLine], profile: ParserProfile
) -> DocumentSegment:
    """Build a DocumentSegment from a group of NormalizedLines."""
    raw_text = "\n".join(ln.raw for ln in lines)
    heading = _extract_heading(lines)
    signals = _compute_signals(raw_text, lines, profile)
    section_map = _build_section_map(lines, profile)
    topic_score = _compute_topic_score(signals)
    boundary_confidence = _heading_confidence(lines)

    return DocumentSegment(
        segment_index=idx,
        heading=heading,
        raw_text=raw_text,
        lines=lines,
        signals=signals,
        boundary_confidence=boundary_confidence,
        topic_score=topic_score,
        section_map=section_map,
    )


def _extract_heading(lines: list[NormalizedLine]) -> str | None:
    """Return the best-guess heading for a segment."""
    for line in lines[:6]:
        if line.line_type == LineType.HEADING and line.text:
            return line.text.strip()
    for line in lines[:6]:
        if line.line_type == LineType.HEADING_WEAK and line.text:
            return line.text.strip()
    # Last resort: first meaningful LABEL line — use the full "Label: content" form
    for line in lines[:8]:
        # Only use if the text (content after colon) is meaningful
        if (
            line.line_type == LineType.LABEL
            and line.label
            and line.text
            and len(line.text) >= 5
            and line.text.lower() != line.label.lower()
        ):
            return line.text.strip()
    # First short CONTINUATION line
    for line in lines[:4]:
        if (
            line.line_type == LineType.CONTINUATION
            and 5 <= len(line.text) <= 100
            and re.match(r"^[A-Z]", line.text)
            and not line.text.endswith(".")
        ):
            return line.text.strip()
    return None


def _compute_signals(
    raw_text: str, lines: list[NormalizedLine], profile: ParserProfile
) -> SemanticSignal:
    """Detect which semantic signals are present in the segment."""
    signals = SemanticSignal.NONE

    if _PROBLEM_WORDS.search(raw_text):
        signals |= SemanticSignal.HAS_PROBLEM
    if _RESOLUTION_WORDS.search(raw_text):
        signals |= SemanticSignal.HAS_RESOLUTION
    if _STEP_WORDS.search(raw_text):
        signals |= SemanticSignal.HAS_STEPS
    if _ESCALATION_WORDS.search(raw_text):
        signals |= SemanticSignal.HAS_ESCALATION
    if _PRODUCT_WORDS.search(raw_text):
        signals |= SemanticSignal.HAS_PRODUCT

    # Troubleshooting: profile label match
    has_ts_label = any(
        line.line_type == LineType.LABEL
        and profile.matches_label(line.raw, "troubleshooting_steps")
        for line in lines
    )
    if has_ts_label or (
        signals & SemanticSignal.HAS_STEPS and signals & SemanticSignal.HAS_PROBLEM
    ):
        signals |= SemanticSignal.HAS_TROUBLESHOOTING

    if (signals & SemanticSignal.HAS_PROBLEM) and (signals & SemanticSignal.HAS_RESOLUTION):
        signals |= SemanticSignal.IS_COMPLETE_TOPIC

    return signals


def _build_section_map(lines: list[NormalizedLine], profile: ParserProfile) -> dict[str, list[str]]:
    """Map schema field names → list of text lines found within that section."""
    result: dict[str, list[str]] = {}
    current_section: str | None = None

    for line in lines:
        if line.line_type == LineType.LABEL and line.label:
            # Detect which profile field this label maps to
            for field_name in profile.section_markers:
                if profile.matches_label(f"{line.label}:", field_name):
                    current_section = field_name
                    # If label has inline content, add it
                    if line.text:
                        result.setdefault(current_section, []).append(line.text)
                    break
            else:
                current_section = None
        elif current_section and line.line_type not in (
            LineType.BLANK,
            LineType.SEPARATOR,
            LineType.HEADING,
            LineType.HEADING_WEAK,
        ):
            result.setdefault(current_section, []).append(line.text or line.raw.strip())

    return result


def _compute_topic_score(signals: SemanticSignal) -> float:
    """Score 0–1 representing how complete an IT support topic this segment is."""
    score = 0.0
    if signals & SemanticSignal.HAS_PROBLEM:
        score += 0.25
    if signals & SemanticSignal.HAS_RESOLUTION:
        score += 0.30
    if signals & SemanticSignal.HAS_STEPS:
        score += 0.20
    if signals & SemanticSignal.HAS_ESCALATION:
        score += 0.10
    if signals & SemanticSignal.HAS_PRODUCT:
        score += 0.05
    if signals & SemanticSignal.IS_COMPLETE_TOPIC:
        score += 0.10
    return min(score, 1.0)


def _heading_confidence(lines: list[NormalizedLine]) -> float:
    """Confidence that the segment boundary is correctly placed."""
    for line in lines[:3]:
        if line.line_type == LineType.HEADING:
            return 0.95
        if line.line_type == LineType.SEPARATOR:
            return 0.90
        if line.line_type == LineType.HEADING_WEAK:
            return 0.65
    return 0.40
