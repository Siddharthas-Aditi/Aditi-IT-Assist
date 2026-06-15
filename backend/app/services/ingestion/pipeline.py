"""Ingestion pipeline orchestrator — adaptive schema-stable architecture.

Nine-stage pipeline from uploaded file to structured candidates:

  Stage 1 — Load job record + locate file on disk
  Stage 2 — Extract raw text (``extractor``)
  Stage 3 — Persist raw text reference + update job status
  Stage 4 — Normalize document structure (``normalizer`` — Layer B)
  Stage 5 — Detect parser profile (``profiles.registry``)
  Stage 6 — Segment into topic blocks (``segmenter`` — Layer C)
  Stage 7 — Extract fields per segment (``field_extractor`` — Layer D)
  Stage 8 — Optional LLM enrichment (``llm_extractor`` — Layer D+)
  Stage 9 — Score confidence, validate, dedup, persist

ADAPTIVE DESIGN:
  - Stages 4-7 are schema-stable: changing how documents parse requires only a
    new/updated ``ParserProfile`` — never pipeline code changes.
  - LLM enrichment (Stage 8) is opt-in via ``settings.INGESTION_LLM_ENABLED``.
  - Any stage failure: job is marked ``failed`` with traceback in error_details.
"""

from __future__ import annotations

import logging
import traceback
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.config import settings
from app.models.ingestion import IngestionCandidate, IngestionJob
from app.repositories.ingestion_repository import IngestionRepository
from app.services.ingestion.confidence import score_candidate
from app.services.ingestion.deduplicator import find_duplicates
from app.services.ingestion.extractor import extract_text
from app.services.ingestion.field_extractor import extract_fields
from app.services.ingestion.llm_extractor import enrich_with_llm
from app.services.ingestion.normalizer import normalize_document
from app.services.ingestion.profiles.registry import detect_profile
from app.services.ingestion.schema import ExtractionCandidate, SCHEMA_VERSION
from app.services.ingestion.segmenter import segment_document
from app.services.ingestion.validator import validate_candidate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── Public entry point ────────────────────────────────────────────────────────

