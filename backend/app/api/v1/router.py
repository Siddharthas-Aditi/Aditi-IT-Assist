"""API v1 router — aggregates all versioned endpoints."""

from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.agent_ops import router as agent_ops_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.device_execution import router as device_execution_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.health import router as health_router
from app.api.v1.ingestion import router as ingestion_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.knowledge_admin import router as knowledge_admin_router
from app.api.v1.remote_support import router as remote_support_router
from app.api.v1.specialist_chat import (
    queue_router as specialist_queue_extras_router,
)
from app.api.v1.specialist_chat import router as specialist_chat_router
from app.api.v1.specialist_queue import router as specialist_queue_router
from app.api.v1.ticket_categories import router as ticket_categories_router
from app.api.v1.tickets import router as tickets_router

api_router = APIRouter()

api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(chat_router, prefix="/chat", tags=["chat"])
api_router.include_router(tickets_router, prefix="/tickets", tags=["tickets"])
api_router.include_router(
    ticket_categories_router, prefix="/ticket-categories", tags=["ticket-categories"]
)
api_router.include_router(
    knowledge_admin_router, prefix="/knowledge/admin", tags=["knowledge-admin"]
)
api_router.include_router(knowledge_router, prefix="/knowledge", tags=["knowledge"])
api_router.include_router(
    ingestion_router, prefix="/knowledge/ingest", tags=["knowledge-ingestion"]
)
api_router.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
api_router.include_router(remote_support_router, prefix="/remote-support", tags=["remote-support"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(feedback_router, prefix="/feedback", tags=["feedback"])
# Live IT-specialist features — queue (claim/release/resolve), 'My Assigned',
# and the human-to-human chat itself. See docs/architecture/live-specialist-chat.md
# ORDER MATTERS: the extras router owns the literal GET /specialist-queue/mine.
# It MUST be included before specialist_queue_router, whose GET /{ticket_id}
# would otherwise match "/mine" first and 422 on UUID parsing (the 'My Assigned'
# page bug). Regression: tests/api/test_specialist_queue_handoff.py
# ::TestMyAssignedRouteNotShadowed.
api_router.include_router(
    specialist_queue_extras_router,
    prefix="/specialist-queue",
    tags=["specialist-queue"],
)
api_router.include_router(
    specialist_queue_router,
    prefix="/specialist-queue",
    tags=["specialist-queue"],
)
api_router.include_router(
    specialist_chat_router,
    prefix="/specialist-chat",
    tags=["specialist-chat"],
)
# Agentic platform operability — status (MCP/RAG/flags), write-action approval
# queue, background-task monitor. See docs/architecture/agent-write-actions-and-tasks.md
api_router.include_router(agent_ops_router, prefix="/agent-ops", tags=["agent-ops"])
# Autonomous device execution — catalog, request-an-action (auto/approve/deny),
# and device-action approvals. See docs/architecture/device-execution.md
api_router.include_router(
    device_execution_router, prefix="/device-execution", tags=["device-execution"]
)
