"""Knowledge indexing pipeline.

Transforms structured articles into retrieval chunks and (re)indexes them into
the configured vector store. Embedding generation is abstracted behind
``EmbeddingClient`` so the pipeline runs identically whether a real embedding
provider is configured or not — in dev, a no-op client marks chunks as indexed
so the retrieval flow is exercised end-to-end without external dependencies.

Indexing is triggered by lifecycle events:
- ``publish``  → prepare chunks + index (article becomes retrievable)
- ``archive``  → remove from index (article stops being retrievable)
- explicit reindex (admin) → rebuild stale or selected articles
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.logging import get_logger
from app.models.knowledge import KnowledgeArticle, KnowledgeChunk
from app.services.knowledge import normalization
from app.services.knowledge.serializers import article_to_dict

if TYPE_CHECKING:
    import uuid

    from app.repositories.knowledge_repository import KnowledgeRepository

logger = get_logger(__name__)


class EmbeddingClient:
    """Abstraction over the embedding/vector backend.

    The default implementation is a no-op suitable for development and tests: it
    does not compute real vectors but lets the pipeline mark chunks indexed so
    the governed retrieval path can be validated. A production implementation
    would call the configured provider and persist vectors to pgvector.
    """

    def __init__(self, store_type: str = "pgvector") -> None:
        self.store_type = store_type
        self.available = False  # real embeddings require provider wiring

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        """Return embeddings for texts, or None when no provider is wired."""
        if not self.available:
            return None
        raise NotImplementedError("Wire a concrete embedding provider here")


class KnowledgeIndexingService:
    """Prepares and (re)indexes knowledge articles for retrieval."""

    def __init__(
        self,
        repo: KnowledgeRepository,
        *,
        embedder: EmbeddingClient | None = None,
    ) -> None:
        self.repo = repo
        self.embedder = embedder or EmbeddingClient(settings.VECTOR_STORE_TYPE)

    async def prepare_article(self, article: KnowledgeArticle) -> int:
        """Regenerate retrieval_text + chunks for an article (no index write).

        Returns the number of chunks prepared. Used on every save so the
        retrieval preview always reflects current content.
        """
        article_dict = article_to_dict(article)
        article.retrieval_text = normalization.build_retrieval_text(article_dict)
        if not article.citation_label:
            article.citation_label = normalization.build_citation_label(article_dict)

        specs = normalization.build_chunks(article_dict)
        chunks = [
            KnowledgeChunk(
                article_id=article.id,
                chunk_index=spec.chunk_index,
                section=spec.section,
                header=spec.header,
                content=spec.content,
                token_estimate=spec.token_estimate,
                embedding_status="pending",
                index_version=article.index_version,
                metadata_json=spec.metadata,
            )
            for spec in specs
        ]
        await self.repo.replace_chunks(article.id, chunks)
        article.embedding_status = "pending"
        return len(chunks)

    async def index_article(self, article: KnowledgeArticle) -> int:
        """Prepare + index an article so it becomes retrievable.

        Only published articles are indexed for the user-facing agent; callers
        gate on status before invoking this for publication.
        """
        chunk_count = await self.prepare_article(article)
        chunks = await self.repo.list_chunks(article.id)

        # Compute embeddings when a provider is wired; otherwise fall back to
        # keyword retrieval over the prepared chunks (still "indexed" + usable).
        await self.embedder.embed([c.content for c in chunks])

        article.index_version += 1
        for chunk in chunks:
            chunk.embedding_status = "indexed"
            chunk.index_version = article.index_version
        article.embedding_status = "indexed"
        article.indexed_at = datetime.now(UTC)

        logger.info(
            "knowledge_indexed",
            article_id=str(article.id),
            chunks=chunk_count,
            index_version=article.index_version,
            vector_store=self.embedder.store_type,
            real_embeddings=self.embedder.available,
        )
        return chunk_count

    async def remove_from_index(self, article: KnowledgeArticle) -> None:
        """Remove an article from the retrieval index (on archive)."""
        await self.repo.replace_chunks(article.id, [])
        article.embedding_status = "not_indexed"
        article.indexed_at = None
        logger.info("knowledge_unindexed", article_id=str(article.id))

    async def mark_stale(self, article: KnowledgeArticle) -> None:
        """Flag an indexed article as stale (content changed post-publish)."""
        if article.embedding_status == "indexed":
            article.embedding_status = "stale"

    async def reindex(
        self,
        *,
        article_ids: list[uuid.UUID] | None = None,
        only_stale: bool = False,
    ) -> dict:
        """Rebuild the index for selected, stale, or all published articles."""
        targets: list[KnowledgeArticle] = []
        errors: list[str] = []

        if article_ids:
            for aid in article_ids:
                art = await self.repo.get(aid)
                if art:
                    targets.append(art)
                else:
                    errors.append(f"Article not found: {aid}")
        elif only_stale:
            targets = await self.repo.list_stale()
            targets += [
                a
                for a in await self.repo.list_published()
                if a.embedding_status in ("stale", "pending", "not_indexed", "failed")
            ]
        else:
            targets = await self.repo.list_published()

        # de-duplicate by id while only indexing published articles
        seen: set[uuid.UUID] = set()
        chunks_written = 0
        reindexed = 0
        skipped = 0
        for art in targets:
            if art.id in seen:
                continue
            seen.add(art.id)
            if art.status != "published":
                skipped += 1
                continue
            try:
                chunks_written += await self.index_article(art)
                reindexed += 1
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("knowledge_reindex_error", article_id=str(art.id), error=str(exc))
                art.embedding_status = "failed"
                errors.append(f"{art.id}: {exc}")

        return {
            "requested": len(seen),
            "reindexed": reindexed,
            "chunks_written": chunks_written,
            "skipped": skipped,
            "errors": errors,
        }

    async def get_status(self) -> dict:
        """Aggregate indexing status for the admin indexing panel."""
        by_status = await self.repo.count_by_status()
        published = await self.repo.list_published(limit=1000)

        counts = {"indexed": 0, "pending": 0, "stale": 0, "failed": 0, "not_indexed": 0}
        last_indexed: datetime | None = None
        max_version = 0
        for art in published:
            counts[art.embedding_status] = counts.get(art.embedding_status, 0) + 1
            max_version = max(max_version, art.index_version)
            if art.indexed_at and (last_indexed is None or art.indexed_at > last_indexed):
                last_indexed = art.indexed_at

        return {
            "total_articles": sum(by_status.values()),
            "published_articles": by_status.get("published", 0),
            "indexed_articles": counts["indexed"],
            "pending_articles": counts["pending"],
            "stale_articles": counts["stale"],
            "failed_articles": counts["failed"],
            "total_chunks": await self.repo.count_chunks(),
            "index_version": max_version,
            "last_indexed_at": last_indexed.isoformat() if last_indexed else None,
            "vector_store": self.embedder.store_type,
        }
