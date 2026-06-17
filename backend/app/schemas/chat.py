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


class QuickReplyOption(BaseModel):
    """A quick-reply option for disambiguation chips in the frontend."""

    label: str
    value: str


class ChatDebugInfo(BaseModel):
    """Developer-facing trace of how a response was produced.

    Only populated when the caller is an IT/admin role (see ChatService). Lets
    the admin debug view explain detected system/subtype, grounding decisions,
    confidence components, and loop/escalation triggers.
    """

    normalized_system: str | None = None
    issue_subtype: str | None = None
    subtype_confidence: float = 0.0
    conversation_phase: str | None = None
    loop_counter: int = 0
    suggested_steps: list[str] = []
    failed_steps: list[str] = []
    confidence_breakdown: dict | None = None
    retrieval_trace: dict | None = None
    escalation_reason: str | None = None


class ChatMessageResponse(BaseModel):
    """AI assistant response with metadata."""

    session_id: str
    message_id: str
    content: str
    role: str = "assistant"
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    issue_category: str | None = None
    issue_subtype: str | None = None
    resolution_steps: list[ResolutionStepSchema] = []
    requires_escalation: bool = False
    follow_up_question: str | None = None
    quick_replies: list[QuickReplyOption] | None = None
    conversation_phase: str | None = None
    resolved: bool = False
    debug: ChatDebugInfo | None = None


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

