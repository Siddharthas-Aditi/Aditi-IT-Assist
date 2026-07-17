"""Versioned extraction schema — the stable contract for adaptive document ingestion.

Schema version: 2.0.0

DESIGN PRINCIPLE: "Schema-stable, parser-flexible."
The schema below is the ONLY stable interface between:
  - Any parsing strategy (deterministic, heuristic, LLM)
  - The validator, mapper, confidence scorer, and review UI

Document formats change constantly; this schema evolves explicitly
via SCHEMA_VERSION and never by accident.

Per-field confidence: every extracted field is wrapped in ``FieldExtraction``
carrying value, confidence (0–1), source excerpt (traceability), extraction
method, and field-specific warnings. The review UI surfaces these directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Flag, StrEnum, auto

SCHEMA_VERSION = "2.0.0"
PARSER_VERSION = "2.0.0"


# ── Extraction methods ────────────────────────────────────────────────────────


class ExtractionMethod(StrEnum):
    """How a field value was obtained."""

    DETERMINISTIC = "deterministic"  # rule / regex — highest trust
    HEURISTIC = "heuristic"  # structural inference
    LLM = "llm"  # LLM-assisted
    COMBINED = "combined"  # deterministic + LLM agreed
    NOT_EXTRACTED = "not_extracted"  # absent or skipped


# ── Confidence levels & thresholds ────────────────────────────────────────────


class ConfidenceLevel(StrEnum):
    HIGH = "high"  # ≥ 0.75 — save as candidate with minimal friction
    MEDIUM = "medium"  # ≥ 0.50 — review recommended
    LOW = "low"  # ≥ 0.30 — review required before save
    VERY_LOW = "very_low"  # < 0.30 — keep as failed; allow retry


HIGH_THRESHOLD = 0.75
MEDIUM_THRESHOLD = 0.50
LOW_THRESHOLD = 0.30


def classify_confidence(score: float) -> ConfidenceLevel:
    if score >= HIGH_THRESHOLD:
        return ConfidenceLevel.HIGH
    if score >= MEDIUM_THRESHOLD:
        return ConfidenceLevel.MEDIUM
    if score >= LOW_THRESHOLD:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.VERY_LOW


def review_required_for_score(score: float) -> bool:
    """True when human review is required before this candidate can be saved."""
    return score < MEDIUM_THRESHOLD


# ── Semantic signals (document-level) ─────────────────────────────────────────


class SemanticSignal(Flag):
    """Signals detected within a document segment."""

    NONE = 0
    HAS_PROBLEM = auto()  # contains a problem/symptom description
    HAS_RESOLUTION = auto()  # contains resolution / fix steps
    HAS_TROUBLESHOOTING = auto()  # contains troubleshooting / diagnosis steps
    HAS_ESCALATION = auto()  # contains escalation criteria
    HAS_PRODUCT = auto()  # product / system name detected
    HAS_STEPS = auto()  # numbered or procedural steps detected
    IS_COMPLETE_TOPIC = auto()  # both problem + resolution present


# ── Per-field extraction container ────────────────────────────────────────────


@dataclass
class FieldExtraction:
    """A single extracted field with full provenance.

    Every field in ``ExtractionCandidate`` is wrapped in this so the review
    UI can show confidence per field, not just per candidate.
    """

    value: object = None  # str | list | None
    confidence: float = 0.0  # 0.0 – 1.0
    source_excerpt: str | None = None  # text snippet the value was drawn from
    method: ExtractionMethod = ExtractionMethod.NOT_EXTRACTED
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def absent(cls) -> FieldExtraction:
        return cls(value=None, confidence=0.0, method=ExtractionMethod.NOT_EXTRACTED)

    @classmethod
    def make(
        cls,
        value: object,
        confidence: float,
        *,
        method: ExtractionMethod = ExtractionMethod.HEURISTIC,
        excerpt: str | None = None,
        warnings: list[str] | None = None,
    ) -> FieldExtraction:
        return cls(
            value=value,
            confidence=confidence,
            source_excerpt=excerpt,
            method=method,
            warnings=warnings or [],
        )

    @property
    def is_present(self) -> bool:
        return self.value is not None and self.value != "" and self.value != []


# ── Step container ────────────────────────────────────────────────────────────


@dataclass
class ExtractionStep:
    step_number: int
    instruction: str
    details: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {
            "step_number": self.step_number,
            "instruction": self.instruction,
            "details": self.details,
        }


# ── The stable extraction candidate ───────────────────────────────────────────


@dataclass
class ExtractionCandidate:
    """Full in-memory extraction result for one document segment.

    This is the STABLE CONTRACT produced by any parsing strategy and
    consumed by the validator, confidence scorer, mapper, and review UI.

    Always carries:
    - ``schema_version`` — for forward-compatible processing
    - ``parser_version`` — for reprocessing old jobs with newer parsers
    - ``parser_profile`` — which profile was applied
    - Per-field ``FieldExtraction`` instances with confidence + excerpt
    - Composite ``extraction_confidence`` and ``review_required``
    """

    schema_version: str = SCHEMA_VERSION
    parser_version: str = PARSER_VERSION
    parser_profile: str = "it_support_v1"
    candidate_index: int = 0
    raw_segment_text: str = ""

    # ── Core identity ──────────────────────────────────────────────────────
    title: FieldExtraction = field(default_factory=FieldExtraction.absent)
    short_summary: FieldExtraction = field(default_factory=FieldExtraction.absent)

    # ── Classification ─────────────────────────────────────────────────────
    category: FieldExtraction = field(default_factory=FieldExtraction.absent)
    subcategory: FieldExtraction = field(default_factory=FieldExtraction.absent)
    product_or_system: FieldExtraction = field(default_factory=FieldExtraction.absent)
    platform: FieldExtraction = field(default_factory=FieldExtraction.absent)
    issue_type: FieldExtraction = field(default_factory=FieldExtraction.absent)

    # ── Content ────────────────────────────────────────────────────────────
    symptoms: FieldExtraction = field(default_factory=FieldExtraction.absent)
    probable_causes: FieldExtraction = field(default_factory=FieldExtraction.absent)
    troubleshooting_steps: FieldExtraction = field(default_factory=FieldExtraction.absent)
    resolution_steps: FieldExtraction = field(default_factory=FieldExtraction.absent)
    validation_steps: FieldExtraction = field(default_factory=FieldExtraction.absent)
    escalation_criteria: FieldExtraction = field(default_factory=FieldExtraction.absent)
    escalation_target_team: FieldExtraction = field(default_factory=FieldExtraction.absent)

    # ── Governance ─────────────────────────────────────────────────────────
    tags: FieldExtraction = field(default_factory=FieldExtraction.absent)
    keywords: FieldExtraction = field(default_factory=FieldExtraction.absent)
    semantic_signals: SemanticSignal = SemanticSignal.NONE

    # ── Composite quality ──────────────────────────────────────────────────
    extraction_confidence: float = 0.0
    confidence_level: str = ConfidenceLevel.VERY_LOW.value
    review_required: bool = True
    parser_warnings: list[str] = field(default_factory=list)
    extraction_metadata: dict = field(default_factory=dict)

    def field_value(self, name: str) -> object:
        fe = getattr(self, name, None)
        return fe.value if isinstance(fe, FieldExtraction) else None

    def field_confidence(self, name: str) -> float:
        fe = getattr(self, name, None)
        return fe.confidence if isinstance(fe, FieldExtraction) else 0.0

    def build_metadata(self) -> dict:
        """Build the extraction_metadata dict for JSONB storage."""
        tracked = [
            "title",
            "short_summary",
            "category",
            "subcategory",
            "product_or_system",
            "platform",
            "symptoms",
            "troubleshooting_steps",
            "resolution_steps",
            "escalation_criteria",
            "tags",
        ]
        return {
            fname: {
                "confidence": getattr(self, fname).confidence,
                "method": getattr(self, fname).method.value,
                "warnings": getattr(self, fname).warnings,
                "excerpt": getattr(self, fname).source_excerpt,
            }
            for fname in tracked
            if isinstance(getattr(self, fname, None), FieldExtraction)
        }
