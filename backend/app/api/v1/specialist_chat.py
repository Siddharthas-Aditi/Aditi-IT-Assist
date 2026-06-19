"""Live specialist-chat API.

Routes (all under ``/api/v1/specialist-chat``):

* ``POST   /start``                — start a live session for a claimed ticket.
* ``GET    /{session_id}``         — poll the full state (messages + status).
                                     Applies idle rules lazily.
* ``POST   /{session_id}/message`` — post a message (user or specialist).
* ``POST   /{session_id}/end``     — explicitly end the session.

Plus a sibling on the queue side:

* ``GET    /specialist-queue/mine`` — "My Assigned" view.

All routes require an authenticated user. Participation (user vs specialist
on this session) is enforced inside the service layer, not the route.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import P
from app.models.auth import User
from app.models.specialist_chat import SpecialistChatSession
from app.models.ticket import Ticket
from app.schemas.specialist_chat import (
    EndLiveChatRequest,
    EndLiveChatResponse,
    MyAssignedItem,
    MyAssignedResponse,
    SendSpecialistMessageRequest,
    SpecialistChatMessageOut,
    SpecialistChatSessionOut,
    StartLiveChatRequest,
)
from app.services.auth.dependencies import CurrentUser, require_permissions
from app.services.knowledge.improvement import KnowledgeImprovementService
from app.services.specialist_chat_service import (
    LiveChatPermissionError,
    LiveChatStateError,
    SpecialistChatService,
)

router = APIRouter()
queue_router = APIRouter()  # mounted by the queue router for "/mine"

DBDep = Annotated[AsyncSession, Depends(get_db)]
# Specialists need to start live chats. The send-message / end endpoints
# are gated by *participation* on the session (the user is also allowed to
# message and end), so they use CurrentUser at the route level and the
# service enforces the actual identity check.
SpecialistDep = Annotated[User, Depends(require_permissions(P.SPECIALIST_CHAT_START))]


def _svc(db: DBDep) -> SpecialistChatService:
    return SpecialistChatService(db)


SvcDep = Annotated[SpecialistChatService, Depends(_svc)]


def _to_out(
    session: SpecialistChatSession,
    ticket_number: str | None = None,
) -> SpecialistChatSessionOut:
    return SpecialistChatSessionOut(
        id=session.id,
        ticket_id=session.ticket_id,
        ticket_number=ticket_number,
        user_id=session.user_id,
        user_name=session.user_name,
        user_email=session.user_email,
        specialist_id=session.specialist_id,
        specialist_name=session.specialist_name,
        specialist_email=session.specialist_email,
        status=session.status,  # type: ignore[arg-type]
        started_at=session.started_at,
        last_activity_at=session.last_activity_at,
        ended_at=session.ended_at,
        end_reason=session.end_reason,  # type: ignore[arg-type]
        idle_warning_seconds=session.idle_warning_seconds,
        idle_end_seconds=session.idle_end_seconds,
        messages=[
            SpecialistChatMessageOut(
                id=m.id,
                role=m.role,  # type: ignore[arg-type]
                content=m.content,
                system_event=m.system_event,
                sender_id=m.sender_id,
                created_at=m.created_at,
            )
            for m in session.messages
        ],
    )


@router.post("/start", response_model=SpecialistChatSessionOut)
async def start_session(
    body: StartLiveChatRequest,
    current_user: SpecialistDep,
    svc: SvcDep,
    db: DBDep,
) -> SpecialistChatSessionOut:
    """Open a live chat after the specialist has claimed the ticket.

    The specialist must already be assigned to the ticket (atomic claim
    happens on the queue endpoint). This route refuses to start a session
    if the ticket is unassigned or assigned to someone else.
    """
    ticket = await db.get(Ticket, body.ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.assigned_to != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You must claim the ticket before starting a live chat",
        )
    # Pull the requester row for user details on the session.
    from app.models.auth import User as UserModel
    user_row = await db.get(UserModel, ticket.requester_id)
    if user_row is None:
        raise HTTPException(status_code=404, detail="Requester not found")
    session = await svc.start(
        ticket=ticket,
        specialist=current_user,
        user=user_row,
        idle_warning_seconds=body.idle_warning_seconds,
        idle_end_seconds=body.idle_end_seconds,
    )
    await db.commit()
    state = await svc.get_state(session.id, caller=current_user, run_idle_check=False)
    return _to_out(state, ticket_number=ticket.ticket_number)


@router.get("/{session_id}", response_model=SpecialistChatSessionOut)
async def get_session(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    svc: SvcDep,
    db: DBDep,
) -> SpecialistChatSessionOut:
    """Poll the session state — both participants use the same endpoint.

    Applies idle rules lazily so a user/specialist whose tab woke up still
    sees the correct timed-out state.
    """
    try:
        session = await svc.get_state(session_id, caller=current_user)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LiveChatPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    await db.commit()
    ticket = await db.get(Ticket, session.ticket_id)
    return _to_out(session, ticket_number=ticket.ticket_number if ticket else None)


@router.post("/{session_id}/message", response_model=SpecialistChatMessageOut)
async def send_message(
    session_id: uuid.UUID,
    body: SendSpecialistMessageRequest,
    current_user: CurrentUser,
    svc: SvcDep,
    db: DBDep,
) -> SpecialistChatMessageOut:
    """Post a message into a live session. Role derived from the caller."""
    try:
        msg = await svc.send_message(
            session_id, sender=current_user, content=body.content,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LiveChatPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LiveChatStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return SpecialistChatMessageOut(
        id=msg.id,
        role=msg.role,  # type: ignore[arg-type]
        content=msg.content,
        system_event=msg.system_event,
        sender_id=msg.sender_id,
        created_at=msg.created_at,
    )


@router.post("/{session_id}/end", response_model=EndLiveChatResponse)
async def end_session(
    session_id: uuid.UUID,
    body: EndLiveChatRequest,
    current_user: CurrentUser,
    svc: SvcDep,
    db: DBDep,
) -> EndLiveChatResponse:
    """End the session. The user, the specialist, or an admin may end it.

    Optionally proposes a knowledge candidate (NEVER auto-publishes).
    """
    try:
        session = await svc.end(
            session_id,
            actor=current_user,
            reason=body.reason,
            resolution_notes=body.resolution_notes,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LiveChatPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    candidate_id = None
    if body.propose_knowledge_candidate and body.resolution_notes:
        improvement = KnowledgeImprovementService(db)
        # Tag the proposal with the ticket so the audit chain is intact.
        ticket = await db.get(Ticket, session.ticket_id)
        candidate = await improvement.record_specialist_resolution(
            title=f"Live-chat resolution: {ticket.title if ticket else 'IT issue'}",
            body=body.resolution_notes,
            proposed_by_agent="specialist_chat",
            steps=[],
            category=ticket.category if ticket else None,
            subtype=ticket.subcategory if ticket else None,
            ticket_id=session.ticket_id,
            proposed_by_user_id=current_user.id,
        )
        candidate_id = candidate.id
        session.sent_to_knowledge_review = True
        session.knowledge_candidate_id = candidate_id

    await db.commit()
    return EndLiveChatResponse(
        session_id=session.id,
        status=session.status,  # type: ignore[arg-type]
        end_reason=session.end_reason or body.reason,  # type: ignore[arg-type]
        knowledge_candidate_id=candidate_id,
    )


# ── "My Assigned" — mounted under the queue router ─────────────────────

# "My Assigned" is a queue view (read-only listing of tickets I own); it
# should be visible to anyone with queue-view permission, not gated by the
# write-action permissions.
MyAssignedViewer = Annotated[
    User, Depends(require_permissions(P.SPECIALIST_QUEUE_VIEW))
]


@queue_router.get("/mine", response_model=MyAssignedResponse)
async def my_assigned(
    current_user: MyAssignedViewer,
    db: DBDep,
) -> MyAssignedResponse:
    """The specialist's own assigned tickets + live-chat status for each."""
    stmt = (
        select(Ticket)
        .where(
            and_(
                Ticket.assigned_to == current_user.id,
                Ticket.status.in_(("triaged", "in_progress", "waiting_for_user")),
            )
        )
        .order_by(Ticket.priority.desc(), Ticket.updated_at.desc())
    )
    tickets = list((await db.execute(stmt)).scalars().all())

    # Pull active live sessions for these tickets in one query.
    ticket_ids = [t.id for t in tickets]
    sess_stmt = select(SpecialistChatSession).where(
        and_(
            SpecialistChatSession.specialist_id == current_user.id,
            SpecialistChatSession.ticket_id.in_(ticket_ids) if ticket_ids else False,
        )
    )
    sessions_by_ticket: dict = {}
    if ticket_ids:
        for s in (await db.execute(sess_stmt)).scalars().all():
            # Keep the most recent session per ticket.
            prev = sessions_by_ticket.get(s.ticket_id)
            if prev is None or s.started_at > prev.started_at:
                sessions_by_ticket[s.ticket_id] = s

    items: list[MyAssignedItem] = []
    from app.models.auth import User as UserModel
    for t in tickets:
        s = sessions_by_ticket.get(t.id)
        # Lookup the requester for the user-facing name on the row.
        requester = await db.get(UserModel, t.requester_id)
        items.append(
            MyAssignedItem(
                ticket_id=t.id,
                ticket_number=t.ticket_number,
                title=t.title,
                priority=t.priority,  # type: ignore[arg-type]
                issue_subtype=t.subcategory,
                user_name=getattr(requester, "full_name", None) if requester else None,
                live_session_id=s.id if s else None,
                live_status=s.status if s else None,  # type: ignore[arg-type]
                last_activity_at=s.last_activity_at if s else None,
            )
        )
    return MyAssignedResponse(total=len(items), items=items)
