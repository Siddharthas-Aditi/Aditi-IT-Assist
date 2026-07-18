"""Ticket management endpoints — enterprise helpdesk lifecycle."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import P
from app.models.auth import User
from app.services.auth.dependencies import CurrentUser, ITAgentUser, require_permissions
from app.services.ticket_service import TicketService

router = APIRouter()

ReopenUser = Annotated[User, Depends(require_permissions(P.TICKET_REOPEN))]


# ─────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────


class TicketCreateRequest(BaseModel):
    """Create ticket request."""

    title: str
    description: str
    priority: str = "medium"
    category: str | None = None
    subcategory: str | None = None
    source: str = "manual"


class TicketResponse(BaseModel):
    """Ticket response for API."""

    id: str
    ticket_number: str
    title: str
    description: str
    status: str
    priority: str
    category: str | None = None
    requester_id: str
    assigned_to: str | None = None
    created_at: str
    sla_response_target: str | None = None
    sla_resolution_target: str | None = None
    ai_summary: str | None = None
    resolution_notes: str | None = None


class TicketListResponse(BaseModel):
    """Paginated ticket list."""

    tickets: list[TicketResponse]
    total: int
    limit: int
    offset: int


class TicketCommentRequest(BaseModel):
    """Add comment to ticket."""

    content: str
    is_internal: bool = False


class TicketAssignRequest(BaseModel):
    """Assign ticket to agent."""

    agent_id: str


class TicketStatusRequest(BaseModel):
    """Update ticket status."""

    status: str
    comment: str | None = None


class TicketReopenRequest(BaseModel):
    """Reopen a resolved/closed ticket."""

    comment: str | None = None


# ─────────────────────────────────────────────────────────────────────
# Employee Endpoints (own tickets only)
# ─────────────────────────────────────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_ticket(
    data: TicketCreateRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketResponse:
    """Create a new support ticket."""
    service = TicketService(db)
    ticket = await service.create_ticket(
        requester=current_user,
        title=data.title,
        description=data.description,
        priority=data.priority,
        category=data.category,
        subcategory=data.subcategory,
        source=data.source,
    )
    return _ticket_to_response(ticket)


@router.get("/my")
async def list_my_tickets(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    ticket_status: str | None = Query(None, alias="status"),
    limit: int = 20,
    offset: int = 0,
) -> TicketListResponse:
    """List current user's own tickets."""
    service = TicketService(db)
    tickets = await service.list_tickets_for_employee(
        employee=current_user,
        status=ticket_status,
        limit=limit,
        offset=offset,
    )
    return TicketListResponse(
        tickets=[_ticket_to_response(t) for t in tickets],
        total=len(tickets),
        limit=limit,
        offset=offset,
    )


