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
    # Agent-activity surfacing (operability): which specialist the supervisor
    # would route to (shadow mode), the retrieval engine used, and the grounded
    # citations behind the answer.
    routed_specialist: str | None = None
    retrieval_source: str | None = None  # db_hybrid | db_keyword | yaml_fallback
    citations: list[dict] = []


class TicketRef(BaseModel):
    """Reference to a persisted support ticket, surfaced to the chat UI.

    Present only once a real ticket has been created (on explicit user
    confirmation / live-agent handoff) — never for a mere escalation offer.
    """

    ticket_id: str
    ticket_number: str
    status: str
    priority: str
    live_agent_requested: bool = False


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
    # True when the agent has OFFERED to raise a ticket + connect a human but
    # is waiting for the user to confirm (drives the "Connect" CTA). Distinct
    # from `ticket`, which is only set once a ticket actually exists.
    escalation_offered: bool = False
    ticket: TicketRef | None = None
    follow_up_question: str | None = None
    quick_replies: list[QuickReplyOption] | None = None
    conversation_phase: str | None = None
    resolved: bool = False
    debug: ChatDebugInfo | None = None


class LiveAgentRequest(BaseModel):
    """Employee request to create a ticket and hand off to a live IT agent."""

    session_id: str


class LiveAgentResponse(BaseModel):
    """Result of a live-agent handoff: the ticket that was created/queued.

    ``ticket`` is None when the handoff was gated by the no-direct-connect
    policy (the user must describe their issue first); the ``message`` then
    carries the request for a problem description.
    """

    session_id: str
    message: str
    ticket: TicketRef | None = None


class CancelWaitingRequest(BaseModel):
    """Employee cancels waiting for a live specialist."""

    session_id: str


class CancelWaitingResponse(BaseModel):
    """Acknowledgement that the waiting state was cleared."""

    session_id: str
    message: str
    cancelled: bool = True


class WaitingStatusResponse(BaseModel):
    """Status of the employee's live-agent wait queue position."""

    session_id: str
    waiting: bool
    ticket_number: str | None = None
    waited_seconds: int = 0
    specialist_available: bool = True
    fallback_message: str | None = None


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
