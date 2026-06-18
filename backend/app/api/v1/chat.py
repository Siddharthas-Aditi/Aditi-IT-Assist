"""Chat endpoints — main support conversation interface."""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import P
from app.models.auth import User
from app.schemas.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    LiveAgentRequest,
    LiveAgentResponse,
    SessionDetail,
    SessionSummary,
)
from app.services.agents.chat_service import ChatService, get_chat_service
from app.services.auth.dependencies import CurrentUser, require_permissions

router = APIRouter()

DBDep = Annotated[AsyncSession, Depends(get_db)]


def get_chat_service_dep(db: DBDep) -> ChatService:
    """DI wrapper that gives the chat service a DB-backed ticket service."""
    return get_chat_service(db)


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service_dep)]


@router.post("/message", response_model=ChatMessageResponse)
async def send_message(
    data: ChatMessageRequest,
    current_user: CurrentUser,
    service: ChatServiceDep,
) -> ChatMessageResponse:
    """Send a message to the AI support system.

    This endpoint:
    1. Creates or resumes a support session
    2. Invokes the LangGraph agent workflow
    3. Returns the AI response with metadata (incl. a created ticket, if the
       user confirmed escalation this turn).

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
        requester=current_user,
        include_debug=include_debug,
    )


@router.post("/request-live-agent", response_model=LiveAgentResponse)
async def request_live_agent(
    data: LiveAgentRequest,
    current_user: Annotated[User, Depends(require_permissions(P.CHAT_REQUEST_LIVE_AGENT))],
    service: ChatServiceDep,
) -> LiveAgentResponse:
    """Create (if needed) and queue a support ticket for a live IT specialist.

    This is the explicit confirmation behind the chat's "Connect with a
    specialist" action. It guarantees a ticket exists BEFORE the human handoff,
    and is idempotent per session (repeated calls reuse the same ticket).
    """
    try:
        message, ticket = await service.request_live_agent(data.session_id, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return LiveAgentResponse(session_id=data.session_id, message=message, ticket=ticket)


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
