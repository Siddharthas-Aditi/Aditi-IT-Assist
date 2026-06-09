"""Ticket management endpoints."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter

from app.schemas.ticket import TicketCreateRequest, TicketListResponse, TicketResponse

router = APIRouter()


@router.post("", response_model=TicketResponse, status_code=201)
async def create_ticket(data: TicketCreateRequest) -> TicketResponse:
    """Create a new support ticket.

    Tickets are typically created by the escalation agent when
    AI cannot resolve an issue and no human agent is available.
    """
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


@router.get("", response_model=TicketListResponse)
async def list_tickets(
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> TicketListResponse:
    """List tickets for the current user with optional status filter."""
    # TODO(team): Implement with database query
    return TicketListResponse(tickets=[], total=0, limit=limit, offset=offset)


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: str) -> TicketResponse:
    """Get ticket details by ID."""
    # TODO(team): Implement with database query
    return TicketResponse(
        ticket_id=ticket_id,
        title="Sample Ticket",
        description="Placeholder ticket",
        priority="medium",
        status="open",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
