"""Data-access layer for the document ingestion pipeline.

All persistence for ingestion jobs and candidates is routed through this
repository — no inline queries in service code.  Methods flush but do not
commit; the unit-of-work is owned by the request-scoped session.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.ingestion import IngestionCandidate, IngestionJob

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class IngestionRepository:
    """Repository for IngestionJob and IngestionCandidate records."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ──────────────────────────────────────────────────────────────
    # IngestionJob
    # ──────────────────────────────────────────────────────────────

    async def create_job(self, job: IngestionJob) -> IngestionJob:
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)
        return job

    async def get_job(self, job_id: uuid.UUID) -> IngestionJob | None:
        result = await self.db.execute(select(IngestionJob).where(IngestionJob.id == job_id))
        return result.scalar_one_or_none()

    async def update_job(self, job_id: uuid.UUID, updates: dict) -> IngestionJob | None:
        job = await self.get_job(job_id)
        if job is None:
            return None
        for key, value in updates.items():
            if hasattr(job, key):
                setattr(job, key, value)
        await self.db.flush()
        await self.db.refresh(job)
        return job

    async def list_jobs(
        self,
        *,
        uploaded_by: uuid.UUID | None = None,
        parse_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IngestionJob]:
        query = select(IngestionJob).order_by(IngestionJob.created_at.desc())
        if uploaded_by is not None:
            query = query.where(IngestionJob.uploaded_by == uploaded_by)
        if parse_status is not None:
            query = query.where(IngestionJob.parse_status == parse_status)
        query = query.limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_jobs(
        self,
        *,
        uploaded_by: uuid.UUID | None = None,
        parse_status: str | None = None,
    ) -> int:
        from sqlalchemy import func

        query = select(func.count()).select_from(IngestionJob)
        if uploaded_by is not None:
            query = query.where(IngestionJob.uploaded_by == uploaded_by)
        if parse_status is not None:
            query = query.where(IngestionJob.parse_status == parse_status)
        result = await self.db.execute(query)
        return result.scalar_one()

    # ──────────────────────────────────────────────────────────────
    # IngestionCandidate
    # ──────────────────────────────────────────────────────────────

    async def create_candidate(self, candidate: IngestionCandidate) -> IngestionCandidate:
        self.db.add(candidate)
        await self.db.flush()
        await self.db.refresh(candidate)
        return candidate

    async def create_candidates_bulk(
        self, candidates: list[IngestionCandidate]
    ) -> list[IngestionCandidate]:
        for c in candidates:
            self.db.add(c)
        await self.db.flush()
        for c in candidates:
            await self.db.refresh(c)
        return candidates

    async def get_candidate(self, candidate_id: uuid.UUID) -> IngestionCandidate | None:
        result = await self.db.execute(
            select(IngestionCandidate).where(IngestionCandidate.id == candidate_id)
        )
        return result.scalar_one_or_none()

    async def update_candidate(
        self, candidate_id: uuid.UUID, updates: dict
    ) -> IngestionCandidate | None:
        candidate = await self.get_candidate(candidate_id)
        if candidate is None:
            return None
        for key, value in updates.items():
            if hasattr(candidate, key):
                setattr(candidate, key, value)
        await self.db.flush()
        await self.db.refresh(candidate)
        return candidate

    async def list_candidates_for_job(
        self,
        job_id: uuid.UUID,
        *,
        review_status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[IngestionCandidate]:
        query = (
            select(IngestionCandidate)
            .where(IngestionCandidate.ingestion_job_id == job_id)
            .order_by(IngestionCandidate.candidate_index)
        )
        if review_status is not None:
            query = query.where(IngestionCandidate.review_status == review_status)
        query = query.limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_candidates_for_job(
        self, job_id: uuid.UUID, *, review_status: str | None = None
    ) -> int:
        from sqlalchemy import func

        query = (
            select(func.count())
            .select_from(IngestionCandidate)
            .where(IngestionCandidate.ingestion_job_id == job_id)
        )
        if review_status is not None:
            query = query.where(IngestionCandidate.review_status == review_status)
        result = await self.db.execute(query)
        return result.scalar_one()

    async def get_candidates_by_ids(
        self, candidate_ids: list[uuid.UUID]
    ) -> list[IngestionCandidate]:
        result = await self.db.execute(
            select(IngestionCandidate).where(IngestionCandidate.id.in_(candidate_ids))
        )
        return list(result.scalars().all())