@router.get("/my/{ticket_id}")
async def get_my_ticket(
    ticket_id: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Get ticket details (employee view — own ticket only)."""
    service = TicketService(db)
    result = await service.get_ticket_for_employee(uuid.UUID(ticket_id), current_user)
    if not result:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {
        "ticket": _ticket_to_response(result["ticket"]),
        "comments": [
            {"id": str(c.id), "content": c.content, "created_at": c.created_at.isoformat()}
            for c in result["comments"]
        ],
        "events": [
            {
                "type": e.event_type,
                "description": e.description,
                "created_at": e.created_at.isoformat(),
            }
            for e in result["events"]
        ],
    }


# ─────────────────────────────────────────────────────────────────────
# IT Agent Endpoints
# ─────────────────────────────────────────────────────────────────────


@router.get("/queue")
async def get_ticket_queue(
    agent_user: ITAgentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    ticket_status: str | None = Query(None, alias="status"),
    priority: str | None = None,
    assigned_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> TicketListResponse:
    """Get ticket queue for IT agents."""
    service = TicketService(db)
    tickets = await service.list_tickets_for_agent(
        agent=agent_user,
        assigned_only=assigned_only,
        status=ticket_status,
        priority=priority,
        limit=limit,
        offset=offset,
    )
    return TicketListResponse(
        tickets=[_ticket_to_response(t) for t in tickets],
        total=len(tickets),
        limit=limit,
        offset=offset,
    )


@router.get("/queue/summary")
async def get_queue_summary(
    agent_user: ITAgentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Get ticket queue summary counts."""
    service = TicketService(db)
    return await service.get_queue_summary()


@router.get("/{ticket_id}")
async def get_ticket_detail(
    ticket_id: str,
    agent_user: ITAgentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Get full ticket detail for IT staff (includes internal notes + events)."""
    service = TicketService(db)
    result = await service.get_ticket_for_agent(uuid.UUID(ticket_id))
    if not result:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {
        "ticket": _ticket_to_response(result["ticket"]),
        "comments": [
            {
                "id": str(c.id),
                "content": c.content,
                "is_internal": c.is_internal,
                "author_id": str(c.author_id),
                "created_at": c.created_at.isoformat(),
            }
            for c in result["comments"]
        ],
        "events": [
            {
                "type": e.event_type,
                "description": e.description,
                "created_at": e.created_at.isoformat(),
            }
            for e in result["events"]
        ],
    }


@router.post("/{ticket_id}/assign")
async def assign_ticket(
    ticket_id: str,
    data: TicketAssignRequest,
    agent_user: ITAgentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketResponse:
    """Assign ticket to an IT agent."""
    service = TicketService(db)
    ticket = await service.assign_ticket(
        uuid.UUID(ticket_id),
        uuid.UUID(data.agent_id),
        agent_user,
    )
    return _ticket_to_response(ticket)


@router.post("/{ticket_id}/status")
async def update_ticket_status(
    ticket_id: str,
    data: TicketStatusRequest,
    agent_user: ITAgentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketResponse:
    """Update ticket status."""
    service = TicketService(db)
    ticket = await service.update_status(
        uuid.UUID(ticket_id),
        data.status,
        agent_user,
        comment=data.comment,
    )
    return _ticket_to_response(ticket)


@router.post("/{ticket_id}/reopen")
async def reopen_ticket(
    ticket_id: str,
    reopen_user: ReopenUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    data: TicketReopenRequest | None = None,
) -> TicketResponse:
    """Reopen a resolved/closed ticket back to active work."""
    service = TicketService(db)
    try:
        ticket = await service.reopen_ticket(
            uuid.UUID(ticket_id), reopen_user, comment=(data.comment if data else None)
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _ticket_to_response(ticket)


@router.post("/{ticket_id}/comments")
async def add_comment(
    ticket_id: str,
    data: TicketCommentRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Add a comment to a ticket."""
    service = TicketService(db)
    comment = await service.add_comment(
        uuid.UUID(ticket_id),
        current_user,
        data.content,
        is_internal=data.is_internal,
    )
    return {
        "id": str(comment.id),
        "content": comment.content,
        "is_internal": comment.is_internal,
        "created_at": comment.created_at.isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _ticket_to_response(ticket) -> TicketResponse:
    """Convert ticket model to response."""
    return TicketResponse(
        id=str(ticket.id),
        ticket_number=ticket.ticket_number,
        title=ticket.title,
        description=ticket.description,
        status=ticket.status,
        priority=ticket.priority,
        category=ticket.category,
        requester_id=str(ticket.requester_id),
        assigned_to=str(ticket.assigned_to) if ticket.assigned_to else None,
        created_at=ticket.created_at.isoformat(),
        sla_response_target=ticket.sla_response_target.isoformat()
        if ticket.sla_response_target
        else None,
        sla_resolution_target=ticket.sla_resolution_target.isoformat()
        if ticket.sla_resolution_target
        else None,
        ai_summary=ticket.ai_summary,
        resolution_notes=ticket.resolution_notes,
    )
