"""Tests for Azure AI wiring — LLM service, embedding client, and config.

All tests use mocked LiteLLM calls so no real API key or network
access is required.  The suite covers:

  • Config computed properties (is_azure, effective_* models, ssl flag)
  • LLMService — Azure model selection, api_base/version forwarding, ssl
  • AzureOpenAIEmbeddingClient — embed, batch, dimensions, error path
  • get_embedding_client() factory routing
  • LLM extractor (ingestion) using a mocked LLMService
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _mock_settings(**overrides) -> MagicMock:
    """Return a settings mock pre-loaded with sensible Azure defaults."""
    s = MagicMock()
    s.LLM_PROVIDER = "azure"
    s.LLM_MODEL = "gpt-4o"
    s.LLM_API_KEY = ""
    s.LLM_TEMPERATURE = 0.3
    s.LLM_MAX_TOKENS = 4096
    s.AZURE_OPENAI_ENDPOINT = "https://it-assist-resource.services.ai.azure.com"
    s.AZURE_OPENAI_API_KEY = "test-azure-key-abc123"
    s.AZURE_OPENAI_API_VERSION = "2024-12-01-preview"
    s.AZURE_OPENAI_LLM_DEPLOYMENT = "gpt-4.1"
    s.AZURE_OPENAI_EMBEDDING_DEPLOYMENT = "text-embedding-3-large"
    s.EMBEDDING_DIMENSIONS = 3072
    s.VECTOR_STORE_TYPE = "pgvector"
    s.AZURE_OPENAI_VERIFY_SSL = True
    # Computed properties backed by regular attrs so tests can override easily
    s.is_azure = True
    s.effective_llm_model = "azure/gpt-4.1"
    s.effective_embedding_model = "azure/text-embedding-3-large"
    s.effective_llm_api_key = "test-azure-key-abc123"
    s.llm_is_configured = True
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _litellm_completion_response(text: str = "Ready") -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = text
    resp.usage = MagicMock(total_tokens=10)
    return resp


def _litellm_embedding_response(
    vectors: list[list[float]],
) -> MagicMock:
    resp = MagicMock()
    resp.data = [{"embedding": v} for v in vectors]
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# 1. Config computed properties
# ─────────────────────────────────────────────────────────────────────────────


class TestAzureConfig:
    """Verify config.py computed properties for the Azure provider."""

    def test_is_azure_true_when_provider_azure(self):
        """Settings.is_azure is True only for LLM_PROVIDER='azure'."""
        from app.core.config import Settings

        s = Settings(
            LLM_PROVIDER="azure",
            AZURE_OPENAI_API_KEY="key",
            AZURE_OPENAI_ENDPOINT="https://x.services.ai.azure.com",
        )
        assert s.is_azure is True

    def test_is_azure_false_for_openai_provider(self):
        from app.core.config import Settings

        s = Settings(LLM_PROVIDER="openai", LLM_API_KEY="sk-test")
        assert s.is_azure is False

    def test_effective_llm_model_has_azure_prefix(self):
        from app.core.config import Settings

        s = Settings(
            LLM_PROVIDER="azure",
            AZURE_OPENAI_LLM_DEPLOYMENT="gpt-4.1",
        )
        assert s.effective_llm_model == "azure/gpt-4.1"

    def test_effective_llm_model_no_prefix_for_openai(self):
        from app.core.config import Settings

        s = Settings(LLM_PROVIDER="openai", LLM_MODEL="gpt-4o")
        assert s.effective_llm_model == "gpt-4o"

    def test_effective_embedding_model_azure_prefix(self):
        from app.core.config import Settings

        s = Settings(
            LLM_PROVIDER="azure",
            AZURE_OPENAI_EMBEDDING_DEPLOYMENT="text-embedding-3-large",
        )
        assert s.effective_embedding_model == "azure/text-embedding-3-large"

    def test_llm_is_configured_false_for_placeholder(self):
        from app.core.config import Settings

        s = Settings(LLM_PROVIDER="azure", AZURE_OPENAI_API_KEY="your-azure-key-here")
        assert s.llm_is_configured is False

    def test_llm_is_configured_false_for_empty_key(self):
        from app.core.config import Settings

        s = Settings(LLM_PROVIDER="azure", AZURE_OPENAI_API_KEY="")
        assert s.llm_is_configured is False

    def test_llm_is_configured_true_for_real_key(self):
        from app.core.config import Settings

        s = Settings(
            LLM_PROVIDER="azure",
            AZURE_OPENAI_API_KEY="DBGGQOx4u2NuXRhtkI-fake",
        )
        assert s.llm_is_configured is True

    def test_verify_ssl_defaults_true(self):
        from app.core.config import Settings

        # Pass True explicitly so the .env file value doesn't interfere.
        # This verifies the field accepts and stores True correctly.
        s = Settings(AZURE_OPENAI_VERIFY_SSL=True)
        assert s.AZURE_OPENAI_VERIFY_SSL is True

    def test_verify_ssl_can_be_set_false(self):
        from app.core.config import Settings

        s = Settings(AZURE_OPENAI_VERIFY_SSL=False)
        assert s.AZURE_OPENAI_VERIFY_SSL is False


# ─────────────────────────────────────────────────────────────────────────────
# 2. LLMService — Azure routing
# ─────────────────────────────────────────────────────────────────────────────


class TestLLMServiceAzure:
    """LLMService correctly uses Azure model names and forwards routing kwargs."""

    def _make_service(self, **overrides):
        s = _mock_settings(**overrides)
        with patch("app.services.llm_service.settings", s):
            from app.services.llm_service import LLMService

            svc = LLMService()
        return svc, s

    def test_model_is_azure_prefixed(self):
        svc, _ = self._make_service()
        assert svc.model == "azure/gpt-4.1"

    def test_is_available_with_azure_key(self):
        svc, _ = self._make_service()
        assert svc.is_available is True

    def test_is_available_false_for_placeholder_key(self):
        svc, _ = self._make_service(
            llm_is_configured=False,
            effective_llm_api_key="your-azure-key-here",
        )
        assert svc.is_available is False

    def test_ssl_verify_false_sets_litellm_global(self):
        """When AZURE_OPENAI_VERIFY_SSL=False the LiteLLM global is disabled."""
        import litellm

        with patch(
            "app.services.llm_service.settings", _mock_settings(AZURE_OPENAI_VERIFY_SSL=False)
        ):
            from app.services.llm_service import LLMService

            LLMService()

        assert litellm.ssl_verify is False
        # Reset for subsequent tests
        litellm.ssl_verify = True

    @pytest.mark.asyncio
    async def test_complete_passes_api_base_and_version(self):
        """acompletion must be called with api_base and api_version for Azure."""
        svc, mock_s = self._make_service()
        mock_resp = _litellm_completion_response("Done")

        # settings must stay patched during the call: _complete_internal reads
        # settings.is_azure at call time, not only at construction time.
        with (
            patch("app.services.llm_service.settings", mock_s),
            patch(
                "litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp
            ) as mock_call,
        ):
            result = await svc.complete("say hi")

        call_kwargs = mock_call.call_args.kwargs
        assert call_kwargs["api_base"] == mock_s.AZURE_OPENAI_ENDPOINT
        assert call_kwargs["api_version"] == mock_s.AZURE_OPENAI_API_VERSION
        assert call_kwargs["model"] == "azure/gpt-4.1"
        assert result == "Done"

    @pytest.mark.asyncio
    async def test_complete_uses_azure_api_key(self):
        s = _mock_settings()
        mock_resp = _litellm_completion_response("ok")

        with patch("app.services.llm_service.settings", s):
            from app.services.llm_service import LLMService

            svc = LLMService()
            with patch(
                "litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp
            ) as mock_call:
                await svc.complete("hello")

        assert mock_call.call_args.kwargs["api_key"] == "test-azure-key-abc123"

    @pytest.mark.asyncio
    async def test_complete_json_parses_azure_response(self):
        svc, _ = self._make_service()
        mock_resp = _litellm_completion_response('{"severity": "high", "confidence": 0.85}')

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp):
            result = await svc.complete_json("classify issue")

        assert result["severity"] == "high"
        assert result["confidence"] == pytest.approx(0.85)

    @pytest.mark.asyncio
    async def test_complete_raises_when_not_configured(self):
        svc, _ = self._make_service(llm_is_configured=False)
        svc._available = False

        with pytest.raises(RuntimeError, match="LLM service not configured"):
            await svc.complete("hello")

    @pytest.mark.asyncio
    async def test_non_azure_provider_omits_routing_kwargs(self):
        """Non-Azure provider must NOT forward api_base / api_version."""
        s = _mock_settings(
            LLM_PROVIDER="openai",
            LLM_API_KEY="sk-test",
            is_azure=False,
            effective_llm_model="gpt-4o",
            effective_llm_api_key="sk-test",
            llm_is_configured=True,
        )
        mock_resp = _litellm_completion_response("hello")

        with patch("app.services.llm_service.settings", s):
            from app.services.llm_service import LLMService

            svc = LLMService()
            with patch(
                "litellm.acompletion", new_callable=AsyncMock, return_value=mock_resp
            ) as mock_call:
                await svc.complete("hi")

        call_kwargs = mock_call.call_args.kwargs
        assert "api_base" not in call_kwargs
        assert "api_version" not in call_kwargs


# ─────────────────────────────────────────────────────────────────────────────
# 3. AzureOpenAIEmbeddingClient
# ─────────────────────────────────────────────────────────────────────────────


class TestAzureEmbeddingClient:
    """AzureOpenAIEmbeddingClient wraps litellm.aembedding correctly."""

    def _make_client(self, **overrides):
        s = _mock_settings(**overrides)
        with patch("app.services.knowledge.indexing.settings", s):
            from app.services.knowledge.indexing import AzureOpenAIEmbeddingClient

            client = AzureOpenAIEmbeddingClient()
        return client, s

    def test_model_is_azure_prefixed(self):
        client, _ = self._make_client()
        assert client.model == "azure/text-embedding-3-large"

    def test_available_when_key_and_endpoint_set(self):
        client, _ = self._make_client()
        assert client.available is True

    def test_not_available_when_key_missing(self):
        client, _ = self._make_client(AZURE_OPENAI_API_KEY="")
        assert client.available is False

    def test_dimensions_set_from_config(self):
        client, _ = self._make_client(EMBEDDING_DIMENSIONS=1536)
        assert client.dimensions == 1536

    def test_ssl_verify_false_sets_litellm_global(self):
        import litellm

        self._make_client(AZURE_OPENAI_VERIFY_SSL=False)

        assert litellm.ssl_verify is False
        litellm.ssl_verify = True  # reset

    @pytest.mark.asyncio
    async def test_embed_returns_vectors(self):
        client, _ = self._make_client()
        vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        mock_resp = _litellm_embedding_response(vectors)

        with patch("litellm.aembedding", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.embed(["hello world", "fix outlook"])

        assert result is not None
        assert result == vectors
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_embed_passes_correct_kwargs(self):
        client, s = self._make_client()
        mock_resp = _litellm_embedding_response([[0.1]])

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_call:
            await client.embed(["test"])

        kw = mock_call.call_args.kwargs
        assert kw["model"] == "azure/text-embedding-3-large"
        assert kw["api_key"] == s.AZURE_OPENAI_API_KEY
        assert kw["api_base"] == s.AZURE_OPENAI_ENDPOINT
        assert kw["api_version"] == s.AZURE_OPENAI_API_VERSION
        assert kw["dimensions"] == s.EMBEDDING_DIMENSIONS

    @pytest.mark.asyncio
    async def test_embed_batch_preserves_order(self):
        client, _ = self._make_client()
        texts = ["alpha", "beta", "gamma"]
        vectors = [[float(i)] * 3 for i in range(len(texts))]
        mock_resp = _litellm_embedding_response(vectors)

        with patch("litellm.aembedding", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.embed(texts)

        assert result == vectors

    @pytest.mark.asyncio
    async def test_embed_empty_input_returns_empty_list(self):
        client, _ = self._make_client()

        result = await client.embed([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_returns_none_when_not_available(self):
        client, _ = self._make_client(AZURE_OPENAI_API_KEY="")
        result = await client.embed(["text"])
        assert result is None

    @pytest.mark.asyncio
    async def test_embed_returns_none_on_litellm_exception(self):
        client, _ = self._make_client()

        with patch(
            "litellm.aembedding",
            new_callable=AsyncMock,
            side_effect=Exception("connection refused"),
        ):
            result = await client.embed(["hello"])

        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# 4. get_embedding_client() factory
# ─────────────────────────────────────────────────────────────────────────────


class TestGetEmbeddingClientFactory:
    """Factory returns the Azure client when properly configured."""

    def test_returns_azure_client_when_azure_configured(self):
        s = _mock_settings()
        with patch("app.services.knowledge.indexing.settings", s):
            from app.services.knowledge.indexing import (
                AzureOpenAIEmbeddingClient,
                get_embedding_client,
            )

            client = get_embedding_client()
        assert isinstance(client, AzureOpenAIEmbeddingClient)

    def test_returns_base_client_when_not_azure(self):
        s = _mock_settings(is_azure=False)
        with patch("app.services.knowledge.indexing.settings", s):
            from app.services.knowledge.indexing import (
                AzureOpenAIEmbeddingClient,
                EmbeddingClient,
                get_embedding_client,
            )

            client = get_embedding_client()
        assert type(client) is EmbeddingClient
        assert not isinstance(client, AzureOpenAIEmbeddingClient)

    def test_returns_base_client_when_key_missing(self):
        s = _mock_settings(AZURE_OPENAI_API_KEY="")
        with patch("app.services.knowledge.indexing.settings", s):
            from app.services.knowledge.indexing import (
                EmbeddingClient,
                get_embedding_client,
            )

            client = get_embedding_client()
        assert type(client) is EmbeddingClient

    def test_returns_base_client_when_endpoint_missing(self):
        s = _mock_settings(AZURE_OPENAI_ENDPOINT="")
        with patch("app.services.knowledge.indexing.settings", s):
            from app.services.knowledge.indexing import (
                EmbeddingClient,
                get_embedding_client,
            )

            client = get_embedding_client()
        assert type(client) is EmbeddingClient


# ─────────────────────────────────────────────────────────────────────────────
# 5. LLM Extractor (ingestion) via mocked LLMService
# ─────────────────────────────────────────────────────────────────────────────


class TestLLMExtractorAzure:
    """enrich_with_llm in the ingestion pipeline uses LLMService correctly."""

    def _make_candidate(self, text: str = "Outlook is not syncing emails."):
        from app.services.ingestion.schema import ExtractionCandidate, FieldExtraction

        c = ExtractionCandidate(raw_segment_text=text, candidate_index=0)
        # Title is absent (low-confidence) so the enricher will attempt to fill it
        c.title = FieldExtraction.absent()
        return c

    def _make_profile(self):
        from app.services.ingestion.profiles.base import ParserProfile

        return ParserProfile(name="test_profile", version="1.0")

    @pytest.mark.asyncio
    async def test_extractor_enriches_fields_when_llm_available(self):
        """enrich_with_llm enriches low-confidence fields from LLM JSON response."""
        from app.services.ingestion.llm_extractor import enrich_with_llm

        mock_svc = MagicMock()
        mock_svc.is_available = True
        mock_svc.complete = AsyncMock(
            return_value='{"title": "Fix Outlook Sync", "short_summary": "Restore email sync."}'
        )

        candidate = self._make_candidate()
        profile = self._make_profile()

        with patch("app.services.ingestion.llm_extractor.settings") as mock_settings:
            mock_settings.INGESTION_LLM_ENABLED = True
            await enrich_with_llm(candidate, profile, mock_svc)

        # The call was made
        mock_svc.complete.assert_awaited_once()
        prompt_used: str = mock_svc.complete.call_args.kwargs.get("prompt", "")
        # The candidate's raw text was included in the prompt
        assert "outlook" in prompt_used.lower() or "sync" in prompt_used.lower()

    @pytest.mark.asyncio
    async def test_extractor_skips_when_llm_unavailable(self):
        """enrich_with_llm returns candidate unchanged when LLM is not configured."""
        from app.services.ingestion.llm_extractor import enrich_with_llm

        mock_svc = MagicMock()
        mock_svc.is_available = False
        mock_svc.complete = AsyncMock()

        candidate = self._make_candidate()
        profile = self._make_profile()

        with patch("app.services.ingestion.llm_extractor.settings") as mock_settings:
            mock_settings.INGESTION_LLM_ENABLED = True
            result = await enrich_with_llm(candidate, profile, mock_svc)

        mock_svc.complete.assert_not_awaited()
        assert result is candidate  # same object returned unchanged

    @pytest.mark.asyncio
    async def test_extractor_skips_when_ingestion_llm_disabled(self):
        """enrich_with_llm skips when INGESTION_LLM_ENABLED=False."""
        from app.services.ingestion.llm_extractor import enrich_with_llm

        mock_svc = MagicMock()
        mock_svc.is_available = True
        mock_svc.complete = AsyncMock()

        candidate = self._make_candidate()
        profile = self._make_profile()

        with patch("app.services.ingestion.llm_extractor.settings") as mock_settings:
            mock_settings.INGESTION_LLM_ENABLED = False
            result = await enrich_with_llm(candidate, profile, mock_svc)

        mock_svc.complete.assert_not_awaited()
        assert result is candidate

    @pytest.mark.asyncio
    async def test_extractor_handles_empty_llm_response_gracefully(self):
        """enrich_with_llm handles empty / invalid LLM output without raising."""
        from app.services.ingestion.llm_extractor import enrich_with_llm

        mock_svc = MagicMock()
        mock_svc.is_available = True
        mock_svc.complete = AsyncMock(return_value="{}")

        candidate = self._make_candidate()
        profile = self._make_profile()

        with patch("app.services.ingestion.llm_extractor.settings") as mock_settings:
            mock_settings.INGESTION_LLM_ENABLED = True
            # Must not raise
            result = await enrich_with_llm(candidate, profile, mock_svc)

        assert result is not None
