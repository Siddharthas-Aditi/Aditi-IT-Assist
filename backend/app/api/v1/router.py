"""API v1 router — aggregates all versioned endpoints."""

from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.health import router as health_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.knowledge_admin import router as knowledge_admin_router
from app.api.v1.remote_support import router as remote_support_router
from app.api.v1.tickets import router as tickets_router

api_router = APIRouter()

api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(chat_router, prefix="/chat", tags=["chat"])
api_router.include_router(tickets_router, prefix="/tickets", tags=["tickets"])
api_router.include_router(
    knowledge_admin_router, prefix="/knowledge/admin", tags=["knowledge-admin"]
)
api_router.include_router(knowledge_router, prefix="/knowledge", tags=["knowledge"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
api_router.include_router(remote_support_router, prefix="/remote-support", tags=["remote-support"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
