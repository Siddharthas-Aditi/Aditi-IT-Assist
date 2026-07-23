"""OpenAI embedding provider wiring (Route A — direct OpenAI embeddings).

When ``LLM_PROVIDER=openai`` and an OpenAI key is configured, the knowledge
indexing pipeline must select a real, *available* embedding client that uses
``text-embedding-3-large`` at 3072 dimensions — matching the ``vector(3072)``
pgvector column. Previously the non-azure path returned ``text-embedding-3-small``
(1536 dims) and a no-op client, so semantic retrieval silently stayed keyword-only.

These are pure config/selection tests (no network). The real ``embed()`` call is
exercised by the backfill against a live provider.
"""

from __future__ import annotations


class TestEffectiveEmbeddingModel:
    def test_openai_provider_uses_large_model(self):
        """Non-azure embedding model must be 3-large (3072 dims), not 3-small (1536)."""
        from app.core.config import Settings

        s = Settings(LLM_PROVIDER="openai", LLM_API_KEY="sk-test")
        assert s.effective_embedding_model == "text-embedding-3-large"

    def test_azure_provider_keeps_prefix(self):
        """Azure path is unchanged."""
        from app.core.config import Settings

        s = Settings(
            LLM_PROVIDER="azure",
            AZURE_OPENAI_EMBEDDING_DEPLOYMENT="text-embedding-3-large",
        )
        assert s.effective_embedding_model == "azure/text-embedding-3-large"


class TestGetEmbeddingClient:
    def test_openai_provider_with_key_is_available(self, monkeypatch):
        """LLM_PROVIDER=openai + a key → a real, available embedding client."""
        from app.core.config import settings
        from app.services.knowledge import indexing

        monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
        monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test-key")

        client = indexing.get_embedding_client()

        assert client.available is True
        assert client.model == "text-embedding-3-large"
        assert client.dimensions == 3072

    def test_openai_provider_without_key_is_noop(self, monkeypatch):
        """No key → no-op client that degrades retrieval to keyword (never raises)."""
        from app.core.config import settings
        from app.services.knowledge import indexing

        monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
        monkeypatch.setattr(settings, "LLM_API_KEY", "")

        client = indexing.get_embedding_client()

        assert client.available is False
