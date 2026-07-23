"""Backfill pgvector embeddings for published knowledge chunks (Phase 6).

Run after configuring an embedding provider to populate vectors for content
that was indexed before semantic retrieval was enabled (chunks left at
``embedding_status='pending'`` with a NULL ``embedding``).

Usage:
    docker compose exec backend uv run python -m scripts.backfill_embeddings
    # or locally:
    python -m scripts.backfill_embeddings [--batch-size 64]

Safe to run repeatedly (idempotent): only chunks missing an embedding are
touched. No-op with a clear message when no embedding provider is configured.
"""

from __future__ import annotations

import argparse
import asyncio

from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.knowledge.indexing import KnowledgeIndexingService

logger = get_logger(__name__)


async def _run(batch_size: int) -> dict:
    total_embedded = 0
    async with async_session_factory() as session:
        repo = KnowledgeRepository(session)
        service = KnowledgeIndexingService(repo)
        if not service.embedder.available:
            print(
                "No embedding provider configured. Set either LLM_PROVIDER=openai "
                "+ LLM_API_KEY, or LLM_PROVIDER=azure + AZURE_OPENAI_*. "
                "Nothing to backfill."
            )
            return {"embedded": 0, "skipped_no_provider": True}

        # Loop batches until no pending chunks remain.
        while True:
            result = await service.backfill_embeddings(batch_size=batch_size)
            total_embedded += result["embedded"]
            await session.commit()
            if result["embedded"] == 0 or not result.get("remaining"):
                break

    print(f"Backfill complete: embedded {total_embedded} chunk(s).")
    return {"embedded": total_embedded, "skipped_no_provider": False}


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill knowledge chunk embeddings.")
    parser.add_argument("--batch-size", type=int, default=64, help="Chunks per embedding call.")
    args = parser.parse_args()
    asyncio.run(_run(args.batch_size))


if __name__ == "__main__":
    main()
