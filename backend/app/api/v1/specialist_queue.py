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
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.permissions import P
from app.models.auth import User
from app.schemas.escalation import (
    EscalationContextOut,
    ResolutionComparisonIn,
    SpecialistHandoffView,
)
from app.schemas.specialist_handoff import OfferOut, PresenceOut, PresenceUpdate
from app.schemas.specialist_queue import (
    ClaimRequest,
    ClaimResponse,
    HandoffPackage,
    QueueListResponse,
    ResolveRequest,
    ResolveResponse,
)
from app.services.auth.dependencies import require_permissions
from app.services.escalation_service import EscalationService
from app.services.specialist_handoff_service import HandoffService
from app.services.specialist_presence_service import PresenceService, is_available
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


def _presence_out(row) -> PresenceOut:
    """Build the response DTO, computing freshness at request time.

    ``is_available`` is derived rather than stored so a stale heartbeat
    always reads as unavailable, even if the row itself hasn't changed.
    """
    now = datetime.now(UTC)
    return PresenceOut(
        user_id=row.user_id,
        status=row.status,
        last_heartbeat_at=row.last_heartbeat_at,
        is_available=is_available(
            row.status, row.last_heartbeat_at, now, settings.SPECIALIST_PRESENCE_TTL_SECONDS
        ),
    )


async def _claim_response(
    service: SpecialistQueueService,
    ticket,
    current_user: User,
    db: DBDep,
) -> ClaimResponse:
    """Build the ``ClaimResponse`` returned after a successful claim.

    Shared by ``claim_ticket`` (POST /claim) and ``accept_offer``
    (POST /offers/{ticket_id}/accept) — both perform the exact same atomic
    claim via ``SpecialistQueueService.claim`` and must return an identical
    shape. Extracted here so the two routes can't silently drift.
    """
    from app.services.specialist_queue_service import waiting_info

    # `build_handoff_package` prefers the persisted escalation context (and
    # falls back to ticket-only fields) — no live in-memory session lookup is
    # needed or available since the SessionStore refactor removed the
    # process-local `chat_service._sessions` dict.
    package = await service.build_handoff_package(ticket)

    # Freshness at claim time: was the employee still inside the wait window
    # when this claim landed? Tells the client whether to open a live chat
    # ("waiting") or route to the ticket workspace ("likely_left").
    state, waited = waiting_info(ticket.created_at, None)

    return ClaimResponse(
        ticket_id=ticket.id,
        ticket_number=ticket.ticket_number,
        claimed_by_user_id=current_user.id,
        claimed_at=ticket.first_response_at or ticket.updated_at,
        waiting_state=state,  # type: ignore[arg-type]
        waited_seconds=waited,
        handoff_package=package,
    )


@router.put("/availability", response_model=PresenceOut)
async def set_availability(body: PresenceUpdate, user: QueueViewerDep, db: DBDep) -> PresenceOut:
    """Explicitly set this specialist's presence to Available or Away."""
    row = await PresenceService(db).set_status(user.id, body.status)
    await db.commit()
    return _presence_out(row)


@router.post("/availability/heartbeat", response_model=PresenceOut)
async def heartbeat(user: QueueViewerDep, db: DBDep) -> PresenceOut:
    """Keep an Available status fresh without changing it."""
    row = await PresenceService(db).heartbeat(user.id)
    await db.commit()
    return _presence_out(row)


@router.get("/availability", response_model=PresenceOut)
async def get_availability(user: QueueViewerDep, db: DBDep) -> PresenceOut:
    """Return this specialist's current presence.

    No row yet (never set presence) defaults to Away / unavailable rather
    than 404ing — a specialist who hasn't opted in is simply not available.
    """
    row = await PresenceService(db).get(user.id)
    if row is None:
        return PresenceOut(
            user_id=user.id, status="away", last_heartbeat_at=None, is_available=False
        )
    return _presence_out(row)


