"""Unit tests for the LLM service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm_service import LLMService


class TestLLMService:
    """Tests for LLMService."""

    def test_is_available_with_no_key(self):
        """Should report unavailable when no API key is set."""
        with patch("app.services.llm_service.settings") as mock_settings:
            mock_settings.LLM_API_KEY = ""
            mock_settings.LLM_MODEL = "gpt-4o-mini"
            mock_settings.LLM_TEMPERATURE = 0.7
            mock_settings.LLM_MAX_TOKENS = 1024
            service = LLMService()
            assert service.is_available is False

    def test_is_available_with_placeholder_key(self):
        """Should report unavailable with placeholder key."""
        with patch("app.services.llm_service.settings") as mock_settings:
            mock_settings.LLM_API_KEY = "your-api-key-here"
            mock_settings.LLM_MODEL = "gpt-4o-mini"
            mock_settings.LLM_TEMPERATURE = 0.7
            mock_settings.LLM_MAX_TOKENS = 1024
            service = LLMService()
            assert service.is_available is False

    def test_is_available_with_real_key(self):
        """Should report available with a real API key."""
        with patch("app.services.llm_service.settings") as mock_settings:
            mock_settings.LLM_API_KEY = "sk-real-key-12345"
            mock_settings.LLM_MODEL = "gpt-4o-mini"
            mock_settings.LLM_TEMPERATURE = 0.7
            mock_settings.LLM_MAX_TOKENS = 1024
            service = LLMService()
            assert service.is_available is True

    @pytest.mark.asyncio
    async def test_complete_raises_when_unavailable(self):
        """Should raise RuntimeError when LLM is not configured."""
        with patch("app.services.llm_service.settings") as mock_settings:
            mock_settings.LLM_API_KEY = ""
            mock_settings.LLM_MODEL = "gpt-4o-mini"
            mock_settings.LLM_TEMPERATURE = 0.7
            mock_settings.LLM_MAX_TOKENS = 1024
            service = LLMService()
            with pytest.raises(RuntimeError, match="LLM service not configured"):
                await service.complete("test prompt")

    @pytest.mark.asyncio
    async def test_complete_returns_response(self):
        """Should return LLM response text on success."""
        with patch("app.services.llm_service.settings") as mock_settings:
            mock_settings.LLM_API_KEY = "sk-test"
            mock_settings.LLM_MODEL = "gpt-4o-mini"
            mock_settings.LLM_TEMPERATURE = 0.7
            mock_settings.LLM_MAX_TOKENS = 1024
            service = LLMService()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello from LLM"

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await service.complete("test prompt")
            assert result == "Hello from LLM"

    @pytest.mark.asyncio
    async def test_complete_json_parses_response(self):
        """Should parse JSON from LLM response."""
        with patch("app.services.llm_service.settings") as mock_settings:
            mock_settings.LLM_API_KEY = "sk-test"
            mock_settings.LLM_MODEL = "gpt-4o-mini"
            mock_settings.LLM_TEMPERATURE = 0.7
            mock_settings.LLM_MAX_TOKENS = 1024
            service = LLMService()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"category": "email/outlook", "confidence": 0.9}'

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await service.complete_json("classify this")
            assert result["category"] == "email/outlook"
            assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_complete_json_strips_code_fences(self):
        """Should strip markdown code fences from JSON response."""
        with patch("app.services.llm_service.settings") as mock_settings:
            mock_settings.LLM_API_KEY = "sk-test"
            mock_settings.LLM_MODEL = "gpt-4o-mini"
            mock_settings.LLM_TEMPERATURE = 0.7
            mock_settings.LLM_MAX_TOKENS = 1024
            service = LLMService()

        fenced_json = '```json\n{"key": "value"}\n```'
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = fenced_json

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await service.complete_json("test")
            assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_complete_json_returns_empty_on_invalid(self):
        """Should return empty dict when response is not valid JSON."""
        with patch("app.services.llm_service.settings") as mock_settings:
            mock_settings.LLM_API_KEY = "sk-test"
            mock_settings.LLM_MODEL = "gpt-4o-mini"
            mock_settings.LLM_TEMPERATURE = 0.7
            mock_settings.LLM_MAX_TOKENS = 1024
            service = LLMService()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not json at all"

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await service.complete_json("test")
            assert result == {}
