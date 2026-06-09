"""Admin endpoints for system management."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/stats")
async def get_system_stats() -> dict:
    """Get system statistics for admin dashboard.

    Returns metrics like total sessions, resolution rate,
    escalation rate, and active knowledge articles.
    """
    # TODO(team): Implement with real database aggregation
    return {
        "total_sessions": 0,
        "resolved_sessions": 0,
        "escalated_sessions": 0,
        "resolution_rate": 0.0,
        "average_confidence": 0.0,
        "total_knowledge_articles": 4,
        "active_tickets": 0,
    }


@router.get("/audit-log")
async def get_audit_log(
    limit: int = 50,
    offset: int = 0,
    event_type: str | None = None,
) -> dict:
    """Retrieve audit log entries."""
    # TODO(team): Implement with database query
    return {
        "events": [],
        "total": 0,
        "limit": limit,
        "offset": offset,
    }
