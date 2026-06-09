"""Chat-related request/response schemas."""

from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    """Incoming chat message from the user."""

    session_id: str | None = None
    message: str = Field(..., min_length=1, max_length=5000, description="User's message text")


class ResolutionStepSchema(BaseModel):
    """A single troubleshooting step returned to the user."""

    step_number: int
    instruction: str
    details: str | None = None


class ChatMessageResponse(BaseModel):
    """AI assistant response with metadata."""

    session_id: str
    message_id: str
    content: str
    role: str = "assistant"
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    issue_category: str | None = None
    resolution_steps: list[ResolutionStepSchema] = []
    requires_escalation: bool = False
    follow_up_question: str | None = None


class SessionSummary(BaseModel):
    """Lightweight session listing schema."""

    session_id: str
    status: str
    issue_category: str | None = None
    created_at: str


class SessionDetail(BaseModel):
    """Full session detail with messages."""

    session_id: str
    status: str
    issue_category: str | None = None
    messages: list[dict] = []
    confidence_score: float = 0.0
    created_at: str
