"""Ingestion pipeline orchestrator.

Coordinates all 9 stages of the document-to-candidate pipeline:

  Stage 1 — Load job record + read file from disk
  Stage 2 — Extract raw text (``extractor``)
  Stage 3 — Persist raw text path + update job status
  Stage 4 — Parse structure into topic segments (``parser``)
  Stage 5 — Optional LLM enrichment (``llm_extractor``)
  Stage 6 — Validate + score each candidate (``validator``)
  Stage 7 — Detect duplicates (``deduplicator``)
  Stage 8 — Persist candidates to DB
  Stage 9 — Finalise job (status = completed / failed, counts)

Each stage updates the job's ``parse_status`` so the frontend can poll
progress.  Any unhandled exception in any stage sets the job to ``failed``
and records the traceback in ``error_details``.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.config import settings
from app.models.ingestion import IngestionCandidate, IngestionJob
from app.repositories.ingestion_repository import IngestionRepository
from app.services.ingestion.deduplicator import find_duplicates
from app.services.ingestion.extractor import extract_text
from app.services.ingestion.llm_extractor import enrich_candidate
from app.services.ingestion.mapper import map_candidate_to_article_create
from app.services.ingestion.parser import CandidatePayload, parse_document
from app.services.ingestion.validator import validate_candidate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

async def run_pipeline(
    job_id: uuid.UUID,
    db: AsyncSession,
    *,
    llm_service: object | None = None,
) -> IngestionJob:
    """Run the full ingestion pipeline for *job_id*.

    This function is designed to be called from a background task (FastAPI
    ``BackgroundTasks``) so it manages its own DB flush cycle.  The caller
    must have already created the ``IngestionJob`` row and saved the file to
    disk at ``settings.UPLOAD_DIR / job_id / source_filename``.

    Returns the updated ``IngestionJob`` on completion (or failure).
    """
    repo = IngestionRepository(db)
    timing: dict[str, float] = {}
    stage_start = _now()

    job = await repo.get_job(job_id)
    if job is None:
        logger.error("Pipeline called for unknown job_id=%s", job_id)
        raise ValueError(f"IngestionJob {job_id} not found")

    try:
        # ── Stage 1: locate file ──────────────────────────────────────────
        file_path = _resolve_file_path(job)
        timing["stage1_locate"] = _elapsed(stage_start)
        stage_start = _now()

        # ── Stage 2: extract text ─────────────────────────────────────────
        await repo.update_job(job_id, {"parse_status": "extracting"})
        await db.commit()

        extraction = extract_text(file_path)
        timing["stage2_extract"] = _elapsed(stage_start)
        stage_start = _now()

        # ── Stage 3: persist raw text path ────────────────────────────────
        raw_text_path = _save_raw_text(job_id, extraction.raw_text)
        await repo.update_job(
            job_id,
            {
                "extraction_status": "completed",
                "raw_text_ref": raw_text_path,
                "parser_version": settings.INGESTION_PARSER_VERSION,
            },
        )
        await db.commit()
        timing["stage3_persist_text"] = _elapsed(stage_start)
        stage_start = _now()

        # ── Stage 4: parse into topic segments ────────────────────────────
        await repo.update_job(job_id, {"parse_status": "parsing"})
        await db.commit()

        candidates: list[CandidatePayload] = parse_document(extraction.raw_text)
        timing["stage4_parse"] = _elapsed(stage_start)
        stage_start = _now()

        # ── Stage 5: optional LLM enrichment ─────────────────────────────
        if llm_service is not None and settings.INGESTION_LLM_ENABLED:
            enriched: list[CandidatePayload] = []
            for c in candidates:
                enriched.append(await enrich_candidate(c, llm_service))
            candidates = enriched
        timing["stage5_llm_enrich"] = _elapsed(stage_start)
        stage_start = _now()

        # ── Stage 6: validate + score ─────────────────────────────────────
        validated_payloads: list[tuple[CandidatePayload, list[dict]]] = []
        for c in candidates:
            vr = validate_candidate({
                "title": c.title,
                "summary": c.summary,
                "category": c.category,
                "symptoms": c.symptoms,
                "troubleshooting_steps": c.troubleshooting_steps,
                "resolution_steps": c.resolution_steps,
                "escalation_criteria": c.escalation_criteria,
                "tags": c.tags,
                "confidence": c.confidence,
            })
            # Merge validation result back into candidate confidence
            c.confidence = vr.confidence
            validated_payloads.append((c, vr.to_warning_dicts()))
        timing["stage6_validate"] = _elapsed(stage_start)
        stage_start = _now()

        # ── Stage 7: duplicate hints (non-blocking) ───────────────────────
        dup_map: dict[int, list[dict]] = {}
        for c, _ in validated_payloads:
            try:
                matches = await find_duplicates(
                    title=c.title,
                    tags=c.tags,
                    product_or_system=c.product_or_system,
                    category=c.category,
                    db=db,
                )
                if matches:
                    dup_map[c.candidate_index] = [
                        {
                            "article_id": m.article_id,
                            "title": m.title,
                            "similarity_score": m.similarity_score,
                            "match_reason": m.match_reason,
                        }
                        for m in matches
                    ]
            except Exception:
                logger.warning("Duplicate check failed for candidate %d", c.candidate_index)
        timing["stage7_dedup"] = _elapsed(stage_start)
        stage_start = _now()

        # ── Stage 8: persist candidates ───────────────────────────────────
        orm_candidates: list[IngestionCandidate] = []
        for c, warnings in validated_payloads:
            dups = dup_map.get(c.candidate_index, [])
            all_warnings = warnings + [
                {"code": "DUPLICATE_HINT", "message": f"Similar article: {d['title']}", "severity": "info"}
                for d in dups
            ]
            orm_c = IngestionCandidate(
                ingestion_job_id=job_id,
                candidate_index=c.candidate_index,
                extracted_title=c.title,
                extracted_summary=c.summary,
                extracted_category=c.category,
                extracted_subcategory=c.subcategory,
                extracted_product_or_system=c.product_or_system,
                extracted_platform=c.platform,
                extracted_symptoms=c.symptoms or None,
                extracted_troubleshooting_steps=c.troubleshooting_steps or None,
                extracted_resolution_steps=c.resolution_steps or None,
                extracted_escalation_criteria=c.escalation_criteria,
                extracted_tags=c.tags or None,
                extracted_keywords=c.keywords or None,
                extracted_confidence=c.confidence,
                validation_warnings=all_warnings or None,
                raw_segment_text=c.raw_segment_text,
                normalized_payload_json=None,
            )
            orm_candidates.append(orm_c)

        await repo.create_candidates_bulk(orm_candidates)
        await db.commit()
        timing["stage8_persist_candidates"] = _elapsed(stage_start)

        # ── Stage 9: finalise job ─────────────────────────────────────────
        timing["total"] = sum(timing.values())
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
            "Ingestion pipeline completed: job=%s candidates=%d total_time=%.2fs",
            job_id,
            len(orm_candidates),
            timing["total"],
        )
        return final_job  # type: ignore[return-value]

    except Exception as exc:
        tb = traceback.format_exc()
        logger.exception("Ingestion pipeline FAILED for job=%s", job_id)
        try:
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
            logger.exception("Could not update job status to failed for job=%s", job_id)
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_file_path(job: IngestionJob) -> Path:
    """Return the expected filesystem path for the uploaded file."""
    upload_dir = Path(settings.UPLOAD_DIR) / str(job.id)
    path = upload_dir / job.source_filename
    if not path.exists():
        # Try without job-id subdirectory (fallback)
        path = Path(settings.UPLOAD_DIR) / job.source_filename
    if not path.exists():
        raise FileNotFoundError(
            f"Uploaded file not found at expected paths for job {job.id}"
        )
    return path


def _save_raw_text(job_id: uuid.UUID, raw_text: str) -> str:
    """Write raw text to disk and return the path string."""
    out_dir = Path(settings.UPLOAD_DIR) / str(job_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "extracted_text.txt"
    out_path.write_text(raw_text, encoding="utf-8")
    return str(out_path)


def _now() -> float:
    import time
    return time.monotonic()


def _elapsed(start: float) -> float:
    import time
    return time.monotonic() - start
