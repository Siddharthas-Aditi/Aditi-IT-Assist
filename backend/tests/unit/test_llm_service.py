"""Unit tests for the LLM service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm_service import LLMService


def _base_mock(*, configured: bool = True, api_key: str = "sk-test"):
    """Return a settings mock with all fields required by LLMService."""
    m = MagicMock()
    m.LLM_API_KEY = api_key
    m.LLM_MODEL = "gpt-4o-mini"
    m.LLM_TEMPERATURE = 0.7
    m.LLM_MAX_TOKENS = 1024
    m.LLM_PROVIDER = "openai"
    m.effective_llm_model = "gpt-4o-mini"
    m.effective_llm_api_key = api_key if configured else ""
    m.llm_is_configured = configured
    m.AZURE_OPENAI_VERIFY_SSL = True
    m.is_azure = False
    return m


class TestLLMService:
    """Tests for LLMService."""

    def test_is_available_with_no_key(self):
        """Should report unavailable when no API key is set."""
        s = _base_mock(configured=False, api_key="")
        with patch("app.services.llm_service.settings", s):
            service = LLMService()
            assert service.is_available is False

    def test_is_available_with_placeholder_key(self):
        """Should report unavailable with placeholder key."""
        s = _base_mock(configured=False, api_key="your-api-key-here")
        with patch("app.services.llm_service.settings", s):
            service = LLMService()
            assert service.is_available is False

    def test_is_available_with_real_key(self):
        """Should report available with a real API key."""
        s = _base_mock(configured=True, api_key="sk-real-key-12345")
        with patch("app.services.llm_service.settings", s):
            service = LLMService()
            assert service.is_available is True

    @pytest.mark.asyncio
    async def test_complete_raises_when_unavailable(self):
        """Should raise RuntimeError when LLM is not configured."""
        s = _base_mock(configured=False, api_key="")
        with patch("app.services.llm_service.settings", s):
            service = LLMService()
            with pytest.raises(RuntimeError, match="LLM service not configured"):
                await service.complete("test prompt")

    @pytest.mark.asyncio
    async def test_complete_returns_response(self):
        """Should return LLM response text on success."""
        s = _base_mock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello from LLM"

        with patch("app.services.llm_service.settings", s):
            service = LLMService()
            with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
                result = await service.complete("test prompt")

        assert result == "Hello from LLM"

    @pytest.mark.asyncio
    async def test_complete_json_parses_response(self):
        """Should parse JSON from LLM response."""
        s = _base_mock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"category": "email/outlook", "confidence": 0.9}'

        with patch("app.services.llm_service.settings", s):
            service = LLMService()
            with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
                result = await service.complete_json("classify this")

        assert result["category"] == "email/outlook"
        assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_complete_json_strips_code_fences(self):
        """Should strip markdown code fences from JSON response."""
        s = _base_mock()
        fenced_json = '```json\n{"key": "value"}\n```'
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = fenced_json

        with patch("app.services.llm_service.settings", s):
            service = LLMService()
            with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
                result = await service.complete_json("test")

        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_complete_json_returns_empty_on_invalid(self):
        """Should return empty dict when response is not valid JSON."""
        s = _base_mock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not json at all"

        with patch("app.services.llm_service.settings", s):
            service = LLMService()
            with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
                result = await service.complete_json("test")

        assert result == {}
