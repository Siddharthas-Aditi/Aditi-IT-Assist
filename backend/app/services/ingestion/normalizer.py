"""Layer B — Structure-aware text normalizer.

Converts raw document text into a sequence of ``NormalizedLine`` objects.
Each line receives a structural type token (HEADING, BULLET, NUMBERED …)
and indent level WITHOUT making semantic decisions (that is the segmenter's job).

Adaptive design: handles all bullet/number/heading variants regardless of
author style — 15+ bullet chars unified, 8+ number formats detected,
heading detection by 5 independent signals.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

# ── Line types ────────────────────────────────────────────────────────────────


class LineType(StrEnum):
    BLANK = "blank"
    HEADING = "heading"  # High-confidence heading
    HEADING_WEAK = "heading_weak"  # Possible heading — needs corroboration
    BULLET = "bullet"  # Bulleted list item
    NUMBERED = "numbered"  # Numbered list item
    LABEL = "label"  # "SomeLabel: content" format
    CONTINUATION = "continuation"  # Normal paragraph / sentence
    TABLE_ROW = "table_row"  # Pipe-separated table row
    SEPARATOR = "separator"  # Decorative separator line (---, ===)


# ── Normalized line ────────────────────────────────────────────────────────────


@dataclass
class NormalizedLine:
    raw: str  # Original line as-is
    text: str  # Cleaned text with marker stripped
    marker: str | None  # Original bullet/number token
    line_type: LineType
    indent: int  # 0-based indent level (0 = left margin)
    number: int | None = None  # Parsed number for NUMBERED lines
    label: str | None = None  # Label name for LABEL lines ("Resolution")


# ── Normalized document ────────────────────────────────────────────────────────


@dataclass
class NormalizedDocument:
    lines: list[NormalizedLine]
    raw_text: str
    heading_count: int = 0
    bullet_count: int = 0
    numbered_count: int = 0
    label_count: int = 0


# ── Character sets and patterns ────────────────────────────────────────────────

# All bullet variants → unified to •
_BULLET_CHARS = frozenset("•●○▪▸◦→⇒►▶-–—*+")

# Regex patterns for different number formats
_NUMBER_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(\d{1,2})[\.\)]\s+(.+)$"),  # 1. text  or  1) text
    re.compile(r"^\((\d{1,2})\)\s+(.+)$"),  # (1) text
    re.compile(r"^[Ss]tep\s+(\d{1,2})[:\.\)]\s+(.+)$", re.I),  # Step 1: text
    re.compile(r"^(\d{1,2})[:\-–]\s+(.+)$"),  # 1: text  or  1- text
]

# Heading signals (each independently contributes evidence)
_HEADING_MARKDOWN = re.compile(r"^#{1,4}\s+(.+)$")
_HEADING_UNDERLINE_NEXT: str = "underline"  # handled during post-processing

# All-caps: ≥ 4 uppercase alpha chars, allows spaces, slashes, dashes
_HEADING_ALL_CAPS = re.compile(r"^[A-Z][A-Z\s\-/&()]{3,}[A-Z]$")

# Short line ending with colon: likely a section label
_LABEL_LINE = re.compile(r"^([A-Za-z][A-Za-z\s\-/]{1,40}):(.*)$")

# Separator line
_SEPARATOR = re.compile(r"^[\-=*_~]{3,}\s*$")


# ── Public entry point ────────────────────────────────────────────────────────


def normalize_document(raw_text: str) -> NormalizedDocument:
    """Convert *raw_text* into a ``NormalizedDocument`` with typed lines."""
    raw_lines = raw_text.splitlines()
    norm_lines: list[NormalizedLine] = []

    for raw in raw_lines:
        nl = _classify_line(raw)
        norm_lines.append(nl)

    # Post-process: detect underline headings (line followed by ===/ ---)
    norm_lines = _detect_underline_headings(norm_lines)

    doc = NormalizedDocument(
        lines=norm_lines,
        raw_text=raw_text,
        heading_count=sum(
            1 for ln in norm_lines if ln.line_type in (LineType.HEADING, LineType.HEADING_WEAK)
        ),
        bullet_count=sum(1 for ln in norm_lines if ln.line_type == LineType.BULLET),
        numbered_count=sum(1 for ln in norm_lines if ln.line_type == LineType.NUMBERED),
        label_count=sum(1 for ln in norm_lines if ln.line_type == LineType.LABEL),
    )
    return doc


# ── Line classification ────────────────────────────────────────────────────────


def _classify_line(raw: str) -> NormalizedLine:
    """Assign a ``LineType`` and extract structural metadata from one raw line."""
    # Blank / whitespace-only
    if not raw.strip():
        return NormalizedLine(raw=raw, text="", marker=None, line_type=LineType.BLANK, indent=0)

    indent = _compute_indent(raw)
    stripped = raw.strip()
    clean = _normalize_unicode(stripped)

    # Separator (--- or ===)
    if _SEPARATOR.match(clean):
        return NormalizedLine(
            raw=raw, text=clean, marker=None, line_type=LineType.SEPARATOR, indent=0
        )

    # Table row (contains | and multiple cells)
    if clean.count("|") >= 2:
        return NormalizedLine(
            raw=raw, text=clean, marker=None, line_type=LineType.TABLE_ROW, indent=indent
        )

    # Markdown heading
    m = _HEADING_MARKDOWN.match(clean)
    if m:
        hash_match = re.match(r"^(#+)", clean)
        marker = hash_match.group(1) if hash_match else "#"
        return NormalizedLine(
            raw=raw, text=m.group(1).strip(), marker=marker, line_type=LineType.HEADING, indent=0
        )

    # Numbered list item
    for pat in _NUMBER_PATTERNS:
        m = pat.match(clean)
        if m:
            num = int(m.group(1))
            text = m.group(2).strip()
            return NormalizedLine(
                raw=raw,
                text=text,
                marker=m.group(1),
                line_type=LineType.NUMBERED,
                indent=indent,
                number=num,
            )

    # Bullet list item
    if clean and clean[0] in _BULLET_CHARS:
        text = clean[1:].lstrip()
        return NormalizedLine(
            raw=raw, text=text, marker=clean[0], line_type=LineType.BULLET, indent=indent
        )

    # Label line: "SomeLabel: optional text"
    m = _LABEL_LINE.match(clean)
    if m:
        label_name = m.group(1).strip()
        content = m.group(2).strip()
        ltype = LineType.LABEL if not content else LineType.LABEL
        return NormalizedLine(
            raw=raw,
            text=content or clean,
            marker=None,
            line_type=ltype,
            indent=indent,
            label=label_name,
        )

    # All-caps heading heuristic
    if _HEADING_ALL_CAPS.match(clean) and len(clean) >= 4:
        return NormalizedLine(
            raw=raw, text=clean, marker=None, line_type=LineType.HEADING_WEAK, indent=0
        )

    # Short, non-sentence line (possible topic title without markup)
    if (
        len(clean) <= 80
        and not clean.endswith((".", "!", "?"))
        and not clean[0].islower()
        and re.match(r"^[A-Z]", clean)
        and len(clean.split()) <= 10
    ):
        return NormalizedLine(
            raw=raw, text=clean, marker=None, line_type=LineType.HEADING_WEAK, indent=indent
        )

    return NormalizedLine(
        raw=raw, text=clean, marker=None, line_type=LineType.CONTINUATION, indent=indent
    )


def _detect_underline_headings(lines: list[NormalizedLine]) -> list[NormalizedLine]:
    """Promote CONTINUATION lines followed by underline separators to HEADING."""
    result = list(lines)
    for i in range(len(result) - 1):
        curr = result[i]
        nxt = result[i + 1]
        if (
            curr.line_type == LineType.CONTINUATION
            and nxt.line_type == LineType.SEPARATOR
            and len(curr.text) <= 80
        ):
            result[i] = NormalizedLine(
                raw=curr.raw, text=curr.text, marker=None, line_type=LineType.HEADING, indent=0
            )
    return result


# ── Helpers ────────────────────────────────────────────────────────────────────


def _normalize_unicode(text: str) -> str:
    """NFKD normalize, unify smart quotes/dashes/arrows."""
    text = unicodedata.normalize("NFKC", text)
    # Smart quotes → straight
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    # Em/en dash → double hyphen
    text = text.replace("\u2013", "--").replace("\u2014", "--")
    # Right arrow variants → ->
    text = text.replace("\u2192", "->").replace("\u21d2", "=>")
    return text.strip()


def _compute_indent(line: str) -> int:
    """Return 0-based indent level (each 2-4 spaces or 1 tab = 1 level)."""
    spaces = len(line) - len(line.lstrip(" "))
    tabs = len(line) - len(line.lstrip("\t"))
    return tabs + spaces // 2
