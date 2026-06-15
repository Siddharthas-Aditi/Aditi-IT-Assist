"""Document ingestion endpoints — admin / IT-lead only.

Mounted under ``/knowledge/ingest``.  All endpoints require either
``knowledge:ingest`` (upload + pipeline) or ``knowledge:ingest_review``
(review, edit, save candidates).

Endpoints
---------
POST   /upload                              — upload file, start background pipeline
GET    /jobs                                — list ingestion jobs
GET    /jobs/{job_id}                       — job detail + candidate counts
GET    /jobs/{job_id}/candidates            — list candidates for a job
GET    /jobs/{job_id}/candidates/{c_id}     — candidate detail
PATCH  /jobs/{job_id}/candidates/{c_id}     — update candidate fields
POST   /jobs/{job_id}/candidates/{c_id}/save   — save as draft knowledge article
POST   /jobs/{job_id}/candidates/{c_id}/reject — reject candidate
POST   /jobs/{job_id}/bulk-save            — bulk save approved candidates
POST   /jobs/{job_id}/retry               — re-run pipeline for a failed job
GET    /duplicates                          — duplicate lookup by title
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.permissions import P
from app.models.auth import User
from app.models.ingestion import IngestionJob
from app.repositories.ingestion_repository import IngestionRepository
from app.schemas.ingestion import (
    BulkSaveRequest,
    BulkSaveResponse,
    BulkSaveResult,
    CandidateUpdatePayload,
    DuplicateCandidateMatch,
    IngestionCandidateDetail,
    IngestionCandidateSummary,
    IngestionJobDetail,
    IngestionJobSummary,
    PipelineStatusResponse,
    RejectCandidateRequest,
    SaveCandidateRequest,
    SaveCandidateResponse,
    UploadResponse,
)
from app.services.auth.dependencies import require_permissions
from app.services.audit_service import AuditService
from app.services.ingestion.deduplicator import find_duplicates
from app.services.ingestion.mapper import map_candidate_to_article_create
from app.services.ingestion.pipeline import run_pipeline
from app.services.knowledge.management import KnowledgeManagementService

logger = get_logger(__name__)
router = APIRouter()

DBDep = Annotated[AsyncSession, Depends(get_db)]
IngestUser = Annotated[User, Depends(require_permissions(P.KNOWLEDGE_INGEST))]
ReviewUser = Annotated[User, Depends(require_permissions(P.KNOWLEDGE_INGEST_REVIEW))]

_ALLOWED_MIME = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/markdown",
}
_ALLOWED_EXT = {"docx", "pdf", "pptx", "txt", "md"}


# ─────────────────────────────────────────────────────────────────────────────
# Upload
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    actor: IngestUser,
    db: DBDep,
) -> UploadResponse:
    """Accept a document upload and start the ingestion pipeline in the background."""
    ext = (Path(file.filename or "").suffix.lstrip(".").lower()) if file.filename else ""
    if ext not in _ALLOWED_EXT:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '.{ext}'. Allowed: {sorted(_ALLOWED_EXT)}",
        )

    # Size guard
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.MAX_UPLOAD_MB} MB limit.",
        )

    # Create job record
    repo = IngestionRepository(db)
    job = IngestionJob(
        source_filename=file.filename or f"upload.{ext}",
        source_type=ext,
        source_size=len(content),
        uploaded_by=actor.id,
        parser_version=settings.INGESTION_PARSER_VERSION,
    )
    await repo.create_job(job)
    await db.commit()
    await db.refresh(job)

    # Save file to disk under UPLOAD_DIR / job_id /
    job_dir = Path(settings.UPLOAD_DIR) / str(job.id)
    job_dir.mkdir(parents=True, exist_ok=True)
    dest = job_dir / (file.filename or f"upload.{ext}")
    dest.write_bytes(content)

    # Audit
    audit = AuditService(db)
    await audit.log(
        "document_uploaded",
        "ingestion_job",
        actor=actor,
        resource_id=str(job.id),
        description=f"Uploaded '{file.filename}' ({len(content)} bytes)",
    )
    await db.commit()

    # Run pipeline in background
    background_tasks.add_task(_run_pipeline_task, job.id)

    return UploadResponse(
        job_id=job.id,
        source_filename=job.source_filename,
        source_type=job.source_type,
        parse_status=job.parse_status,
    )


async def _run_pipeline_task(job_id: uuid.UUID) -> None:
    """Background task wrapper — creates its own DB session."""
    from app.core.database import async_session_factory

    async with async_session_factory() as db:
        try:
            await run_pipeline(job_id, db)
        except Exception:
            logger.exception("Background pipeline task failed for job=%s", job_id)


# ─────────────────────────────────────────────────────────────────────────────
# Jobs
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/jobs", response_model=list[IngestionJobSummary])
async def list_jobs(
    actor: IngestUser,
    db: DBDep,
    parse_status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[IngestionJobSummary]:
    """List all ingestion jobs (most recent first)."""
    repo = IngestionRepository(db)
    jobs = await repo.list_jobs(parse_status=parse_status, limit=limit, offset=offset)
    return [IngestionJobSummary.model_validate(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=PipelineStatusResponse)
async def get_job(
    job_id: uuid.UUID,
    actor: IngestUser,
    db: DBDep,
) -> PipelineStatusResponse:
    """Job detail with per-status candidate counts."""
    repo = IngestionRepository(db)
    job = await repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    counts = {
        s: await repo.count_candidates_for_job(job_id, review_status=s)
        for s in ("pending", "approved", "rejected", "saved")
    }
    return PipelineStatusResponse(
        job=IngestionJobDetail.model_validate(job),
        candidates_pending=counts["pending"],
        candidates_approved=counts["approved"],
        candidates_rejected=counts["rejected"],
        candidates_saved=counts["saved"],
    )


@router.post("/jobs/{job_id}/retry", response_model=IngestionJobSummary)
async def retry_job(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    actor: IngestUser,
    db: DBDep,
) -> IngestionJobSummary:
    """Re-run the pipeline for a failed job."""
    repo = IngestionRepository(db)
    job = await repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.parse_status not in ("failed", "completed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed or completed jobs can be retried.",
        )
    job = await repo.update_job(
        job_id,
        {"parse_status": "pending", "extraction_status": "pending", "error_details": None},
    )
    await db.commit()
    background_tasks.add_task(_run_pipeline_task, job_id)
    return IngestionJobSummary.model_validate(job)


# ─────────────────────────────────────────────────────────────────────────────
# Candidates — list + detail
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}/candidates", response_model=list[IngestionCandidateSummary])
async def list_candidates(
    job_id: uuid.UUID,
    actor: ReviewUser,
    db: DBDep,
    review_status: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[IngestionCandidateSummary]:
    """List all candidates for a job."""
    repo = IngestionRepository(db)
    candidates = await repo.list_candidates_for_job(
        job_id, review_status=review_status, limit=limit, offset=offset
    )
    result = []
    for c in candidates:
        summary = IngestionCandidateSummary.model_validate(c)
        summary.warning_count = len(c.validation_warnings or [])
        result.append(summary)
    return result


@router.get(
    "/jobs/{job_id}/candidates/{candidate_id}",
    response_model=IngestionCandidateDetail,
)
async def get_candidate(
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    actor: ReviewUser,
    db: DBDep,
) -> IngestionCandidateDetail:
    """Full candidate detail."""
    repo = IngestionRepository(db)
    c = await repo.get_candidate(candidate_id)
    if c is None or c.ingestion_job_id != job_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return IngestionCandidateDetail.model_validate(c)


# ─────────────────────────────────────────────────────────────────────────────
# Candidates — mutations
# ─────────────────────────────────────────────────────────────────────────────

@router.patch(
    "/jobs/{job_id}/candidates/{candidate_id}",
    response_model=IngestionCandidateDetail,
)
async def update_candidate(
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    payload: CandidateUpdatePayload,
    actor: ReviewUser,
    db: DBDep,
) -> IngestionCandidateDetail:
    """Update extracted fields on a candidate during review."""
    repo = IngestionRepository(db)
    c = await repo.get_candidate(candidate_id)
    if c is None or c.ingestion_job_id != job_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    if c.review_status == "saved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot edit a candidate that has already been saved.",
        )

    updates: dict = {}
    for field_name, value in payload.model_dump(exclude_none=True).items():
        # CandidateUpdatePayload fields are already named with the "extracted_" prefix
        # (e.g. extracted_title, extracted_category) — use them directly as column names.
        db_field = field_name
        if hasattr(c, db_field):
            # Convert Pydantic ExtractionStep models to plain dicts for JSONB
            if isinstance(value, list) and value and hasattr(value[0], "model_dump"):
                value = [v.model_dump() for v in value]
            updates[db_field] = value

    updated = await repo.update_candidate(candidate_id, updates)
    await db.commit()
    return IngestionCandidateDetail.model_validate(updated)


@router.post(
    "/jobs/{job_id}/candidates/{candidate_id}/save",
    response_model=SaveCandidateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_candidate_as_article(
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    payload: SaveCandidateRequest,
    actor: ReviewUser,
    db: DBDep,
) -> SaveCandidateResponse:
    """Promote a candidate to a draft knowledge article."""
    repo = IngestionRepository(db)
    c = await repo.get_candidate(candidate_id)
    if c is None or c.ingestion_job_id != job_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    if c.review_status == "rejected":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Rejected candidates cannot be saved."
        )
    if c.review_status == "saved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Candidate has already been saved."
        )

    # Build ArticleCreate from candidate fields
    article_create = map_candidate_to_article_create(
        {
            "extracted_title": c.extracted_title,
            "extracted_summary": c.extracted_summary,
            "extracted_category": c.extracted_category,
            "extracted_subcategory": c.extracted_subcategory,
            "extracted_product_or_system": c.extracted_product_or_system,
            "extracted_platform": c.extracted_platform,
            "extracted_symptoms": c.extracted_symptoms,
            "extracted_troubleshooting_steps": c.extracted_troubleshooting_steps,
            "extracted_resolution_steps": c.extracted_resolution_steps,
            "extracted_escalation_criteria": c.extracted_escalation_criteria,
            "extracted_tags": c.extracted_tags,
            "extracted_keywords": c.extracted_keywords,
            "extracted_owner_group": c.extracted_owner_group,
        },
        job_id=str(job_id),
        candidate_index=c.candidate_index,
        ownership_group_id=str(payload.ownership_group_id) if payload.ownership_group_id else None,
    )

    # Use existing management service to create the draft
    mgmt = KnowledgeManagementService(db)
    article = await mgmt.create_draft(actor, article_create)

    # Mark candidate as saved
    await repo.update_candidate(
        candidate_id,
        {"review_status": "saved", "mapped_article_id": article.id},
    )

    audit = AuditService(db)
    await audit.log(
        "ingestion_candidate_saved",
        "ingestion_candidate",
        actor=actor,
        resource_id=str(candidate_id),
        description=f"Saved as draft article '{article.title}' ({article.id})",
    )
    await db.commit()

    return SaveCandidateResponse(
        candidate_id=candidate_id,
        article_id=article.id,
        article_slug=article.slug,
    )


@router.post(
    "/jobs/{job_id}/candidates/{candidate_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def reject_candidate(
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    payload: RejectCandidateRequest,
    actor: ReviewUser,
    db: DBDep,
) -> Response:
    """Reject a candidate — it will not become an article."""
    repo = IngestionRepository(db)
    c = await repo.get_candidate(candidate_id)
    if c is None or c.ingestion_job_id != job_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    if c.review_status == "saved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot reject a candidate that has already been saved.",
        )
    existing_warnings = list(c.validation_warnings or [])
    if payload.reason:
        existing_warnings.append(
            {"code": "REJECTED", "message": payload.reason, "severity": "info"}
        )
    await repo.update_candidate(
        candidate_id,
        {"review_status": "rejected", "validation_warnings": existing_warnings or None},
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────────────────────────────────────
# Bulk save
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/bulk-save", response_model=BulkSaveResponse)
async def bulk_save_candidates(
    job_id: uuid.UUID,
    payload: BulkSaveRequest,
    actor: ReviewUser,
    db: DBDep,
) -> BulkSaveResponse:
    """Save multiple candidates as draft articles in a single request."""
    repo = IngestionRepository(db)
    candidates = await repo.get_candidates_by_ids(payload.candidate_ids)

    results: list[BulkSaveResult] = []
    saved_count = 0
    failed_count = 0

    for c in candidates:
        if c.ingestion_job_id != job_id:
            results.append(BulkSaveResult(
                candidate_id=c.id, success=False, error="Candidate does not belong to this job."
            ))
            failed_count += 1
            continue
        if c.review_status in ("saved", "rejected"):
            results.append(BulkSaveResult(
                candidate_id=c.id, success=False,
                error=f"Candidate status is '{c.review_status}', cannot save."
            ))
            failed_count += 1
            continue
        try:
            article_create = map_candidate_to_article_create(
                {
                    "extracted_title": c.extracted_title,
                    "extracted_summary": c.extracted_summary,
                    "extracted_category": c.extracted_category,
                    "extracted_subcategory": c.extracted_subcategory,
                    "extracted_product_or_system": c.extracted_product_or_system,
                    "extracted_platform": c.extracted_platform,
                    "extracted_symptoms": c.extracted_symptoms,
                    "extracted_troubleshooting_steps": c.extracted_troubleshooting_steps,
                    "extracted_resolution_steps": c.extracted_resolution_steps,
                    "extracted_escalation_criteria": c.extracted_escalation_criteria,
                    "extracted_tags": c.extracted_tags,
                    "extracted_keywords": c.extracted_keywords,
                    "extracted_owner_group": c.extracted_owner_group,
                },
                job_id=str(job_id),
                candidate_index=c.candidate_index,
                ownership_group_id=str(payload.ownership_group_id) if payload.ownership_group_id else None,
            )
            mgmt = KnowledgeManagementService(db)
            article = await mgmt.create_draft(actor, article_create)
            await repo.update_candidate(
                c.id, {"review_status": "saved", "mapped_article_id": article.id}
            )
            results.append(BulkSaveResult(
                candidate_id=c.id, success=True, article_id=article.id
            ))
            saved_count += 1
        except Exception as exc:
            logger.exception("Bulk save failed for candidate %s", c.id)
            results.append(BulkSaveResult(
                candidate_id=c.id, success=False, error=str(exc)
            ))
            failed_count += 1

    await db.commit()
    return BulkSaveResponse(saved=saved_count, failed=failed_count, results=results)


# ─────────────────────────────────────────────────────────────────────────────
# Duplicate lookup
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/duplicates", response_model=list[DuplicateCandidateMatch])
async def check_duplicates(
    actor: ReviewUser,
    db: DBDep,
    title: str = Query(..., min_length=3),
    tags: list[str] = Query(default_factory=list),
    product: str | None = Query(default=None),
    category: str | None = Query(default=None),
) -> list[DuplicateCandidateMatch]:
    """Check for potentially duplicate articles before saving a candidate."""
    matches = await find_duplicates(
        title=title,
        tags=tags,
        product_or_system=product,
        category=category,
        db=db,
    )
    return [
        DuplicateCandidateMatch(
            article_id=uuid.UUID(m.article_id),
            title=m.title,
            category=m.category,
            similarity_score=m.similarity_score,
            match_reason=m.match_reason,
        )
        for m in matches
    ]
