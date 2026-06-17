"""Chat endpoints — main support conversation interface."""

from uuid import uuid4

from fastapi import APIRouter, Depends

from app.schemas.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    SessionDetail,
    SessionSummary,
)
from app.services.agents.chat_service import ChatService, get_chat_service
from app.services.auth.dependencies import CurrentUser

router = APIRouter()


@router.post("/message", response_model=ChatMessageResponse)
async def send_message(
    data: ChatMessageRequest,
    current_user: CurrentUser,
    service: ChatService = Depends(get_chat_service),  # noqa: B008
) -> ChatMessageResponse:
    """Send a message to the AI support system.

    This endpoint:
    1. Creates or resumes a support session
    2. Invokes the LangGraph agent workflow
    3. Returns the AI response with metadata

    Requires: authenticated user (any role).
    """
    session_id = data.session_id or str(uuid4())

    # Developer trace is attached only for IT/admin roles — never for employees,
    # preserving data isolation (internal grounding/debug stays internal).
    staff_roles = {"it_agent", "it_lead", "it_admin", "security_auditor"}
    include_debug = bool(staff_roles.intersection(getattr(current_user, "role_names", []) or []))

    return await service.process_message(
        session_id=session_id,
        user_message=data.message,
        user_id=str(current_user.id),
        user_name=getattr(current_user, "full_name", None),
        user_email=getattr(current_user, "email", None),
        include_debug=include_debug,
    )


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(current_user: CurrentUser) -> list[SessionSummary]:
    """List all support sessions for the current user."""
    # TODO(team): Implement with database query filtered by user
    return []


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str, current_user: CurrentUser) -> SessionDetail:
    """Get full session details including message history."""
    # TODO(team): Implement with database query
    return SessionDetail(
        session_id=session_id,
        status="active",
        messages=[],
    )
