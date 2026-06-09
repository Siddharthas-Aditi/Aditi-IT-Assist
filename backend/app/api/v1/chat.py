"""Chat endpoints — main support conversation interface."""

from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


class ChatMessageRequest(BaseModel):
    """Request to send a message in a support session."""

    session_id: str | None = None
    message: str = Field(..., min_length=1, max_length=5000)


class ResolutionStep(BaseModel):
    """A single troubleshooting step."""

    step_number: int
    instruction: str
    details: str | None = None


class ChatMessageResponse(BaseModel):
    """Response from the AI support system."""

    session_id: str
    message_id: str
    content: str
    role: str = "assistant"
    confidence_score: float = 0.0
    issue_category: str | None = None
    resolution_steps: list[ResolutionStep] = []
    requires_escalation: bool = False
    follow_up_question: str | None = None


class SessionResponse(BaseModel):
    """Support session details."""

    session_id: str
    status: str
    issue_category: str | None = None
    created_at: str


@router.post("/message", response_model=ChatMessageResponse)
async def send_message(data: ChatMessageRequest) -> ChatMessageResponse:
    """Send a message to the AI support system.

    This endpoint:
    1. Creates or resumes a support session
    2. Invokes the LangGraph agent workflow
    3. Returns the AI response with metadata
    """
    # Create new session if not provided
    session_id = data.session_id or str(uuid4())

    # TODO(team): Invoke LangGraph workflow via AgentService
    # For now, return a demonstration response
    from app.services.agents.chat_service import ChatService

    service = ChatService()
    response = await service.process_message(
        session_id=session_id,
        user_message=data.message,
    )
    return response


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions() -> list[SessionResponse]:
    """List all support sessions for the current user."""
    # TODO(team): Implement with database query filtered by user
    return []


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    """Get full session details including message history."""
    # TODO(team): Implement with database query
    return {"session_id": session_id, "messages": [], "status": "active"}
