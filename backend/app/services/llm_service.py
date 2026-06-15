"""LLM service — provider-agnostic interface for language model calls.

Uses LiteLLM under the hood for multi-provider support (OpenAI, Azure, Anthropic, etc.).
All agent nodes should call this service rather than making direct LLM API calls.
"""

import json
from typing import Any

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLMService:
    """Provider-agnostic LLM invocation service.

    Wraps LiteLLM to provide:
    - Consistent interface across providers
    - Retry logic with exponential backoff
    - Structured output parsing
    - Token usage tracking
    - Fallback behavior when LLM is unavailable
    """

    def __init__(self) -> None:
        self.model = settings.effective_llm_model
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS
        self._available = settings.llm_is_configured
        self._ssl_verify = settings.AZURE_OPENAI_VERIFY_SSL
        # Apply global LiteLLM SSL setting at init time so all internal
        # httpx clients created by LiteLLM pick it up automatically.
        if not self._ssl_verify:
            import litellm as _litellm  # noqa: PLC0415
            _litellm.ssl_verify = False

    @property
    def is_available(self) -> bool:
        """Check if the LLM service is configured and available."""
        return self._available

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _complete_internal(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Internal retry-wrapped LLM call (assumes is_available is True)."""
        import litellm

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        logger.debug(
            "llm_request",
            model=self.model,
            provider=settings.LLM_PROVIDER,
            prompt_length=len(prompt),
        )

        response = await litellm.acompletion(
            model=self.model,
            messages=messages,
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
            api_key=settings.effective_llm_api_key,
            # Azure-specific routing — ignored by LiteLLM for non-azure providers
            **(
                {
                    "api_base": settings.AZURE_OPENAI_ENDPOINT,
                    "api_version": settings.AZURE_OPENAI_API_VERSION,
                }
                if settings.is_azure
                else {}
            ),
        )

        content = response.choices[0].message.content or ""
        logger.debug(
            "llm_response",
            model=self.model,
            response_length=len(content),
            usage=getattr(response, "usage", None),
        )
        return content

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate a completion from the LLM.

        Args:
            prompt: The user/task prompt
            system_prompt: Optional system message for context
            temperature: Override default temperature
            max_tokens: Override default max tokens

        Returns:
            The LLM's response text

        Raises:
            RuntimeError: If the LLM service is not configured
        """
        if not self.is_available:
            raise RuntimeError("LLM service not configured — set LLM_API_KEY in environment")

        return await self._complete_internal(
            prompt, system_prompt=system_prompt, temperature=temperature, max_tokens=max_tokens
        )

    async def complete_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Generate a JSON-structured response from the LLM.

        Attempts to parse the LLM response as JSON. Falls back to
        an empty dict on parse failure.

        Returns:
            Parsed JSON dict from the LLM response
        """
        raw = await self.complete(prompt, system_prompt=system_prompt, temperature=0.1)

        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("llm_json_parse_failed", raw_response=raw[:200])
            return {}


# Singleton instance — used via dependency injection
_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    """Get or create the LLM service singleton."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
