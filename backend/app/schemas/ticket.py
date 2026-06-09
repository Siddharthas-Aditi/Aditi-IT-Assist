"""Ticket-related schemas."""

from pydantic import BaseModel, Field


class TicketCreateRequest(BaseModel):
    """Request to create a support ticket."""

    session_id: str | None = None
    title: str = Field(..., min_length=5, max_length=500)
    description: str = Field(..., min_length=10)
    priority: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    category: str | None = None


class TicketResponse(BaseModel):
    """Support ticket response."""

    ticket_id: str
    title: str
    description: str
    priority: str
    status: str
    category: str | None = None
    assigned_to: str | None = None
    created_at: str


class TicketListResponse(BaseModel):
    """Paginated ticket list."""

    tickets: list[TicketResponse]
    total: int
    limit: int
    offset: int
