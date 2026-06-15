"""Parser profile base types.

A ``ParserProfile`` describes how a family of documents maps to the
extraction schema.  Adding support for a new document family means
adding a new profile — never changing extraction code.

Key idea: section labels and marker patterns vary wildly between authors.
Profiles encode that variability as data, not code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Pattern


# ── Section label mappings ────────────────────────────────────────────────────

# Maps internal schema field → list of label strings that identify it in text.
# Matching is case-insensitive prefix match on a line followed by ":" or end.
SectionMarkers = dict[str, list[str]]


# ── Confidence weights (per field) ────────────────────────────────────────────

@dataclass
class ConfidenceWeights:
    """How much each field contributes to the composite confidence score."""
    title: float = 0.25
    category: float = 0.15
    short_summary: float = 0.05
    symptoms: float = 0.10
    troubleshooting_steps: float = 0.10
    resolution_steps: float = 0.20
    escalation_criteria: float = 0.05
    tags: float = 0.05
    product_or_system: float = 0.05

    def total(self) -> float:
        return (
            self.title + self.category + self.short_summary
            + self.symptoms + self.troubleshooting_steps
            + self.resolution_steps + self.escalation_criteria
            + self.tags + self.product_or_system
        )


# ── Review thresholds ─────────────────────────────────────────────────────────

@dataclass
class ReviewThresholds:
    """Composite confidence thresholds for review routing."""
    high: float = 0.75     # ≥ high → save directly as candidate
    medium: float = 0.50   # ≥ medium → review recommended
    low: float = 0.30      # ≥ low → review required
    # < low → failed extraction; keep job for retry


# ── Detection criteria ────────────────────────────────────────────────────────

@dataclass
class DetectionCriteria:
    """Heuristics used to auto-select this profile for an uploaded document."""
    keyword_signals: list[str] = field(default_factory=list)
    filename_patterns: list[Pattern] = field(default_factory=list)
    min_keyword_matches: int = 1


# ── The parser profile ────────────────────────────────────────────────────────

@dataclass
class ParserProfile:
    """Encapsulates all document-family-specific extraction configuration.

    Parser logic reads from the profile rather than hardcoding label strings.
    Evolving a profile requires NO code changes to the extraction engine.

    Fields:
    - ``name`` — unique profile identifier (used as ``parser_profile`` on candidates)
    - ``version`` — profile data version (increment when markers change)
    - ``section_markers`` — label → section type mapping
    - ``heading_signals`` — extra patterns that signal a heading in this family
    - ``topic_separators`` — patterns that separate distinct topics (e.g. "---")
    - ``confidence_weights`` — per-field weight for composite score
    - ``thresholds`` — review routing thresholds
    - ``detection`` — how to auto-detect this profile
    """
    name: str
    version: str
    description: str = ""
    section_markers: SectionMarkers = field(default_factory=dict)
    heading_signals: list[Pattern] = field(default_factory=list)
    topic_separators: list[Pattern] = field(default_factory=list)
    confidence_weights: ConfidenceWeights = field(default_factory=ConfidenceWeights)
    thresholds: ReviewThresholds = field(default_factory=ReviewThresholds)
    detection: DetectionCriteria = field(default_factory=DetectionCriteria)

    def labels_for(self, field_name: str) -> list[str]:
        """Return section label strings for a schema field, lower-cased."""
        return [s.lower() for s in self.section_markers.get(field_name, [])]

    def matches_label(self, line: str, field_name: str) -> bool:
        """True if *line* starts with a label that maps to *field_name*."""
        clean = line.strip().lower().rstrip(":")
        return any(clean == lbl or clean.startswith(lbl) for lbl in self.labels_for(field_name))
