"""Data-access layer for knowledge management.

All knowledge persistence goes through this repository — services never build
queries inline (per the clean-architecture rule in CLAUDE.md). Methods return
ORM models or primitives; they do not commit (the unit-of-work is owned by the
request-scoped session in ``get_db``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Integer, String, func, or_, select

from app.models.knowledge import (
    KnowledgeArticle,
    KnowledgeArticleVersion,
    KnowledgeChunk,
    KnowledgeFeedback,
    KnowledgeOwnershipGroup,
    KnowledgeReviewNote,
    KnowledgeTaxonomyTerm,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class KnowledgeRepository:
    """Repository for knowledge articles, versions, chunks, taxonomy and feedback."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Articles ────────────────────────────────────────────────

    async def get(self, article_id: uuid.UUID) -> KnowledgeArticle | None:
        result = await self.db.execute(
            select(KnowledgeArticle).where(KnowledgeArticle.id == article_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> KnowledgeArticle | None:
        result = await self.db.execute(
            select(KnowledgeArticle).where(KnowledgeArticle.slug == slug)
        )
        return result.scalar_one_or_none()

    async def add(self, article: KnowledgeArticle) -> KnowledgeArticle:
        self.db.add(article)
        await self.db.flush()
        return article

    async def delete(self, article: KnowledgeArticle) -> None:
        """Hard-delete an article and all its chunks (cascade handles chunks)."""
        await self.db.delete(article)
        await self.db.flush()

    async def list(
        self,
        *,
        statuses: list[str] | None = None,
        category: str | None = None,
        product_or_system: str | None = None,
        platform: str | None = None,
        audience: str | None = None,
        ownership_group_id: uuid.UUID | None = None,
        search: str | None = None,
        review_due_before: datetime | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> tuple[list[KnowledgeArticle], int]:
        """List articles with filtering; returns (page, total_count)."""
        conditions = []
        if statuses:
            conditions.append(KnowledgeArticle.status.in_(statuses))
        if category:
            conditions.append(KnowledgeArticle.category == category)
        if product_or_system:
            conditions.append(KnowledgeArticle.product_or_system == product_or_system)
        if platform:
            conditions.append(KnowledgeArticle.platform == platform)
        if audience:
            conditions.append(KnowledgeArticle.audience == audience)
        if ownership_group_id:
            conditions.append(KnowledgeArticle.ownership_group_id == ownership_group_id)
        if review_due_before:
            conditions.append(KnowledgeArticle.next_review_due_at.is_not(None))
            conditions.append(KnowledgeArticle.next_review_due_at <= review_due_before)
        if search:
            pattern = f"%{search.lower()}%"
            conditions.append(
                or_(
                    func.lower(KnowledgeArticle.title).like(pattern),
                    func.lower(func.coalesce(KnowledgeArticle.short_summary, "")).like(pattern),
                    func.lower(func.coalesce(KnowledgeArticle.retrieval_text, "")).like(pattern),
                    KnowledgeArticle.tags.cast(String).ilike(pattern),
                )
            )

        base = select(KnowledgeArticle)
        count_q = select(func.count()).select_from(KnowledgeArticle)
        for cond in conditions:
            base = base.where(cond)
            count_q = count_q.where(cond)

        total = (await self.db.execute(count_q)).scalar_one()
        rows = (
            (
                await self.db.execute(
                    base.order_by(KnowledgeArticle.updated_at.desc()).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), int(total)

    async def list_published(
        self,
        *,
        category: str | None = None,
        product_or_system: str | None = None,
        platform: str | None = None,
        audiences: list[str] | None = None,
        limit: int = 50,
    ) -> list[KnowledgeArticle]:
        """Published-only listing used by the retrieval layer."""
        q = select(KnowledgeArticle).where(KnowledgeArticle.status == "published")
        if category:
            q = q.where(KnowledgeArticle.category == category)
        if product_or_system:
            q = q.where(KnowledgeArticle.product_or_system == product_or_system)
        if platform:
            q = q.where(KnowledgeArticle.platform == platform)
        if audiences:
            q = q.where(KnowledgeArticle.audience.in_(audiences))
        q = q.order_by(KnowledgeArticle.usage_count.desc()).limit(limit)
        return list((await self.db.execute(q)).scalars().all())

    async def list_review_queue(self, limit: int = 50) -> list[KnowledgeArticle]:
        q = (
            select(KnowledgeArticle)
            .where(KnowledgeArticle.status == "in_review")
            .order_by(KnowledgeArticle.updated_at.asc())
            .limit(limit)
        )
        return list((await self.db.execute(q)).scalars().all())

    async def list_stale(
        self, *, now: datetime | None = None, limit: int = 100
    ) -> list[KnowledgeArticle]:
        now = now or datetime.now(UTC)
        q = (
            select(KnowledgeArticle)
            .where(
                KnowledgeArticle.status == "published",
                KnowledgeArticle.next_review_due_at.is_not(None),
                KnowledgeArticle.next_review_due_at <= now,
            )
            .order_by(KnowledgeArticle.next_review_due_at.asc())
            .limit(limit)
        )
        return list((await self.db.execute(q)).scalars().all())

    async def count_by_status(self) -> dict[str, int]:
        q = select(KnowledgeArticle.status, func.count()).group_by(KnowledgeArticle.status)
        rows = (await self.db.execute(q)).all()
        return {status: int(count) for status, count in rows}

    async def find_duplicates(
        self, title: str, *, exclude_id: uuid.UUID | None = None
    ) -> list[KnowledgeArticle]:
        """Lightweight duplicate-title detection hint for the editor."""
        tokens = [t for t in title.lower().split() if len(t) > 3]
        if not tokens:
            return []
        q = select(KnowledgeArticle)
        if exclude_id:
            q = q.where(KnowledgeArticle.id != exclude_id)
        q = q.where(
            or_(*[func.lower(KnowledgeArticle.title).like(f"%{tok}%") for tok in tokens])
        ).limit(5)
        return list((await self.db.execute(q)).scalars().all())

    # ── Versions ────────────────────────────────────────────────

    async def add_version(self, version: KnowledgeArticleVersion) -> KnowledgeArticleVersion:
        self.db.add(version)
        await self.db.flush()
        return version

    async def list_versions(self, article_id: uuid.UUID) -> list[KnowledgeArticleVersion]:
        q = (
            select(KnowledgeArticleVersion)
            .where(KnowledgeArticleVersion.article_id == article_id)
            .order_by(KnowledgeArticleVersion.version.desc())
        )
        return list((await self.db.execute(q)).scalars().all())

    async def get_version(
        self, article_id: uuid.UUID, version: int
    ) -> KnowledgeArticleVersion | None:
        q = select(KnowledgeArticleVersion).where(
            KnowledgeArticleVersion.article_id == article_id,
            KnowledgeArticleVersion.version == version,
        )
        return (await self.db.execute(q)).scalar_one_or_none()

    # ── Chunks ──────────────────────────────────────────────────

    async def replace_chunks(self, article_id: uuid.UUID, chunks: list[KnowledgeChunk]) -> None:
        existing = (
            (
                await self.db.execute(
                    select(KnowledgeChunk).where(KnowledgeChunk.article_id == article_id)
                )
            )
            .scalars()
            .all()
        )
        for chunk in existing:
            await self.db.delete(chunk)
        # Flush deletes before inserts to avoid the unique constraint on
        # (article_id, chunk_index) firing when SQLAlchemy batches them together.
        await self.db.flush()
        for chunk in chunks:
            self.db.add(chunk)
        await self.db.flush()

    async def list_chunks(self, article_id: uuid.UUID) -> list[KnowledgeChunk]:
        q = (
            select(KnowledgeChunk)
            .where(KnowledgeChunk.article_id == article_id)
            .order_by(KnowledgeChunk.chunk_index)
        )
        return list((await self.db.execute(q)).scalars().all())

    async def article_vector_scores(
        self,
        query_embedding: list[float],
        article_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, float]:
        """Best-chunk cosine similarity per article (Phase 6, pgvector).

        For each article in ``article_ids`` that has at least one embedded chunk,
        returns ``{article_id: similarity}`` where similarity = ``1 - cosine
        distance`` of the *closest* chunk to the query embedding. Articles with
        no embedded chunk are simply absent from the result (the caller treats a
        missing key as "no vector signal" and falls back to keyword for it).

        Uses pgvector's ``cosine_distance`` comparator; only chunks with a
        non-null embedding participate.
        """
        if not query_embedding or not article_ids:
            return {}
        distance = KnowledgeChunk.embedding.cosine_distance(query_embedding)
        q = (
            select(KnowledgeChunk.article_id, func.min(distance).label("distance"))
            .where(
                KnowledgeChunk.article_id.in_(article_ids),
                KnowledgeChunk.embedding.is_not(None),
            )
            .group_by(KnowledgeChunk.article_id)
        )
        rows = (await self.db.execute(q)).all()
        return {article_id: 1.0 - float(distance) for article_id, distance in rows}

    async def list_chunks_missing_embeddings(self, *, limit: int = 500) -> list[KnowledgeChunk]:
        """Chunks of published articles that have no embedding yet (backfill)."""
        q = (
            select(KnowledgeChunk)
            .join(KnowledgeArticle, KnowledgeChunk.article_id == KnowledgeArticle.id)
            .where(
                KnowledgeArticle.status == "published",
                KnowledgeChunk.embedding.is_(None),
            )
            .order_by(KnowledgeChunk.article_id, KnowledgeChunk.chunk_index)
            .limit(limit)
        )
        return list((await self.db.execute(q)).scalars().all())

    async def count_chunks(self) -> int:
        return int(
            (await self.db.execute(select(func.count()).select_from(KnowledgeChunk))).scalar_one()
        )

    # ── Feedback ────────────────────────────────────────────────

    async def add_feedback(self, feedback: KnowledgeFeedback) -> KnowledgeFeedback:
        self.db.add(feedback)
        await self.db.flush()
        return feedback

    async def list_feedback(
        self, article_id: uuid.UUID, limit: int = 50
    ) -> list[KnowledgeFeedback]:
        q = (
            select(KnowledgeFeedback)
            .where(KnowledgeFeedback.article_id == article_id)
            .order_by(KnowledgeFeedback.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.execute(q)).scalars().all())

    async def feedback_aggregate(self, article_id: uuid.UUID) -> dict:
        q = select(
            func.count(),
            func.avg(KnowledgeFeedback.rating),
            func.sum(func.cast(KnowledgeFeedback.was_helpful, Integer)),
        ).where(KnowledgeFeedback.article_id == article_id)
        count, avg_rating, helpful = (await self.db.execute(q)).one()
        return {
            "count": int(count or 0),
            "avg_rating": float(avg_rating) if avg_rating is not None else None,
            "helpful_count": int(helpful or 0),
        }

    # ── Review notes ────────────────────────────────────────────

    async def add_review_note(self, note: KnowledgeReviewNote) -> KnowledgeReviewNote:
        self.db.add(note)
        await self.db.flush()
        return note

    async def list_review_notes(self, article_id: uuid.UUID) -> list[KnowledgeReviewNote]:
        q = (
            select(KnowledgeReviewNote)
            .where(KnowledgeReviewNote.article_id == article_id)
            .order_by(KnowledgeReviewNote.created_at.asc())
        )
        return list((await self.db.execute(q)).scalars().all())

    # ── Taxonomy ────────────────────────────────────────────────

    async def list_taxonomy(self, term_type: str | None = None) -> list[KnowledgeTaxonomyTerm]:
        q = select(KnowledgeTaxonomyTerm)
        if term_type:
            q = q.where(KnowledgeTaxonomyTerm.term_type == term_type)
        q = q.order_by(KnowledgeTaxonomyTerm.term_type, KnowledgeTaxonomyTerm.sort_order)
        return list((await self.db.execute(q)).scalars().all())

    async def get_taxonomy_term(self, term_id: uuid.UUID) -> KnowledgeTaxonomyTerm | None:
        return (
            await self.db.execute(
                select(KnowledgeTaxonomyTerm).where(KnowledgeTaxonomyTerm.id == term_id)
            )
        ).scalar_one_or_none()

    async def get_taxonomy_by_key(self, term_type: str, key: str) -> KnowledgeTaxonomyTerm | None:
        return (
            await self.db.execute(
                select(KnowledgeTaxonomyTerm).where(
                    KnowledgeTaxonomyTerm.term_type == term_type,
                    KnowledgeTaxonomyTerm.key == key,
                )
            )
        ).scalar_one_or_none()

    async def add_taxonomy_term(self, term: KnowledgeTaxonomyTerm) -> KnowledgeTaxonomyTerm:
        self.db.add(term)
        await self.db.flush()
        return term

    async def delete_taxonomy_term(self, term: KnowledgeTaxonomyTerm) -> None:
        await self.db.delete(term)

    # ── Ownership groups ────────────────────────────────────────

    async def list_ownership_groups(self) -> list[KnowledgeOwnershipGroup]:
        q = select(KnowledgeOwnershipGroup).order_by(KnowledgeOwnershipGroup.display_name)
        return list((await self.db.execute(q)).scalars().all())

    async def get_ownership_group(self, group_id: uuid.UUID) -> KnowledgeOwnershipGroup | None:
        return (
            await self.db.execute(
                select(KnowledgeOwnershipGroup).where(KnowledgeOwnershipGroup.id == group_id)
            )
        ).scalar_one_or_none()

    async def add_ownership_group(self, group: KnowledgeOwnershipGroup) -> KnowledgeOwnershipGroup:
        self.db.add(group)
        await self.db.flush()
        return group
