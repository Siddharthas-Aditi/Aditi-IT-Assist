"""Pydantic v2 schemas for the document ingestion pipeline.

Covers:
- IngestionJob lifecycle (create → summary → detail)
- IngestionCandidate lifecycle (summary → detail → edit → save)
- Bulk operations
- Pipeline status responses
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enums (strings, mirror ORM enums) ─────────────────────────────────────────

PARSE_STATUSES = ("pending", "extracting", "parsing", "completed", "failed")
EXTRACTION_STATUSES = ("pending", "completed", "failed")
REVIEW_STATUSES = ("pending", "approved", "rejected", "saved")
ALLOWED_EXTENSIONS = ("docx", "pdf", "pptx", "txt", "md")


# ── Step helper ────────────────────────────────────────────────────────────────

class ExtractionStep(BaseModel):
    """One structured step in troubleshooting or resolution sections."""

    step_number: int
    instruction: str
    details: str = ""


# ── Validation warning ─────────────────────────────────────────────────────────

class IngestionWarning(BaseModel):
    """A validation issue attached to a candidate."""

    code: str
    message: str
    severity: str = Field(default="warning", pattern="^(error|warning|info)$")


# ─────────────────────────────────────────────────────────────────────────────
# IngestionJob schemas
# ─────────────────────────────────────────────────────────────────────────────

class IngestionJobCreate(BaseModel):
    """Internal schema populated after the upload handler saves the file."""

    source_filename: str
    source_type: str
    source_size: int | None = None
    uploaded_by: uuid.UUID
    parser_version: str | None = None

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        if v.lower() not in ALLOWED_EXTENSIONS:
            msg = f"Unsupported source type '{v}'. Allowed: {ALLOWED_EXTENSIONS}"
            raise ValueError(msg)
        return v.lower()


class IngestionJobSummary(BaseModel):
    """Lightweight projection used in list views."""

    id: uuid.UUID
    source_filename: str
    source_type: str
    source_size: int | None
    parse_status: str
    extraction_status: str
    candidate_count: int
    uploaded_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IngestionJobDetail(IngestionJobSummary):
    """Full job detail including pipeline diagnostics."""

    processing_summary: dict[str, Any] | None = None
    parser_version: str | None = None
    error_details: str | None = None
    raw_text_ref: str | None = None

    model_config = {"from_attributes": True}


class IngestionJobUpdate(BaseModel):
    """Fields the pipeline may update during processing."""

    parse_status: str | None = None
    extraction_status: str | None = None
    candidate_count: int | None = None
    processing_summary: dict[str, Any] | None = None
    raw_text_ref: str | None = None
    parser_version: str | None = None
    error_details: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# IngestionCandidate schemas
# ─────────────────────────────────────────────────────────────────────────────

class IngestionCandidateSummary(BaseModel):
    """Card-level view for the candidate list page."""

    id: uuid.UUID
    ingestion_job_id: uuid.UUID
    candidate_index: int
    extracted_title: str | None
    extracted_category: str | None
    extracted_subcategory: str | None
    extracted_confidence: float | None
    review_status: str
    mapped_article_id: uuid.UUID | None
    warning_count: int = Field(
        default=0,
        description="Computed from len(validation_warnings)",
    )
    created_at: datetime

    # ── Adaptive extraction metadata (v2 pipeline) ─────────────────────────
    confidence_level: str | None = Field(
        default=None,
        description="HIGH / MEDIUM / LOW / VERY_LOW — from normalized_payload_json",
    )
    review_required: bool = Field(
        default=True,
        description="Whether human review is required before saving",
    )

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _populate_from_payload(cls, data: Any) -> Any:
        """Extract confidence_level and review_required from normalized_payload_json."""
        if not isinstance(data, dict):
            # ORM object — let from_attributes handle it; fields default to None/True
            return data
        payload = data.get("normalized_payload_json") or {}
        if isinstance(payload, dict):
            if "confidence_level" not in data or data.get("confidence_level") is None:
                data["confidence_level"] = payload.get("confidence_level")
            if "review_required" not in data:
                data["review_required"] = payload.get("review_required", True)
        return data


class IngestionCandidateDetail(BaseModel):
    """Full candidate detail for the editor page."""

    id: uuid.UUID
    ingestion_job_id: uuid.UUID
    candidate_index: int

    # Extracted content
    extracted_title: str | None = None
    extracted_summary: str | None = None
    extracted_category: str | None = None
    extracted_subcategory: str | None = None
    extracted_product_or_system: str | None = None
    extracted_platform: str | None = None
    extracted_symptoms: list[str] | None = None
    extracted_troubleshooting_steps: list[ExtractionStep] | None = None
    extracted_resolution_steps: list[ExtractionStep] | None = None
    extracted_escalation_criteria: str | None = None
    extracted_tags: list[str] | None = None
    extracted_keywords: list[str] | None = None
    extracted_owner_group: str | None = None
    extracted_confidence: float | None = None
    validation_warnings: list[IngestionWarning] | None = None

    # Review state
    review_status: str
    mapped_article_id: uuid.UUID | None = None

    # Source
    raw_segment_text: str | None = None
    normalized_payload_json: dict[str, Any] | None = None

    # ── Adaptive extraction metadata (v2 pipeline) ─────────────────────────
    schema_version: str | None = Field(
        default=None, description="Extraction schema version (e.g. '2.0.0')"
    )
    parser_profile: str | None = Field(
        default=None, description="Name of the parser profile used"
    )
    parser_version: str | None = Field(
        default=None, description="Pipeline version that produced this candidate"
    )
    confidence_level: str | None = Field(
        default=None, description="HIGH / MEDIUM / LOW / VERY_LOW"
    )
    review_required: bool = Field(
        default=True, description="Whether human review is required before saving"
    )
    field_confidences: dict[str, float] | None = Field(
        default=None, description="Per-field extraction confidence scores (0–1)"
    )
    parser_warnings: list[str] | None = Field(
        default=None, description="Human-readable extraction quality warnings"
    )

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _populate_from_payload(cls, data: Any) -> Any:
        """Unpack normalized_payload_json into top-level convenience fields."""
        if not isinstance(data, dict):
            return data
        payload = data.get("normalized_payload_json") or {}
        if not isinstance(payload, dict):
            return data
        for key in ("schema_version", "parser_profile", "parser_version",
                    "confidence_level", "review_required",
                    "field_confidences", "parser_warnings"):
            if key not in data or data.get(key) is None:
                data[key] = payload.get(key)
        return data


class CandidateUpdatePayload(BaseModel):
    """Fields an admin may edit during review."""

    extracted_title: str | None = None
    extracted_summary: str | None = None
    extracted_category: str | None = None
    extracted_subcategory: str | None = None
    extracted_product_or_system: str | None = None
    extracted_platform: str | None = None
    extracted_symptoms: list[str] | None = None
    extracted_troubleshooting_steps: list[ExtractionStep] | None = None
    extracted_resolution_steps: list[ExtractionStep] | None = None
    extracted_escalation_criteria: str | None = None
    extracted_tags: list[str] | None = None
    extracted_keywords: list[str] | None = None
    extracted_owner_group: str | None = None


class SaveCandidateRequest(BaseModel):
    """Optional overrides when promoting a candidate to a draft article."""

    ownership_group_id: uuid.UUID | None = None
    author_override: uuid.UUID | None = None


class SaveCandidateResponse(BaseModel):
    """Returned after a candidate is saved as a draft knowledge article."""

    candidate_id: uuid.UUID
    article_id: uuid.UUID
    article_slug: str | None = None
    message: str = "Candidate saved as draft knowledge article."


class RejectCandidateRequest(BaseModel):
    """Optional reason when an admin rejects a candidate."""

    reason: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Bulk operations
# ─────────────────────────────────────────────────────────────────────────────

class BulkSaveRequest(BaseModel):
    """Save multiple approved candidates from a single job."""

    candidate_ids: list[uuid.UUID] = Field(min_length=1)
    ownership_group_id: uuid.UUID | None = None


class BulkSaveResult(BaseModel):
    """Per-candidate outcome inside a bulk save response."""

    candidate_id: uuid.UUID
    success: bool
    article_id: uuid.UUID | None = None
    error: str | None = None


class BulkSaveResponse(BaseModel):
    """Summary of a bulk-save operation."""

    saved: int
    failed: int
    results: list[BulkSaveResult]


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline / upload responses
# ─────────────────────────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    """Immediate response after a file is accepted for processing."""

    job_id: uuid.UUID
    source_filename: str
    source_type: str
    parse_status: str
    message: str = "Document accepted. Processing started in background."


class PipelineStatusResponse(BaseModel):
    """Polling response — mirrors IngestionJobDetail plus candidate counts."""

    job: IngestionJobDetail
    candidates_pending: int = 0
    candidates_approved: int = 0
    candidates_rejected: int = 0
    candidates_saved: int = 0


class DuplicateCandidateMatch(BaseModel):
    """An existing knowledge article that is similar to a candidate."""

    article_id: uuid.UUID
    title: str
    category: str | None = None
    similarity_score: float = Field(ge=0.0, le=1.0)
    match_reason: str