@router.get("/offers/mine", response_model=list[OfferOut])
async def my_offers(user: QueueViewerDep, service: QueueDep, db: DBDep) -> list[OfferOut]:
    """Active live-handoff offers currently targeted to the caller."""
    from sqlalchemy import select

    from app.models.live_handoff import LiveHandoffOffer
    from app.models.ticket import Ticket

    stmt = (
        select(LiveHandoffOffer, Ticket)
        .join(Ticket, Ticket.id == LiveHandoffOffer.ticket_id)
        .where(
            LiveHandoffOffer.state == "offered",
            LiveHandoffOffer.offered_to == user.id,
        )
        .order_by(LiveHandoffOffer.offered_at.asc())
    )
    rows = (await db.execute(stmt)).all()
    out: list[OfferOut] = []
    for offer, ticket in rows:
        entry = service._to_queue_entry(ticket)  # reuse existing summary builder
        out.append(
            OfferOut(
                ticket_id=ticket.id,
                ticket_number=ticket.ticket_number,
                offered_at=offer.offered_at,
                expires_at=offer.expires_at,
                round_index=offer.round_index,
                state=offer.state,
                summary=entry.summary,
            )
        )
    return out


@router.post("/offers/{ticket_id}/accept", response_model=ClaimResponse)
async def accept_offer(
    ticket_id: uuid.UUID,
    service: QueueDep,
    current_user: ClaimerDep,
    db: DBDep,
) -> ClaimResponse:
    """Accept a targeted live-handoff offer.

    Mirrors ``claim_ticket``: the actual guarantee against two specialists
    picking up the same chat is the atomic DB-level claim, not the offer
    row — so this reuses ``SpecialistQueueService.claim`` verbatim (same
    404/409 mapping) and returns the same ``ClaimResponse`` shape. It does
    NOT start a live-chat session; the frontend calls the live-chat
    ``start`` endpoint separately once the claim succeeds.

    Marking the offer record itself accepted is best-effort bookkeeping —
    the claim has already succeeded by the time we touch it, so a stale/
    already-terminal offer must never fail the request.
    """
    try:
        ticket = await service.claim(ticket_id, claimer=current_user)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await db.commit()

    try:
        await HandoffService(db).accept(ticket_id, specialist=current_user)
        await db.commit()
    except PermissionError:
        pass  # claim already succeeded — offer bookkeeping is non-critical

    return await _claim_response(service, ticket, current_user, db)


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

    session_state = cs_mod._sessions.get(str(ticket.session_id)) if ticket.session_id else None
    return await service.build_handoff_package(ticket, session_state=session_state)


@router.get("/{ticket_id}/handoff-view", response_model=SpecialistHandoffView)
async def get_handoff_view(
    ticket_id: uuid.UUID,
    current_user: QueueViewerDep,
    db: DBDep,
) -> SpecialistHandoffView:
    """Summary-first, transcript-second view a specialist reads on pickup.

    Renders: Overview → AI Handoff Summary → Troubleshooting Attempted →
    KB Signals / Knowledge Gaps → Full Conversation Transcript (collapsible).
    Degrades gracefully for tickets without a persisted escalation context.
    """
    view = await EscalationService(db).get_handoff_view(ticket_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return view


@router.get("/{ticket_id}/escalation-context", response_model=EscalationContextOut)
async def get_escalation_context(
    ticket_id: uuid.UUID,
    current_user: QueueViewerDep,
    db: DBDep,
) -> EscalationContextOut:
    """Return the raw structured escalation context (analytics / admin use)."""
    context = await EscalationService(db).get_context_out(ticket_id)
    if context is None:
        raise HTTPException(status_code=404, detail="No escalation context for this ticket")
    return context


@router.post("/{ticket_id}/resolution-comparison", response_model=EscalationContextOut)
async def record_resolution_comparison(
    ticket_id: uuid.UUID,
    body: ResolutionComparisonIn,
    current_user: ResolverDep,
    db: DBDep,
) -> EscalationContextOut:
    """Capture what the specialist actually did vs. what the AI suggested.

    Stores structured comparison data for human-reviewed AI/KB improvement.
    There is NO uncontrolled self-learning.
    """
    service = EscalationService(db)
    context = await service.record_resolution_comparison(
        ticket_id=ticket_id,
        specialist_resolution_summary=body.specialist_resolution_summary,
        specialist_resolution_steps=body.specialist_resolution_steps,
        final_resolution_category=body.final_resolution_category,
        ai_vs_specialist_resolution_gap=body.ai_vs_specialist_resolution_gap,
        kb_candidate_flag=body.kb_candidate_flag,
        actor=current_user,
    )
    if context is None:
        raise HTTPException(status_code=404, detail="No escalation context for this ticket")
    await db.commit()
    out = await service.get_context_out(ticket_id)
    assert out is not None
    return out


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

    return await _claim_response(service, ticket, current_user, db)


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