async def run_pipeline(
    job_id: uuid.UUID,
    db: AsyncSession,
    *,
    llm_service: object | None = None,
) -> IngestionJob:
    """Run the full ingestion pipeline for *job_id*.

    Designed for use from a FastAPI ``BackgroundTasks`` callback.  The caller
    must have created the ``IngestionJob`` row and saved the uploaded file to
    ``settings.UPLOAD_DIR/<job_id>/<source_filename>`` before calling this.

    Returns the updated ``IngestionJob`` on success; re-raises after marking
    the job ``failed`` on any unhandled exception.
    """
    repo = IngestionRepository(db)
    timing: dict[str, float] = {}
    t = _now()

    job = await repo.get_job(job_id)
    if job is None:
        logger.error("Pipeline called for unknown job_id=%s", job_id)
        raise ValueError(f"IngestionJob {job_id} not found")

    try:
        # ── Stage 1: locate file ──────────────────────────────────────────
        file_path = _resolve_file_path(job)
        timing["s1_locate"] = _elapsed(t); t = _now()

        # ── Stage 2: extract raw text ─────────────────────────────────────
        await repo.update_job(job_id, {"parse_status": "extracting"})
        await db.commit()

        extraction = extract_text(file_path)
        raw_text = extraction.raw_text
        timing["s2_extract"] = _elapsed(t); t = _now()

        # ── Stage 3: persist raw text reference ───────────────────────────
        raw_text_path = _save_raw_text(job_id, raw_text)
        await repo.update_job(
            job_id,
            {
                "extraction_status": "completed",
                "raw_text_ref": raw_text_path,
                "parser_version": settings.INGESTION_PARSER_VERSION,
            },
        )
        await db.commit()
        timing["s3_persist_text"] = _elapsed(t); t = _now()

        # ── Stage 4: normalize ─────────────────────────────────────────────
        await repo.update_job(job_id, {"parse_status": "parsing"})
        await db.commit()

        source_format = job.source_type or "txt"  # noqa: F841 — kept for future use
        norm_doc = normalize_document(raw_text)
        timing["s4_normalize"] = _elapsed(t); t = _now()

        # ── Stage 5: detect profile ────────────────────────────────────────
        profile = detect_profile(raw_text)
        logger.info("job=%s detected profile=%s", job_id, profile.name)

        # ── Stage 6: segment ───────────────────────────────────────────────
        segments = segment_document(norm_doc, profile)
        timing["s6_segment"] = _elapsed(t); t = _now()

        if not segments:
            await repo.update_job(
                job_id,
                {
                    "parse_status": "failed",
                    "error_details": "Segmenter produced 0 segments — document may be empty or unreadable.",
                },
            )
            await db.commit()
            raise RuntimeError("No segments produced by segmenter")

        # ── Stage 7: field extraction (deterministic) ─────────────────────
        parser_version = settings.INGESTION_PARSER_VERSION
        candidates: list[ExtractionCandidate] = [
            extract_fields(seg, profile, candidate_index=i, parser_version=parser_version)
            for i, seg in enumerate(segments)
        ]
        timing["s7_field_extract"] = _elapsed(t); t = _now()

        # ── Stage 8: optional LLM enrichment ─────────────────────────────
        if llm_service is not None:
            enriched: list[ExtractionCandidate] = []
            for c in candidates:
                enriched.append(await enrich_with_llm(c, profile, llm_service))
            candidates = enriched
        timing["s8_llm_enrich"] = _elapsed(t); t = _now()

        # ── Stage 9: score, validate, dedup, persist ──────────────────────
        orm_candidates: list[IngestionCandidate] = []

        for candidate in candidates:
            # Score
            candidate = score_candidate(candidate, profile)

            # Validate (works on flat dict)
            vr = validate_candidate(_candidate_to_validator_dict(candidate))

            # Duplicate hints — use a SAVEPOINT so that if the SELECT fails
            # (e.g. schema mismatch, transient error) the outer transaction is
            # NOT poisoned. Without this, a caught Python exception still leaves
            # the PostgreSQL connection in an aborted-transaction state, causing
            # every subsequent statement to fail with InFailedSQLTransactionError.
            dup_warnings: list[dict] = []
            try:
                dup_title = str(candidate.field_value("title") or "")
                dup_tags = list(candidate.field_value("tags") or [])  # type: ignore[arg-type]
                dup_product = _str_val(candidate.field_value("product_or_system"))
                dup_category = _str_val(candidate.field_value("category"))
                async with db.begin_nested():
                    matches = await find_duplicates(
                        title=dup_title,
                        tags=dup_tags,
                        product_or_system=dup_product,
                        category=dup_category,
                        db=db,
                    )
                dup_warnings = [
                    {
                        "code": "DUPLICATE_HINT",
                        "message": f"Similar article: {m.title} ({m.similarity_score:.0%})",
                        "severity": "info",
                    }
                    for m in matches
                ]
            except Exception:
                logger.warning("Duplicate check failed for candidate %d", candidate.candidate_index)

            all_warnings = vr.to_warning_dicts() + dup_warnings

            # Build normalised payload JSONB (schema provenance + per-field confidence)
            norm_payload = {
                "schema_version": candidate.schema_version,
                "parser_profile": candidate.parser_profile,
                "parser_version": candidate.parser_version,
                "confidence_level": candidate.confidence_level,
                "review_required": candidate.review_required,
                "parser_warnings": candidate.parser_warnings,
                "field_confidences": {
                    fname: candidate.field_confidence(fname)
                    for fname in [
                        "title", "category", "subcategory", "short_summary",
                        "product_or_system", "platform", "symptoms",
                        "troubleshooting_steps", "resolution_steps",
                        "escalation_criteria", "tags",
                    ]
                },
                "extraction_metadata": candidate.build_metadata(),
            }

            orm_c = IngestionCandidate(
                ingestion_job_id=job_id,
                candidate_index=candidate.candidate_index,
                extracted_title=_str_val(candidate.field_value("title")),
                extracted_summary=_str_val(candidate.field_value("short_summary")),
                extracted_category=_str_val(candidate.field_value("category")),
                extracted_subcategory=_str_val(candidate.field_value("subcategory")),
                extracted_product_or_system=_str_val(candidate.field_value("product_or_system")),
                extracted_platform=_str_val(candidate.field_value("platform")),
                extracted_symptoms=candidate.field_value("symptoms") or None,
                extracted_troubleshooting_steps=candidate.field_value("troubleshooting_steps") or None,
                extracted_resolution_steps=candidate.field_value("resolution_steps") or None,
                extracted_escalation_criteria=_str_val(candidate.field_value("escalation_criteria")),
                extracted_tags=candidate.field_value("tags") or None,
                extracted_keywords=candidate.field_value("keywords") or None,
                extracted_confidence=candidate.extraction_confidence,
                validation_warnings=all_warnings or None,
                raw_segment_text=candidate.raw_segment_text,
                normalized_payload_json=norm_payload,
            )
            orm_candidates.append(orm_c)

        await repo.create_candidates_bulk(orm_candidates)
        await db.commit()
        timing["s9_persist"] = _elapsed(t)
        timing["total"] = sum(timing.values())

        # ── Finalize job ───────────────────────────────────────────────────
        final_job = await repo.update_job(
            job_id,
            {
                "parse_status": "completed",
                "extraction_status": "completed",
                "candidate_count": len(orm_candidates),
                "processing_summary": {k: round(v, 3) for k, v in timing.items()},
            },
        )
        await db.commit()
        logger.info(
            "Ingestion pipeline completed: job=%s profile=%s segments=%d total=%.2fs",
            job_id, profile.name, len(orm_candidates), timing["total"],
        )
        return final_job  # type: ignore[return-value]

    except Exception as exc:
        tb = traceback.format_exc()
        logger.exception("Ingestion pipeline FAILED for job=%s", job_id)
        try:
            # The session may be in a failed/rolled-back state after the error.
            # Explicitly roll back before issuing new SQL so we get a clean
            # transaction for the status update.
            await db.rollback()
            await repo.update_job(
                job_id,
                {
                    "parse_status": "failed",
                    "extraction_status": "failed",
                    "error_details": f"{exc}\n\n{tb}"[:4000],
                },
            )
            await db.commit()
        except Exception:
            logger.exception("Could not update job to failed for job=%s", job_id)
        raise


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_file_path(job: IngestionJob) -> Path:
    upload_dir = Path(settings.UPLOAD_DIR) / str(job.id)
    path = upload_dir / job.source_filename
    if not path.exists():
        path = Path(settings.UPLOAD_DIR) / job.source_filename
    if not path.exists():
        raise FileNotFoundError(
            f"Uploaded file not found for job {job.id}: {job.source_filename}"
        )
    return path


def _save_raw_text(job_id: uuid.UUID, raw_text: str) -> str:
    out_dir = Path(settings.UPLOAD_DIR) / str(job_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "extracted_text.txt"
    out_path.write_text(raw_text, encoding="utf-8")
    return str(out_path)


def _candidate_to_validator_dict(c: ExtractionCandidate) -> dict:
    """Convert an ExtractionCandidate to the flat dict validate_candidate expects."""
    return {
        "title": c.field_value("title"),
        "summary": c.field_value("short_summary"),
        "category": c.field_value("category"),
        "symptoms": c.field_value("symptoms") or [],
        "troubleshooting_steps": c.field_value("troubleshooting_steps") or [],
        "resolution_steps": c.field_value("resolution_steps") or [],
        "escalation_criteria": c.field_value("escalation_criteria"),
        "tags": c.field_value("tags") or [],
        "keywords": c.field_value("keywords") or [],
        "confidence": c.extraction_confidence,
    }


def _str_val(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _now() -> float:
    import time
    return time.monotonic()


def _elapsed(start: float) -> float:
    import time
    return time.monotonic() - start
