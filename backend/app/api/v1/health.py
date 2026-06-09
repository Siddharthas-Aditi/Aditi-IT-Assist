"""Health check endpoint."""

from fastapi import APIRouter
from pydantic import BaseModel

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
    """Check if application is ready to serve traffic.

    Future: check database and Redis connectivity.
    """
    # TODO(team): Add actual database and Redis connectivity checks
    return {"status": "ready"}
