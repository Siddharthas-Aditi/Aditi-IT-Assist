"""Health check endpoints — basic, readiness, and LLM/embedding smoke tests."""

from fastapi import APIRouter, Response
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
async def readiness_check(response: Response) -> dict[str, object]:
    """Readiness probe — verifies the dependencies traffic actually needs.

    * Database: ``SELECT 1`` on the async engine.
    * Redis: ``PING`` (denylist + rate limiting live there). Redis being
      down degrades those features (fail-open) but doesn't stop serving,
      so it is reported but only the DB gates readiness.

    Returns 503 (so load balancers stop routing) when the DB check fails.
    """
    checks: dict[str, str] = {}

    try:
        from sqlalchemy import text

        from app.core.database import engine

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {type(exc).__name__}"

    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        try:
            await client.ping()
            checks["redis"] = "ok"
        finally:
            await client.aclose()
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {type(exc).__name__}"

    ready = checks["database"] == "ok"
    if not ready:
        response.status_code = 503
    return {"status": "ready" if ready else "not_ready", "checks": checks}


@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics exposition (gated by METRICS_ENABLED).

    Deployment note: this path must not be exposed publicly — nginx only
    proxies it for internal networks (see frontend/nginx.conf).
    """
    if not settings.METRICS_ENABLED:
        return Response(status_code=404)
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


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
