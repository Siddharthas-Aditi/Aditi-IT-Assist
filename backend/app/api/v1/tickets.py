"""Ticket management endpoints — enterprise helpdesk lifecycle."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.auth.dependencies import CurrentUser, ITAgentUser
from app.services.ticket_category_validation import CategoryCascadeError
from app.services.ticket_service import TicketService

router = APIRouter()


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
    source: str | None = None
    requester_id: str
    assigned_to: str | None = None
    created_at: str
    sla_response_target: str | None = None
    sla_resolution_target: str | None = None
    ai_summary: str | None = None
    resolution_notes: str | None = None
    subcategory: str | None = None
    item: str | None = None
    ticket_type: str | None = None
    urgency: str | None = None
    impact: str | None = None
    close_notes: str | None = None
    closed_by: str | None = None
    closed_at: str | None = None
    resolved_at: str | None = None


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


class TicketUpdateRequest(BaseModel):
    """Partial update of ticket properties (IT staff)."""

    priority: str | None = None
    urgency: str | None = None
    impact: str | None = None
    ticket_type: str | None = None
    category: str | None = None
    subcategory: str | None = None
    item: str | None = None
    resolution_notes: str | None = None
    status: str | None = None


class TicketCloseRequest(BaseModel):
    """Close a ticket with a mandatory resolution form (IT staff only).

    Employees cannot close tickets — only IT staff can mark a ticket closed
    after verifying the issue is resolved.
    """

    resolution_notes: str
    category: str
    subcategory: str
    item: str
    close_notes: str | None = None


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
    ticket_status: str | None = Query(None, alias="status", description="Comma-separated statuses"),
    priority: str | None = Query(None, description="Comma-separated priorities"),
    category: str | None = None,
    source: str | None = None,
    search: str | None = None,
    date_from: datetime | None = Query(None, description="ISO 8601 start date (inclusive)"),
    date_to: datetime | None = Query(None, description="ISO 8601 end date (inclusive)"),
    assigned_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TicketListResponse:
    """Get ticket queue for IT agents with rich filtering and accurate pagination."""
    service = TicketService(db)
    tickets, total = await service.list_tickets_for_agent(
        agent=agent_user,
        assigned_only=assigned_only,
        status=ticket_status,
        priority=priority,
        category=category,
        source=source,
        search=search,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return TicketListResponse(
        tickets=[_ticket_to_response(t) for t in tickets],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/export")
async def export_tickets_csv(
    agent_user: ITAgentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    ticket_status: str | None = Query(None, alias="status"),
    priority: str | None = None,
    category: str | None = None,
    source: str | None = None,
    search: str | None = None,
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    assigned_only: bool = False,
) -> Response:
    """Download all matching tickets as a CSV file (no pagination limit)."""
    service = TicketService(db)
    csv_content = await service.export_tickets_csv(
        agent=agent_user,
        assigned_only=assigned_only,
        status=ticket_status,
        priority=priority,
        category=category,
        source=source,
        search=search,
        date_from=date_from,
        date_to=date_to,
    )
    filename = f"tickets_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
    try:
        ticket = await service.update_status(
            uuid.UUID(ticket_id),
            data.status,
            agent_user,
            comment=data.comment,
        )
    except ValueError as exc:
        if "Use POST" in str(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _ticket_to_response(ticket)


@router.post("/{ticket_id}/close")
async def close_ticket(
    ticket_id: str,
    data: TicketCloseRequest,
    agent_user: ITAgentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketResponse:
    """Close ticket with mandatory resolution form (IT staff only)."""
    service = TicketService(db)
    try:
        ticket = await service.close_ticket(
            uuid.UUID(ticket_id),
            agent_user,
            resolution_notes=data.resolution_notes,
            category=data.category,
            subcategory=data.subcategory,
            item=data.item,
            close_notes=data.close_notes,
        )
        await db.commit()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CategoryCascadeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        msg = str(exc)
        if msg == "Ticket not found":
            code = 404
        elif "already closed" in msg or "Use POST" in msg:
            code = 409
        else:
            code = 400
        raise HTTPException(status_code=code, detail=msg) from exc
    return _ticket_to_response(ticket)


@router.patch("/{ticket_id}")
async def patch_ticket(
    ticket_id: str,
    data: TicketUpdateRequest,
    agent_user: ITAgentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TicketResponse:
    """Partial property update (IT staff). Cannot close via this endpoint."""
    service = TicketService(db)
    try:
        ticket = await service.update_ticket_properties(
            uuid.UUID(ticket_id),
            agent_user,
            priority=data.priority,
            urgency=data.urgency,
            impact=data.impact,
            ticket_type=data.ticket_type,
            category=data.category,
            subcategory=data.subcategory,
            item=data.item,
            resolution_notes=data.resolution_notes,
            status=data.status,
        )
        await db.commit()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CategoryCascadeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        msg = str(exc)
        if msg == "Ticket not found":
            code = 404
        elif "Use POST" in msg:
            code = 409
        else:
            code = 400
        raise HTTPException(status_code=code, detail=msg) from exc
    return _ticket_to_response(ticket)


@router.post("/{ticket_id}/reopen")
async def reopen_ticket(
    ticket_id: str,
    agent_user: ITAgentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    data: TicketReopenRequest | None = None,
) -> TicketResponse:
    """Reopen a resolved/closed ticket back to active work (IT staff only)."""
    service = TicketService(db)
    try:
        ticket = await service.reopen_ticket(
            uuid.UUID(ticket_id), agent_user, comment=(data.comment if data else None)
        )
    except ValueError as exc:
        if str(exc) == "Ticket not found":
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _ticket_to_response(ticket)


@router.post("/{ticket_id}/comments")
async def add_comment(
    ticket_id: str,
    data: TicketCommentRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Add a comment to a ticket.

    Employees may only comment on their own tickets (public notes only).
    """
    service = TicketService(db)
    try:
        comment = await service.add_comment(
            uuid.UUID(ticket_id),
            current_user,
            data.content,
            is_internal=data.is_internal,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
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
        source=getattr(ticket, "source", None),
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
        subcategory=ticket.subcategory,
        item=ticket.item,
        ticket_type=ticket.ticket_type,
        urgency=ticket.urgency,
        impact=ticket.impact,
        close_notes=ticket.close_notes,
        closed_by=str(ticket.closed_by) if ticket.closed_by else None,
        closed_at=ticket.closed_at.isoformat() if ticket.closed_at else None,
        resolved_at=ticket.resolved_at.isoformat() if ticket.resolved_at else None,
    )
