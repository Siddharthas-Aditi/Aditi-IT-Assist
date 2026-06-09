"""Ticket management endpoints."""

from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


class TicketCreateRequest(BaseModel):
    """Request to create a support ticket."""

    session_id: str | None = None
    title: str = Field(..., min_length=5, max_length=500)
    description: str = Field(..., min_length=10)
    priority: str = "medium"
    category: str | None = None


class TicketResponse(BaseModel):
    """Support ticket response."""

    ticket_id: str
    title: str
    description: str
    priority: str
    status: str
    category: str | None = None
    created_at: str


@router.post("", response_model=TicketResponse)
async def create_ticket(data: TicketCreateRequest) -> TicketResponse:
    """Create a new support ticket.

    Tickets are typically created by the escalation agent when
    AI cannot resolve an issue and no human agent is available.
    """
    from datetime import datetime, timezone

    ticket_id = str(uuid4())
    return TicketResponse(
        ticket_id=ticket_id,
        title=data.title,
        description=data.description,
        priority=data.priority,
        status="open",
        category=data.category,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("", response_model=list[TicketResponse])
async def list_tickets() -> list[TicketResponse]:
    """List tickets for the current user."""
    # TODO(team): Implement with database query
    return []


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: str) -> TicketResponse:
    """Get ticket details by ID."""
    # TODO(team): Implement with database query
    from datetime import datetime, timezone

    return TicketResponse(
        ticket_id=ticket_id,
        title="Sample Ticket",
        description="Placeholder ticket",
        priority="medium",
        status="open",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
