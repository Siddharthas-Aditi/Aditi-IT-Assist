"""IT Specialist queue API.

Routes:
  GET    /specialist-queue              — list queue entries (filtered)
  GET    /specialist-queue/{ticket_id}  — full handoff package
  POST   /specialist-queue/claim        — atomic claim
  POST   /specialist-queue/release      — release a claim
  POST   /specialist-queue/resolve      — mark resolved + (optionally) propose KB candidate

All routes require ``ticket:claim_chat`` (typically held by ``it_agent``,
``it_lead``, ``it_admin``). The service layer enforces ownership semantics
(only the claimer can release or resolve a ticket they hold).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import P
from app.models.auth import User
from app.schemas.specialist_queue import (
    ClaimRequest,
    ClaimResponse,
    HandoffPackage,
    QueueListResponse,
    ResolveRequest,
    ResolveResponse,
)
from app.services.auth.dependencies import require_permissions
from app.services.specialist_queue_service import SpecialistQueueService

router = APIRouter()

DBDep = Annotated[AsyncSession, Depends(get_db)]


def _queue_service(db: DBDep) -> SpecialistQueueService:
    return SpecialistQueueService(db)


QueueDep = Annotated[SpecialistQueueService, Depends(_queue_service)]
# Listing the queue is broader than claiming/resolving — separate scopes so
# read-only roles (e.g. it_lead viewing without taking work) don't need the
# claim permission. The route-level dep here uses claim because every queue
# endpoint also exposes write actions.
ClaimerDep = Annotated[User, Depends(require_permissions(P.SPECIALIST_QUEUE_CLAIM))]
ResolverDep = Annotated[User, Depends(require_permissions(P.SPECIALIST_QUEUE_RESOLVE))]
QueueViewerDep = Annotated[User, Depends(require_permissions(P.SPECIALIST_QUEUE_VIEW))]


@router.get("", response_model=QueueListResponse)
async def list_queue(
    service: QueueDep,
    current_user: QueueViewerDep,
    only_unclaimed: bool = Query(False, description="Hide tickets already claimed by anyone."),
    include_mine: bool = Query(True, description="Include tickets already assigned to me."),
    limit: int = Query(50, ge=1, le=200),
) -> QueueListResponse:
    """List queue entries, ordered by priority then age (FIFO within tier)."""
    entries = await service.list_queue(
        only_unclaimed=only_unclaimed,
        for_user_id=current_user.id if include_mine else None,
        limit=limit,
    )
    return QueueListResponse(total=len(entries), entries=entries)


@router.get("/{ticket_id}", response_model=HandoffPackage)
async def get_handoff_package(
    ticket_id: uuid.UUID,
    service: QueueDep,
    current_user: QueueViewerDep,
    db: DBDep,
) -> HandoffPackage:
    """Return the full typed handoff package for a single queue entry."""
    from app.models.ticket import Ticket  # local import to avoid cycle in routers

    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    # Pull session state if the chat service still holds it.
    from app.services.agents import chat_service as cs_mod
    session_state = (
        cs_mod._sessions.get(str(ticket.session_id))
        if ticket.session_id else None
    )
    return await service.build_handoff_package(ticket, session_state=session_state)


@router.post("/claim", response_model=ClaimResponse)
async def claim_ticket(
    body: ClaimRequest,
    service: QueueDep,
    current_user: ClaimerDep,
    db: DBDep,
) -> ClaimResponse:
    """Atomically claim a queue entry for this specialist.

    Returns the full handoff package on success so the UI can pop the
    Context pane immediately.
    """
    try:
        ticket = await service.claim(body.ticket_id, claimer=current_user)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await db.commit()

    from app.services.agents import chat_service as cs_mod
    session_state = (
        cs_mod._sessions.get(str(ticket.session_id))
        if ticket.session_id else None
    )
    package = await service.build_handoff_package(ticket, session_state=session_state)

    return ClaimResponse(
        ticket_id=ticket.id,
        ticket_number=ticket.ticket_number,
        claimed_by_user_id=current_user.id,
        claimed_at=ticket.first_response_at or ticket.updated_at,
        handoff_package=package,
    )


@router.post("/release")
async def release_ticket(
    body: ClaimRequest,
    service: QueueDep,
    current_user: ClaimerDep,
    db: DBDep,
) -> dict:
    """Release a claim — the ticket returns to the queue at ``triaged``."""
    try:
        ticket = await service.release(body.ticket_id, by_user=current_user)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    await db.commit()
    return {"ticket_id": str(ticket.id), "status": ticket.status}


@router.post("/resolve", response_model=ResolveResponse)
async def resolve_ticket(
    body: ResolveRequest,
    service: QueueDep,
    current_user: ResolverDep,
    db: DBDep,
) -> ResolveResponse:
    """Mark a ticket resolved + optionally propose a KB improvement candidate.

    The candidate goes into the SME review queue — it does NOT publish to
    the production knowledge base. SMEs review and explicitly promote.
    """
    try:
        ticket, candidate_id = await service.resolve(
            body.ticket_id,
            by_user=current_user,
            resolution_notes=body.resolution_notes,
            propose_knowledge_candidate=body.propose_knowledge_candidate,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    await db.commit()
    return ResolveResponse(
        ticket_id=ticket.id,
        status="resolved",
        knowledge_candidate_id=candidate_id,
    )
