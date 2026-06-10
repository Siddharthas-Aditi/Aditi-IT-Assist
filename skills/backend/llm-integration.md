# Skill: LLM Integration Patterns

> Standards for integrating LLM calls via LiteLLM in Aditi IT Assist.

---

## Pattern 1: LLM Service Abstraction

Never call LLM providers directly. Always use the service layer:

```python
from litellm import acompletion
from app.core.config import settings

class LLMService:
    """Abstraction over LLM providers via LiteLLM."""

    def __init__(self):
        self.model = settings.llm_model
        self.api_key = settings.llm_api_key
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens

    async def generate(
        self,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: int = 15,
    ) -> str:
        """Generate a completion. Returns content string."""
        response = await acompletion(
            model=self.model,
            messages=messages,
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
            api_key=self.api_key,
            timeout=timeout,
        )
        return response.choices[0].message.content

    async def generate_json(
        self,
        messages: list[dict],
        timeout: int = 15,
    ) -> dict:
        """Generate a JSON completion. Parses response."""
        content = await self.generate(
            messages=messages,
            temperature=0.1,  # Low temp for structured output
            timeout=timeout,
        )
        return json.loads(content)
```

---

## Pattern 2: Prompt Construction

```python
def build_classification_prompt(user_message: str, history: str = "") -> list[dict]:
    """Build messages list for LLM classification."""
    return [
        {
            "role": "system",
            "content": TRIAGE_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": f"User says: {user_message}\n\nHistory: {history}",
        },
    ]

# System prompts are constants, not dynamically generated
TRIAGE_SYSTEM_PROMPT = """You are an IT support triage agent for Aditi Consulting.
Classify the user's IT issue. Respond in JSON only.
..."""
```

---

## Pattern 3: Error Handling & Fallback

```python
async def classify_with_fallback(message: str, llm: LLMService) -> Classification:
    """Try LLM classification, fall back to keywords."""
    try:
        result = await llm.generate_json(
            messages=build_classification_prompt(message),
            timeout=10,
        )
        return Classification(**result)
    except asyncio.TimeoutError:
        logger.warning("llm.timeout", operation="classify")
        return keyword_fallback(message)
    except json.JSONDecodeError:
        logger.warning("llm.invalid_json", operation="classify")
        return keyword_fallback(message)
    except Exception as e:
        logger.error("llm.error", operation="classify", error=str(e))
        return keyword_fallback(message)
```

---

## Pattern 4: Token Management

```python
def truncate_context(messages: list, max_tokens: int = 3000) -> list:
    """Truncate message history to fit token budget."""
    # Keep system message + last N messages
    if len(messages) <= 3:
        return messages

    system = messages[0]
    recent = messages[-4:]  # Last 4 messages (2 turns)
    return [system] + recent
```

---

## Anti-Patterns

| Don't | Do Instead |
|-------|-----------|
| `import openai; openai.chat(...)` | Use `LLMService.generate()` |
| Hardcode model names in nodes | Read from `settings.llm_model` |
| Ignore timeouts | Always set explicit timeout (10-15s) |
| Parse LLM output without validation | Use `try/except json.JSONDecodeError` |
| Trust LLM output blindly | Validate against expected schema |

---

## Configuration

```bash
# .env
LLM_PROVIDER=openai          # openai | azure | anthropic
LLM_MODEL=gpt-4o-mini        # Model identifier
LLM_API_KEY=sk-...           # Provider API key
LLM_TEMPERATURE=0.3          # Default temperature
LLM_MAX_TOKENS=4096          # Max response tokens
```
