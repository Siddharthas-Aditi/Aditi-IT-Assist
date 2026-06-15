"""Health check endpoints — basic, readiness, and LLM/embedding smoke tests."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings
from app.services.llm_service import get_llm_service

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str
    service: str
    version: str


@router.get("", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check application health status."""
    return HealthResponse(
        status="healthy",
        service="aditi-it-assist",
        version="0.1.0",
    )


@router.get("/ready")
async def readiness_check() -> dict[str, str]:
    """Check if application is ready to serve traffic."""
    return {"status": "ready"}


@router.get("/llm")
async def llm_health_check() -> dict:
    """Smoke-test the configured LLM provider.

    Sends a minimal prompt and returns the provider, model, and a trimmed
    echo of the response. Returns ``status=unavailable`` (not an HTTP error)
    when no API key is configured so dev environments never break.
    """
    svc = get_llm_service()
    if not svc.is_available:
        return {
            "status": "unavailable",
            "provider": settings.LLM_PROVIDER,
            "model": settings.effective_llm_model,
            "reason": "API key not configured",
        }
    try:
        reply = await svc.complete(
            "Reply with exactly one word: ready",
            system_prompt="You are a health-check assistant.",
            max_tokens=10,
        )
        return {
            "status": "ok",
            "provider": settings.LLM_PROVIDER,
            "model": settings.effective_llm_model,
            "endpoint": settings.AZURE_OPENAI_ENDPOINT if settings.is_azure else "openai",
            "reply": reply.strip(),
        }
    except Exception as exc:
        return {
            "status": "error",
            "provider": settings.LLM_PROVIDER,
            "model": settings.effective_llm_model,
            "error": str(exc),
        }


@router.get("/embedding")
async def embedding_health_check() -> dict:
    """Smoke-test the embedding model by embedding a single phrase."""
    from app.services.knowledge.indexing import get_embedding_client

    client = get_embedding_client()
    if not client.available:
        return {
            "status": "unavailable",
            "model": settings.effective_embedding_model,
            "reason": "Embedding client not configured",
        }
    try:
        vectors = await client.embed(["IT support health check"])
        if vectors:
            return {
                "status": "ok",
                "model": settings.effective_embedding_model,
                "dimensions": len(vectors[0]),
            }
        return {"status": "no_output", "model": settings.effective_embedding_model}
    except Exception as exc:
        return {
            "status": "error",
            "model": settings.effective_embedding_model,
            "error": str(exc),
        }

