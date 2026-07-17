"""Document ingestion models.

Tracks the lifecycle of admin-uploaded source documents and the structured
knowledge article candidates extracted from them.

- ``IngestionJob``       — one uploaded document → one processing job
- ``IngestionCandidate`` — one extracted topic segment → one candidate article
"""

from __future__ import annotations

import uuid  # noqa: TC003
from enum import StrEnum

from sqlalchemy import (
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ParseStatus(StrEnum):
    """Overall job processing status."""

    PENDING = "pending"
    EXTRACTING = "extracting"
    PARSING = "parsing"
    COMPLETED = "completed"
    FAILED = "failed"


class ExtractionStatus(StrEnum):
    """Text extraction sub-status."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class CandidateReviewStatus(StrEnum):
    """Human review decision on a candidate."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SAVED = "saved"  # already promoted to a draft KnowledgeArticle


class IngestionJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Represents a single document upload and the pipeline that processes it."""

    __tablename__ = "ingestion_jobs"

    # ── Source file ─────────────────────────────────────────────────────────
    source_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="docx | pdf | pptx | txt | md"
    )
    source_size: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="File size in bytes"
    )

    # ── Uploader ─────────────────────────────────────────────────────────────
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Pipeline status ───────────────────────────────────────────────────────
    parse_status: Mapped[str] = mapped_column(
        Enum(
            ParseStatus,
            name="ingestion_parse_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=ParseStatus.PENDING.value,
        server_default=ParseStatus.PENDING.value,
    )
    extraction_status: Mapped[str] = mapped_column(
        Enum(
            ExtractionStatus,
            name="ingestion_extraction_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=ExtractionStatus.PENDING.value,
        server_default=ExtractionStatus.PENDING.value,
    )

    # ── Results ───────────────────────────────────────────────────────────────
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processing_summary: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Per-stage timing and counts"
    )

    # ── Storage ───────────────────────────────────────────────────────────────
    raw_text_ref: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Filesystem path to extracted raw text"
    )
    parser_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_details: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Traceback or error message on failure"
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    candidates: Mapped[list[IngestionCandidate]] = relationship(
        "IngestionCandidate",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<IngestionJob id={self.id} file={self.source_filename!r} status={self.parse_status}>"
        )


class IngestionCandidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single extracted topic segment — a candidate knowledge article."""

    __tablename__ = "ingestion_candidates"

    # ── Parent job ────────────────────────────────────────────────────────────
    ingestion_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_index: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Zero-based position within the job"
    )

    # ── Extracted fields ──────────────────────────────────────────────────────
    extracted_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    extracted_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    extracted_subcategory: Mapped[str | None] = mapped_column(String(128), nullable=True)
    extracted_product_or_system: Mapped[str | None] = mapped_column(String(256), nullable=True)
    extracted_platform: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # ── Structured content (stored as JSON arrays) ────────────────────────────
    extracted_symptoms: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, comment="list[str]"
    )
    extracted_troubleshooting_steps: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, comment="list[{step_number, instruction, details}]"
    )
    extracted_resolution_steps: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, comment="list[{step_number, instruction, details}]"
    )
    extracted_escalation_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Taxonomy ──────────────────────────────────────────────────────────────
    extracted_tags: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="list[str]")
    extracted_keywords: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, comment="list[str]"
    )
    extracted_owner_group: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # ── Quality ───────────────────────────────────────────────────────────────
    extracted_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="0.0 – 1.0 pipeline confidence"
    )
    validation_warnings: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, comment="list[{code, message, severity}]"
    )

    # ── Review ────────────────────────────────────────────────────────────────
    review_status: Mapped[str] = mapped_column(
        Enum(
            CandidateReviewStatus,
            name="ingestion_candidate_review_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=CandidateReviewStatus.PENDING.value,
        server_default=CandidateReviewStatus.PENDING.value,
    )
    mapped_article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_articles.id", ondelete="SET NULL"),
        nullable=True,
        comment="Set when candidate is saved as a draft article",
    )

    # ── Raw source ────────────────────────────────────────────────────────────
    raw_segment_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Original text segment from the source document"
    )
    normalized_payload_json: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Full normalised candidate payload pre-mapping"
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    job: Mapped[IngestionJob] = relationship("IngestionJob", back_populates="candidates")

    def __repr__(self) -> str:
        return (
            f"<IngestionCandidate id={self.id} job={self.ingestion_job_id} "
            f"idx={self.candidate_index} status={self.review_status}>"
        )
